import { useEffect, useRef } from "react";
import { useMe } from "../api/hooks";
import { claimLocalVotes } from "./claim";
import { readLocalVotes } from "./storage";

/**
 * Si une session existe au chargement et que des votes locaux subsistent (claim échoué
 * lors d'une session précédente), retente le rattachement en silence, une fois par session.
 */
export function useClaimOnSession() {
  const email = useMe().data?.email;
  const tried = useRef<string | null>(null);
  useEffect(() => {
    if (!email || tried.current === email) return;
    tried.current = email;
    if (readLocalVotes().length > 0) void claimLocalVotes();
  }, [email]);
}
