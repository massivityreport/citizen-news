import { keepPreviousData, useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { PoolTab } from "./types";

export const meKey = ["me"] as const;

export function useMe() {
  return useQuery({ queryKey: meKey, queryFn: api.me, staleTime: 5 * 60_000 });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.logout,
    onSuccess: () => {
      qc.setQueryData(meKey, null);
      qc.removeQueries({ queryKey: uneKey }); // la une du compte ne reste pas en mémoire
    },
  });
}

export const uneKey = ["une"] as const;
export const poolKey = (tab: PoolTab, seed: string) => ["pool", tab, tab === "random" ? seed : ""] as const;

const POOL_REFRESH_MS = 60_000;

/**
 * Bassin du jour. Rafraîchi chaque minute et à la reprise de focus ; l'ordre « random » dépend de la graine
 * de la session de navigation (le client réordonne ensuite : vus d'abord).
 */
export function usePool(tab: PoolTab, seed: string, enabled = true) {
  return useQuery({
    queryKey: poolKey(tab, seed),
    queryFn: () => api.pool(tab, tab === "random" ? seed : undefined),
    enabled,
    staleTime: 10_000,
    refetchInterval: POOL_REFRESH_MS,
    refetchOnWindowFocus: true,
  });
}

/** Une du compte connecté (jamais sans session). */
export function useUne(enabled: boolean) {
  return useQuery({
    queryKey: uneKey,
    queryFn: api.une,
    enabled,
    staleTime: 60_000,
    refetchOnWindowFocus: true,
  });
}

export const currentEditionKey = ["edition", "current"] as const;
export const editionKey = (date: string) => ["edition", date] as const;
export const editionsKey = (limit: number) => ["editions", limit] as const;

const RETRY_PUBLICATION_MS = 15_000;

/**
 * Une publiée. Une fois l'heure de clôture passée (horloge du lecteur corrigée du décalage avec le serveur),
 * on réinterroge toutes les 15 s jusqu'à ce que la nouvelle édition (et un nouveau next_close_at) arrive.
 */
export function useCurrentEdition() {
  return useQuery({
    queryKey: currentEditionKey,
    queryFn: api.currentEdition,
    staleTime: 60_000,
    refetchInterval: (query) => {
      const { data, dataUpdatedAt } = query.state;
      if (!data) return false;
      const offset = Date.parse(data.server_time) - dataUpdatedAt;
      return Date.parse(data.next_close_at) <= Date.now() + offset ? RETRY_PUBLICATION_MS : false;
    },
  });
}

/** Une édition publiée est figée : jamais rafraîchie. */
export function useEdition(date: string, enabled = true) {
  return useQuery({ queryKey: editionKey(date), queryFn: () => api.edition(date), staleTime: Infinity, enabled });
}

export function useEditions(limit = 30) {
  return useQuery({ queryKey: editionsKey(limit), queryFn: () => api.editions(limit), staleTime: 5 * 60_000 });
}

export const adminSessionKey = ["admin", "session"] as const;

/** true : session admin valide ; false : à connecter. Les futures requêtes admin utiliseront la clé ["admin", …]. */
export function useAdminSession() {
  return useQuery({ queryKey: adminSessionKey, queryFn: api.adminMe, staleTime: 5 * 60_000 });
}

export function useAdminLogin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.adminLogin,
    onSuccess: () => qc.setQueryData(adminSessionKey, true),
  });
}

/** Session admin terminée (déconnexion ou 401) : on oublie les données admin, on garde la requête de session. */
export function endAdminSession(qc: QueryClient) {
  qc.removeQueries({ queryKey: ["admin"], predicate: (q) => q.queryKey[1] !== adminSessionKey[1] });
  qc.setQueryData(adminSessionKey, false);
}

export function useAdminLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.adminLogout,
    onSettled: () => endAdminSession(qc), // les données admin ne survivent pas à la session
  });
}

export const adminSourcesKey = ["admin", "sources"] as const;

export function useAdminSources() {
  return useQuery({ queryKey: adminSourcesKey, queryFn: api.adminSources });
}

export function useAddSource() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.adminAddSource,
    onSuccess: () => qc.invalidateQueries({ queryKey: adminSourcesKey }),
  });
}

export function useSetSourceActive() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, active }: { id: number; active: boolean }) => api.adminSetSourceActive(id, active),
    onSettled: () => qc.invalidateQueries({ queryKey: adminSourcesKey }),
  });
}

export function useDeleteSource() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, confirm }: { id: number; confirm: number }) => api.adminDeleteSource(id, confirm),
    // même en cas de refus (nombre d’articles changé) : on recharge la liste pour afficher le vrai nombre
    onSettled: () => qc.invalidateQueries({ queryKey: adminSourcesKey }),
  });
}

// Listes du backoffice : la clé contient tous les paramètres (page, tri, filtres) ; keepPreviousData garde
// l’ancienne page affichée pendant le chargement de la suivante.
export const adminArticlesKey = (params: Record<string, string>) => ["admin", "articles", params] as const;
export const adminTopicsKey = (params: Record<string, string>) => ["admin", "topics", params] as const;
export const adminTopicKey = (id: number) => ["admin", "topic", id] as const;
export const adminTopicVotesKey = (id: number, params: Record<string, string>) => ["admin", "topic", id, "votes", params] as const;

export function useAdminArticles(params: Record<string, string>) {
  return useQuery({ queryKey: adminArticlesKey(params), queryFn: () => api.adminArticles(params), placeholderData: keepPreviousData });
}

export function useAdminTopics(params: Record<string, string>) {
  return useQuery({ queryKey: adminTopicsKey(params), queryFn: () => api.adminTopics(params), placeholderData: keepPreviousData });
}

export function useAdminTopic(id: number) {
  return useQuery({ queryKey: adminTopicKey(id), queryFn: () => api.adminTopic(id) });
}

export function useAdminTopicVotes(id: number, params: Record<string, string>) {
  return useQuery({
    queryKey: adminTopicVotesKey(id, params),
    queryFn: () => api.adminTopicVotes(id, params),
    placeholderData: keepPreviousData,
  });
}

export const adminStatsKey = ["admin", "stats"] as const;

/** Statistiques de l’accueil : fraîches 1 minute, jamais de rafraîchissement automatique (bouton « Actualiser »). */
export function useAdminStats() {
  return useQuery({ queryKey: adminStatsKey, queryFn: api.adminStats, staleTime: 60_000, refetchOnWindowFocus: false });
}
