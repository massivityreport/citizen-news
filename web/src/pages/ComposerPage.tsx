import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { Link } from "react-router-dom";
import { usePool } from "../api/hooks";
import type { PoolTab, TopicCard } from "../api/types";
import { usePageTitle } from "../components/usePageTitle";
import { ActionBar, Carousel, type CarouselActions } from "../composer/Carousel";
import { ExploreTabs, PANEL_ID, TABS, tabId } from "../composer/ExploreTabs";
import { Gauge } from "../composer/Gauge";
import { Preview } from "../composer/Preview";
import { ReviewPanel } from "../composer/ReviewPanel";
import { useComposition, type Result } from "../composer/useComposition";
import styles from "../composer/composer.module.css";
import { getSeed, getSeen, markSeen, orderRandom, subscribeSeen } from "../lib/browse";
import { MAX_PLACES } from "../lib/draft";
import { formatHour } from "../lib/format";

type Positions = Record<PoolTab, { id: number; index: number } | null>;
type Notice = { kind: "full" } | { kind: "error"; text: string } | { kind: "merge"; text: string } | null;

const EMPTY_TEXT: Record<PoolTab, string> = {
  random: "Aucun sujet n’est encore disponible aujourd’hui. Revenez un peu plus tard.",
  recent: "Aucun sujet récent pour le moment.",
  radar: "Aucun sujet peu couvert par les médias pour le moment.",
};

export default function ComposerPage() {
  const h1 = usePageTitle("Composer ma une");
  const [seed] = useState(getSeed);
  const seen = useSyncExternalStore(subscribeSeen, getSeen);
  const [tab, setTab] = useState<PoolTab>("random");
  const [view, setView] = useState<"browse" | "review">("browse");
  const [positions, setPositions] = useState<Positions>({ random: null, recent: null, radar: null });
  const [replacing, setReplacing] = useState<{ id: number; place: number } | null>(null);
  const [status, setStatus] = useState("");
  const [notice, setNotice] = useState<Notice>(null);

  // « Au hasard » est toujours chargé : il sert de référence pour les titres de l'aperçu.
  const random = usePool("random", seed);
  const other = usePool(tab, seed, tab !== "random");
  const query = tab === "random" ? random : other;

  const meta = random.data ?? other.data;
  const editionMeta = useMemo(
    () => (meta ? { edition_date: meta.edition_date, closes_at: meta.closes_at, open: meta.open } : undefined),
    [meta],
  );
  const poolIds = useMemo(
    () =>
      random.data && random.data.total <= random.data.items.length
        ? new Set(random.data.items.map((t) => t.id))
        : undefined,
    [random.data],
  );
  const comp = useComposition(editionMeta, poolIds);

  const known = useMemo(() => {
    const m = new Map<number, TopicCard>();
    for (const t of other.data?.items ?? []) m.set(t.id, t);
    for (const t of random.data?.items ?? []) m.set(t.id, t);
    return m;
  }, [random.data, other.data]);

  const items = useMemo(() => {
    const list = query.data?.items ?? [];
    return tab === "random" ? orderRandom(list, seen) : list;
  }, [query.data, tab, seen]);

  // Position : retenue par sujet (la carte courante reste en place quand la liste est rafraîchie) et par onglet.
  const pos = positions[tab];
  let index = -1;
  if (items.length > 0) {
    index = pos ? items.findIndex((t) => t.id === pos.id) : -1;
    if (index < 0) {
      const lastSeen = tab === "random" ? items.reduce((acc, t, i) => (seen.includes(t.id) ? i : acc), -1) : -1;
      index = pos ? Math.min(pos.index, items.length - 1) : Math.max(0, lastSeen);
    }
  }
  const topic = index >= 0 ? items[index] : undefined;
  if (topic && (!pos || pos.id !== topic.id || pos.index !== index)) {
    setPositions((p) => ({ ...p, [tab]: { id: topic.id, index } }));
  }

  const topicId = topic?.id;
  useEffect(() => {
    if (tab === "random" && topicId !== undefined) markSeen(topicId);
  }, [tab, topicId]);

  const inUneSet = useMemo(() => new Set(comp.ids), [comp.ids]);
  const titles = comp.ids.map((id) => known.get(id)?.title ?? "Ce sujet n’est plus au bassin du jour");
  const readOnly = comp.closed || !comp.ready;
  const closes = comp.closesAt;
  const replaceTarget = replacing && comp.ids[replacing.place - 1] === replacing.id ? replacing : null;

  function go(i: number) {
    const t = items[i];
    if (!t) return;
    setPositions((p) => ({ ...p, [tab]: { id: t.id, index: i } }));
    setNotice(null);
    setStatus(`Sujet ${i + 1} sur ${items.length} : ${t.title}`);
  }

  function report(r: Result, t: TopicCard) {
    const count = (n: number) => `${n}/${MAX_PLACES}`;
    switch (r.outcome) {
      case "added":
      case "removed": {
        const n = Math.max(0, Math.min(MAX_PLACES, comp.ids.length + (r.outcome === "added" ? 1 : -1)));
        setNotice(null);
        setStatus(r.outcome === "added" ? `Ajouté à votre une (${count(n)})` : `Retiré de votre une (${count(n)})`);
        break;
      }
      case "present":
      case "absent":
        break;
      case "full":
        setNotice({ kind: "full" });
        setStatus(`Votre une est complète (${count(MAX_PLACES)}). Ouvrez « Revoir et valider » pour remplacer un sujet.`);
        break;
      case "closed":
        setNotice(null);
        setStatus("La clôture est passée : votre une n’est plus modifiable.");
        break;
      case "unavailable":
        setStatus("Votre une se charge, réessayez dans un instant.");
        break;
      default:
        setNotice({ kind: "error", text: r.message ?? `Le sujet « ${t.title} » n’a pas pu être mis à jour.` });
        setStatus(r.message ?? "L’opération a échoué.");
    }
  }

  async function onAdd() {
    if (!topic || readOnly) return;
    if (replaceTarget && !inUneSet.has(topic.id)) {
      const r = await comp.replace(replaceTarget.id, topic.id);
      if (r.outcome === "added") {
        setReplacing(null);
        setNotice(null);
        setStatus(`Sujet remplacé : « ${topic.title} » est à la place ${replaceTarget.place}.`);
      } else report(r, topic);
      return;
    }
    report(await comp.add(topic.id), topic);
  }

  async function onRemove() {
    if (!topic || readOnly) return;
    report(await comp.remove(topic.id), topic);
  }

  const actions: CarouselActions = {
    onPrev: () => go(index - 1),
    onNext: () => go(index + 1),
    onAdd: () => void onAdd(),
    onRemove: () => void onRemove(),
  };

  async function mergeDraft() {
    const r = await comp.mergeDraft();
    if (r.outcome === "added") setStatus("Brouillon fusionné avec votre une.");
    else if (r.outcome === "closed") setStatus("La clôture est passée : le brouillon n’a pas pu être fusionné.");
    else if (r.outcome === "error" || r.outcome === "unauthorized")
      setNotice({ kind: "error", text: r.message ?? "La fusion a échoué. Réessayez." });
  }

  const showDraftOffer = comp.mode === "server" && comp.ready && !comp.closed && comp.mergeFailed && comp.pendingDraft.length > 0;

  if (view === "review") {
    return (
      <>
        <p role="status" className={styles.srOnly}>
          {status}
        </p>
        <ReviewPanel
          ids={comp.ids}
          topics={known}
          signedIn={comp.mode === "server"}
          closed={comp.closed}
          closesAt={closes}
          onRemove={(id) => {
            const t = known.get(id);
            void comp.remove(id).then((r) => report(r, t ?? ({ title: "ce sujet" } as TopicCard)));
          }}
          onReplace={(id, place) => {
            setReplacing({ id, place });
            setView("browse");
            setStatus(`Choisissez le sujet qui prendra la place ${place}, puis ajoutez-le.`);
          }}
          onBack={() => setView("browse")}
        />
      </>
    );
  }

  let body;
  if (query.isPending) {
    body = <div className={styles.skeleton} role="status" aria-busy="true" aria-label="Chargement des sujets" />;
  } else if (query.isError && !query.data) {
    body = (
      <div className={styles.notice} role="alert" data-kind="error">
        <p className={styles.noticeText}>Les sujets n’ont pas pu être chargés. Vérifiez votre connexion.</p>
        <button type="button" className={styles.btn} onClick={() => void query.refetch()}>
          Réessayer
        </button>
      </div>
    );
  } else if (!topic) {
    body = <p className={styles.empty}>{EMPTY_TEXT[tab]}</p>;
  } else {
    body = (
      <Carousel
        key={tab}
        topic={topic}
        inUne={inUneSet.has(topic.id)}
        position={index + 1}
        total={items.length}
        actions={actions}
        disabled={readOnly}
      />
    );
  }

  const addLabel = replaceTarget ? `Mettre à la place ${replaceTarget.place}` : "Ajouter à ma une";

  return (
    <div className={styles.page}>
      <div className={styles.top}>
        <p className={styles.eyebrow}>Citizen News</p>
        <h1 ref={h1} tabIndex={-1}>
          Composer ma une
        </h1>
        <p className={styles.closes}>
          {closes ? (
            <>
              Prochaine une à <time dateTime={closes}>{formatHour(closes)}</time>
            </>
          ) : (
            "Prochaine une : heure en cours de chargement"
          )}
        </p>
        <div className={styles.gaugeRow}>
          <Gauge count={comp.ids.length} />
          <span className={styles.pill} data-saved={comp.saved && comp.ready ? "true" : "false"}>
            {comp.mode === "loading" || (comp.saved && !comp.ready) ? "Chargement…" : comp.saved ? (comp.saving ? "Enregistrement…" : "Enregistrée") : "Non enregistrée"}
          </span>
        </div>
      </div>

      {comp.closed && (
        <p className={styles.notice} role="status">
          La clôture est passée : votre une est en lecture seule. La prochaine une repart vide.
        </p>
      )}
      {comp.loadError && (
        <div className={styles.notice} role="alert" data-kind="error">
          <p className={styles.noticeText}>{comp.loadError}</p>
          <button type="button" className={styles.btn} onClick={comp.retryLoad}>
            Réessayer
          </button>
        </div>
      )}
      {comp.mergeBusy && (
        <p className={styles.notice} role="status">
          Fusion de votre brouillon avec votre une…
        </p>
      )}
      {comp.mergeNote && (
        <p className={styles.notice} role="status">
          {comp.mergeNote}
        </p>
      )}
      {showDraftOffer && (
        <div className={styles.notice} role="group" aria-label="Brouillon de cet appareil">
          <p className={styles.noticeText}>
            La fusion de votre brouillon ({comp.pendingDraft.length} sujet{comp.pendingDraft.length > 1 ? "s" : ""}) n’a pas abouti. Il
            est resté sur cet appareil : réessayer ?
          </p>
          <button type="button" className={styles.btn} onClick={() => void mergeDraft()} disabled={comp.mergeBusy}>
            {comp.mergeBusy ? "Fusion…" : "Réessayer la fusion"}
          </button>
          <button type="button" className={`${styles.btn} ${styles.btnLight}`} onClick={comp.discardDraft}>
            Supprimer le brouillon
          </button>
        </div>
      )}

      <h2 className={styles.srOnly}>Aperçu de ma une</h2>
      <Preview titles={titles} highlight={replaceTarget ? replaceTarget.place - 1 : null} />
      <button type="button" className={`${styles.btn} ${styles.review}`} onClick={() => setView("review")}>
        Revoir et valider
      </button>

      {replaceTarget && (
        <div className={styles.notice}>
          <p className={styles.noticeText}>
            Vous remplacez la place {replaceTarget.place}. Parcourez les sujets puis choisissez « {addLabel} ».
          </p>
          <button type="button" className={`${styles.btn} ${styles.btnLight}`} onClick={() => setReplacing(null)}>
            Annuler
          </button>
        </div>
      )}

      <h2 className={styles.srOnly}>Sujets à explorer</h2>
      <ExploreTabs value={tab} onChange={(t) => (setTab(t), setNotice(null))} />
      <div role="tabpanel" id={PANEL_ID} aria-labelledby={tabId(tab)} aria-label={TABS.find((t) => t.id === tab)?.label}>
        {body}
      </div>

      {notice?.kind === "full" && (
        <div className={styles.notice} data-kind="error">
          <p className={styles.noticeText}>
            Votre une est complète ({MAX_PLACES}/{MAX_PLACES}). Pour ajouter ce sujet, remplacez-en un autre.
          </p>
          <button type="button" className={styles.btn} onClick={() => setView("review")}>
            Revoir et valider
          </button>
        </div>
      )}
      {(notice?.kind === "error" || notice?.kind === "merge") && (
        <p className={styles.notice} data-kind={notice.kind === "error" ? "error" : undefined}>
          {notice.text}
        </p>
      )}
      <p role="status" className={styles.status}>
        {status}
      </p>

      {topic && (
        <ActionBar
          actions={actions}
          canPrev={index > 0}
          canNext={index < items.length - 1}
          inUne={inUneSet.has(topic.id)}
          readOnly={readOnly}
          addLabel={addLabel}
        />
      )}
      <p className={styles.help}>
        <Link to="/comment-ca-marche">Comment fonctionnent le tirage au hasard et l’agrégation ?</Link>
      </p>
    </div>
  );
}
