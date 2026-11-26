import type { Vote, VoteChoice } from "../api/types";

/** Clé versionnée : on ne stocke que {topic_id, choice}, rien d'autre. */
export const STORAGE_KEY = "citizen-news:anonymous-votes:v1";

const CHOICES: readonly VoteChoice[] = ["more", "not_priority", "unknown"];

function isVote(v: unknown): v is Vote {
  if (typeof v !== "object" || v === null) return false;
  const { topic_id, choice } = v as Record<string, unknown>;
  return Number.isInteger(topic_id) && CHOICES.includes(choice as VoteChoice);
}

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

/** Votes anonymes conservés dans le navigateur. Jamais d'exception : [] si indisponible ou corrompu. */
export function readLocalVotes(): Vote[] {
  try {
    const raw = storage()?.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    const byTopic = new Map<number, Vote>();
    for (const v of parsed) if (isVote(v)) byTopic.set(v.topic_id, { topic_id: v.topic_id, choice: v.choice });
    return [...byTopic.values()];
  } catch {
    return [];
  }
}

/** Enregistre un vote anonyme (le dernier vote d'un sujet remplace le précédent). Renvoie false si le stockage échoue. */
export function saveLocalVote(vote: Vote): boolean {
  try {
    const s = storage();
    if (!s) return false;
    const next = readLocalVotes().filter((v) => v.topic_id !== vote.topic_id);
    next.push({ topic_id: vote.topic_id, choice: vote.choice });
    s.setItem(STORAGE_KEY, JSON.stringify(next));
    return true;
  } catch {
    return false;
  }
}

/** Vide la liste locale (à appeler après un POST /api/votes/claim réussi). */
export function clearLocalVotes(): void {
  try {
    storage()?.removeItem(STORAGE_KEY);
  } catch {
    /* stockage indisponible : rien à vider */
  }
}
