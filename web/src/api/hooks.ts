import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { api } from "./client";

export const meKey = ["me"] as const;

export function useMe() {
  return useQuery({ queryKey: meKey, queryFn: api.me, staleTime: 5 * 60_000 });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.logout,
    onSuccess: () => qc.setQueryData(meKey, null),
  });
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
