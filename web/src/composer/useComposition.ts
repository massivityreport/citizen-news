import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import { meKey, uneKey, useMe, useUne } from "../api/hooks";
import type { Une } from "../api/types";
import { MAX_PLACES } from "../lib/draft";
import { draftStore } from "../lib/draftStore";
import { journal } from "../lib/journal";

export type Outcome = "added" | "removed" | "present" | "absent" | "full" | "closed" | "unavailable" | "unauthorized" | "error";
export interface Result {
  outcome: Outcome;
  message?: string;
}

export interface EditionMeta {
  edition_date: string;
  closes_at: string;
  open: boolean;
}

const CLOSED_RE = /cl[ôo]ture/i;

/**
 * Composition de la une. Avec session (GET /api/me : 200) la une est celle du serveur, modifiée de façon optimiste
 * (retour arrière sur erreur). Sans session, c'est le brouillon local. Les actions lisent toujours l'état
 * courant (cache ou stockage), jamais une fermeture périmée : elles s'enchaînent sans se marcher dessus.
 */
export function useComposition(meta: EditionMeta | undefined, poolIds?: ReadonlySet<number>) {
  const qc = useQueryClient();
  const me = useMe();
  const mode = me.isPending ? "loading" : me.data ? "server" : "local";
  const une = useUne(mode === "server");
  const draft = useSyncExternalStore(draftStore.subscribe, draftStore.get);
  const [closedFor, setClosedFor] = useState<string | null>(null);
  const [pending, setPending] = useState(0);
  const inflight = useRef(0);

  // Session disparue entre-temps : on repasse au brouillon local.
  const uneError = une.error;
  useEffect(() => {
    if (uneError instanceof ApiError && uneError.status === 401) {
      qc.setQueryData(meKey, null);
      qc.removeQueries({ queryKey: uneKey });
    }
  }, [uneError, qc]);

  // Brouillon local : on retire ce qui n'est plus au bassin (poolIds fourni seulement si le bassin est complet)
  // et un brouillon d'une édition passée.
  useEffect(() => {
    if (mode !== "local" || !meta) return;
    const d = draftStore.get();
    if (d.ids.length === 0) return;
    const stale = d.editionDate !== null && d.editionDate !== meta.edition_date;
    const kept = stale ? [] : poolIds ? d.ids.filter((id) => poolIds.has(id)) : d.ids;
    if (stale || kept.length !== d.ids.length) draftStore.set({ editionDate: meta.edition_date, ids: kept });
  }, [mode, meta, poolIds, draft]);

  const unData = mode === "server" ? une.data : undefined;
  const editionDate = unData?.edition_date ?? meta?.edition_date ?? null;
  const closesAt = unData?.closes_at ?? meta?.closes_at ?? null;
  // Un brouillon d'une autre édition que celle de la une affichée est ignoré (aussi en mode serveur).
  const draftStale = draft.editionDate !== null && editionDate !== null && draft.editionDate !== editionDate;
  const localIds = draftStale ? [] : draft.ids;
  const ids = mode === "server" ? (unData?.topic_ids ?? []) : mode === "local" ? localIds : [];
  const closed = unData?.open === false || meta?.open === false || (editionDate !== null && closedFor === editionDate);
  const ready = mode === "local" || (mode === "server" && une.isSuccess);

  const current = useCallback((): number[] => {
    if (mode === "server") return qc.getQueryData<Une>(uneKey)?.topic_ids ?? [];
    const d = draftStore.get();
    return meta && d.editionDate && d.editionDate !== meta.edition_date ? [] : d.ids;
  }, [mode, qc, meta]);

  const setServerIds = useCallback(
    (fn: (ids: number[]) => number[]) =>
      qc.setQueryData<Une>(uneKey, (old) => (old ? { ...old, topic_ids: fn(old.topic_ids) } : old)),
    [qc],
  );

  /** Écriture serveur optimiste ; revient en arrière si elle échoue. */
  const writeServer = useCallback(
    async (id: number, adding: boolean): Promise<Result> => {
      setServerIds((l) => (adding ? [...l.filter((x) => x !== id), id] : l.filter((x) => x !== id)));
      inflight.current += 1;
      setPending((n) => n + 1);
      try {
        const body = await (adding ? api.uneAdd(id) : api.uneRemove(id));
        // Une réponse n'écrase l'état que s'il ne reste aucune autre écriture en vol.
        if (inflight.current === 1) qc.setQueryData(uneKey, body);
        journal.record({ type: adding ? "topic_added" : "topic_removed", topic_id: id });
        return { outcome: adding ? "added" : "removed" };
      } catch (e) {
        setServerIds((l) => (adding ? l.filter((x) => x !== id) : [...l.filter((x) => x !== id), id]));
        if (e instanceof ApiError) {
          if (e.status === 401) {
            qc.setQueryData(meKey, null);
            qc.removeQueries({ queryKey: uneKey });
            return { outcome: "unauthorized", message: e.message };
          }
          if (e.status === 409 && CLOSED_RE.test(e.message)) {
            setClosedFor(qc.getQueryData<Une>(uneKey)?.edition_date ?? meta?.edition_date ?? null);
            return { outcome: "closed", message: e.message };
          }
          if (e.status === 409) {
            void qc.invalidateQueries({ queryKey: uneKey }); // le serveur a une autre idée de la une
            return { outcome: "full", message: e.message };
          }
          return { outcome: "error", message: e.message };
        }
        return { outcome: "error", message: "Le réseau ne répond pas. Réessayez dans un instant." };
      } finally {
        inflight.current -= 1;
        setPending((n) => n - 1);
      }
    },
    [qc, setServerIds, meta],
  );

  const write = useCallback(
    async (id: number, adding: boolean): Promise<Result> => {
      if (!ready) return { outcome: "unavailable" };
      if (closed) return { outcome: "closed" };
      const cur = current();
      const has = cur.includes(id);
      if (adding && has) return { outcome: "present" };
      if (!adding && !has) return { outcome: "absent" };
      if (adding && cur.length >= MAX_PLACES) return { outcome: "full" };
      if (mode === "local") {
        const d = draftStore.get();
        const next = adding ? [...cur, id] : cur.filter((x) => x !== id);
        draftStore.set({ editionDate: meta?.edition_date ?? d.editionDate, ids: next });
        journal.record({ type: adding ? "topic_added" : "topic_removed", topic_id: id });
        return { outcome: adding ? "added" : "removed" };
      }
      return writeServer(id, adding);
    },
    [ready, closed, current, mode, meta, writeServer],
  );

  const add = useCallback((id: number) => write(id, true), [write]);
  const remove = useCallback((id: number) => write(id, false), [write]);

  /** Retire `oldId` puis ajoute `newId` ; si l'ajout échoue, `oldId` est remis. */
  const replace = useCallback(
    async (oldId: number, newId: number): Promise<Result> => {
      const removed = await write(oldId, false);
      if (removed.outcome !== "removed" && removed.outcome !== "absent") return removed;
      const added = await write(newId, true);
      if (added.outcome !== "added" && added.outcome !== "present" && removed.outcome === "removed") await write(oldId, true);
      return added;
    },
    [write],
  );

  /** Brouillon local en attente de fusion : connecté, ids pas déjà dans la une. */
  const pendingDraft = mode === "server" ? localIds.filter((id) => !ids.includes(id)) : [];

  const merging = useRef(false);
  const [mergeBusy, setMergeBusy] = useState(false);
  const email = me.data?.email ?? null;
  // Message et échec sont attachés au compte qui les a produits : ils disparaissent au changement de compte ou à la déconnexion.
  const [mergeFailedFor, setMergeFailed] = useState<string | null>(null);
  const [mergeNoteFor, setMergeNote] = useState<{ email: string; text: string } | null>(null);
  const mergeFailed = email !== null && mergeFailedFor === email;
  const mergeNote = email !== null && mergeNoteFor?.email === email ? mergeNoteFor.text : null;

  /**
   * POST /api/me/une/merge avec le brouillon local (sans ce qui est déjà dans la une), puis vide le brouillon
   * SEULEMENT après succès. Un seul appel à la fois (double clic, StrictMode) ; en cas d'échec, le brouillon reste.
   * Si la page est démontée pendant l'envoi, le brouillon n'est pas vidé ; un rejeu ne duplique rien : le serveur
   * ignore les doublons (le merge est idempotent).
   */
  const mergeDraft = useCallback(async (): Promise<Result> => {
    if (merging.current) return { outcome: "unavailable" };
    const d = draftStore.get();
    // La une doit venir d'une requête réussie et à jour (pas en cours de rafraîchissement) pour ce compte.
    const state = qc.getQueryState<Une>(uneKey);
    const base = qc.getQueryData<Une>(uneKey);
    if (!email || !base || state?.status !== "success" || state.fetchStatus !== "idle") return { outcome: "unavailable" };
    if (d.editionDate !== null && d.editionDate !== base.edition_date) {
      draftStore.clear(); // brouillon d'une autre édition : jamais fusionné
      return { outcome: "absent" };
    }
    const toMerge = d.ids.filter((id) => !base.topic_ids.includes(id));
    if (toMerge.length === 0) {
      draftStore.clear(); // rien à fusionner : tout est déjà dans la une (à jour)
      return { outcome: "absent" };
    }
    merging.current = true;
    setMergeBusy(true);
    setMergeFailed(null);
    try {
      const res = await api.uneMerge(toMerge);
      qc.setQueryData(uneKey, res.une);
      draftStore.clear();
      const n = res.added;
      const g = res.ignored;
      setMergeNote({
        email,
        text: `${n} sujet${n > 1 ? "s ajoutés" : " ajouté"} à votre une${g > 0 ? `, ${g} ignoré${g > 1 ? "s" : ""} (une complète ou sujet plus au bassin)` : ""}.`,
      });
      return { outcome: "added" };
    } catch (e) {
      if (e instanceof ApiError && e.status === 409 && CLOSED_RE.test(e.message)) {
        setClosedFor(qc.getQueryData<Une>(uneKey)?.edition_date ?? null);
        return { outcome: "closed", message: e.message };
      }
      setMergeFailed(email);
      if (e instanceof ApiError && e.status === 401) {
        qc.setQueryData(meKey, null);
        return { outcome: "unauthorized", message: e.message };
      }
      return { outcome: "error", message: e instanceof ApiError ? e.message : "Le réseau ne répond pas. Réessayez." };
    } finally {
      merging.current = false;
      setMergeBusy(false);
    }
  }, [qc, email]);

  // Fusion automatique, une fois par connexion (par e-mail) : jamais deux envois, même en StrictMode.
  const autoFor = useRef<string | null>(null);
  const hasDraft = localIds.length > 0;
  const settled = une.isSuccess && !une.isFetching;
  useEffect(() => {
    if (mode !== "server") {
      autoFor.current = null;
      return;
    }
    if (!settled || closed || !email || autoFor.current === email) return;
    if (draftStale) {
      draftStore.clear();
      return;
    }
    if (!hasDraft) return;
    autoFor.current = email;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- envoi réseau déclenché une fois ; l'état « en cours » suit
    void mergeDraft();
  }, [mode, settled, closed, email, hasDraft, draftStale, mergeDraft]);

  return {
    mode,
    ready,
    ids,
    /** Enregistrée côté serveur (compte) ; sinon brouillon local. */
    saved: mode === "server",
    saving: pending > 0,
    closed,
    editionDate,
    closesAt,
    loadError: mode === "server" && une.isError ? "Votre une n’a pas pu être chargée." : null,
    retryLoad: () => void une.refetch(),
    add,
    remove,
    replace,
    pendingDraft,
    mergeBusy,
    /** L'envoi automatique a échoué : le brouillon est resté, la reprise est manuelle. */
    mergeFailed,
    mergeNote,
    mergeDraft,
    discardDraft: () => draftStore.clear(),
    email,
  };
}
