/** Clé du stockage local des votes anonymes de la V1 (supprimée avec le vote). */
export const LEGACY_VOTES_KEY = "citizen-news:anonymous-votes:v1";

/** Supprime l'ancienne clé s'il en reste une. Jamais d'exception (stockage indisponible, mode privé). */
export function purgeLegacyVotes(): void {
  try {
    window.localStorage.removeItem(LEGACY_VOTES_KEY);
  } catch {
    /* stockage indisponible : rien à purger */
  }
}
