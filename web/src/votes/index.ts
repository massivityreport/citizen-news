/**
 * Votes anonymes (sans compte), conservés dans le navigateur.
 *
 * Rattachement après connexion : `claimLocalVotes()` (lots de 200, vide la liste
 * seulement si tout est passé).
 */
export { clearLocalVotes, readLocalVotes, saveLocalVote, STORAGE_KEY } from "./storage";
export { useVoteDeck } from "./useVoteDeck";
export type { VoteNotice } from "./useVoteDeck";
export { CLAIM_BATCH_SIZE, claimLocalVotes } from "./claim";
export type { ClaimResult } from "./claim";
export { useClaimOnSession } from "./useClaimOnSession";
