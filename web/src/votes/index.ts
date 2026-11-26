/**
 * Votes anonymes (sans compte), conservés dans le navigateur.
 *
 * Rattachement après connexion :
 *   const votes = readLocalVotes();
 *   if (votes.length) { await api.claimVotes(votes); clearLocalVotes(); }
 */
export { clearLocalVotes, readLocalVotes, saveLocalVote, STORAGE_KEY } from "./storage";
export { useVoteDeck } from "./useVoteDeck";
export type { VoteNotice } from "./useVoteDeck";
