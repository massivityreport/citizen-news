import { api, ApiError } from "../api/client";
import { clearLocalVotes, readLocalVotes } from "./storage";

/** Taille maximale d'un lot accepté par POST /api/votes/claim. */
export const CLAIM_BATCH_SIZE = 200;

export type ClaimResult =
  /** Aucun vote local à rattacher. */
  | { status: "none"; sent: 0; claimed: 0 }
  /** Tout est rattaché et la liste locale est vidée. `claimed` = votes réellement créés par le serveur. */
  | { status: "ok"; sent: number; claimed: number }
  /** Session absente ou expirée (401) : la liste locale est conservée. */
  | { status: "unauthorized"; sent: number; claimed: number }
  /** Erreur réseau, 5xx, 422… : la liste locale est conservée, on réessaiera à la prochaine session. */
  | { status: "error"; sent: number; claimed: number };

async function run(): Promise<ClaimResult> {
  const votes = readLocalVotes();
  if (votes.length === 0) return { status: "none", sent: 0, claimed: 0 };

  let claimed = 0;
  for (let i = 0; i < votes.length; i += CLAIM_BATCH_SIZE) {
    try {
      const res = await api.claimVotes(votes.slice(i, i + CLAIM_BATCH_SIZE));
      claimed += res.claimed;
    } catch (e) {
      const status = e instanceof ApiError && e.isUnauthorized ? "unauthorized" : "error";
      return { status, sent: votes.length, claimed };
    }
  }
  // Un vote déjà enregistré côté serveur n'est pas écrasé : claimed peut être < sent, on vide quand même.
  clearLocalVotes();
  return { status: "ok", sent: votes.length, claimed };
}

let inFlight: Promise<ClaimResult> | null = null;

/**
 * Rattache les votes anonymes du navigateur au compte connecté, par lots de 200.
 * Les appels simultanés partagent la même requête (connexion + nouvelle tentative silencieuse).
 */
export function claimLocalVotes(): Promise<ClaimResult> {
  inFlight ??= run().finally(() => {
    inFlight = null;
  });
  return inFlight;
}
