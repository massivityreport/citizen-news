/** Brouillon de une sans compte : au plus dix identifiants de sujets, dans le stockage local du navigateur. */
export const DRAFT_KEY = "citizen-news:draft:v2";
export const MAX_PLACES = 10;

export interface Draft {
  /** Édition visée (AAAA-MM-JJ) ; null tant qu'on ne la connaît pas. */
  editionDate: string | null;
  ids: number[];
}

/** Garde les entiers > 0, sans doublon, dix au plus (les premiers). */
export function cleanIds(raw: unknown): number[] {
  if (!Array.isArray(raw)) return [];
  const out: number[] = [];
  for (const v of raw) {
    if (typeof v === "number" && Number.isSafeInteger(v) && v > 0 && !out.includes(v)) out.push(v);
    if (out.length === MAX_PLACES) break;
  }
  return out;
}

export function loadDraft(): Draft {
  try {
    const raw = window.localStorage.getItem(DRAFT_KEY);
    if (!raw) return { editionDate: null, ids: [] };
    const data = JSON.parse(raw) as { v?: unknown; edition_date?: unknown; ids?: unknown } | null;
    if (!data || typeof data !== "object" || data.v !== 1) return { editionDate: null, ids: [] };
    return {
      editionDate: typeof data.edition_date === "string" ? data.edition_date : null,
      ids: cleanIds(data.ids),
    };
  } catch {
    return { editionDate: null, ids: [] };
  }
}

/** Jamais d'exception : un stockage indisponible laisse le brouillon en mémoire seulement. */
export function saveDraft(draft: Draft): void {
  try {
    if (draft.ids.length === 0) window.localStorage.removeItem(DRAFT_KEY);
    else
      window.localStorage.setItem(
        DRAFT_KEY,
        JSON.stringify({ v: 1, edition_date: draft.editionDate, ids: cleanIds(draft.ids) }),
      );
  } catch {
    /* stockage indisponible (mode privé, quota) */
  }
}

export function clearDraft(): void {
  saveDraft({ editionDate: null, ids: [] });
}
