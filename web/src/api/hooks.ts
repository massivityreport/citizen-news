import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
