/**
 * Session de navigation : graine du tirage « Au hasard » et sujets déjà vus, dans sessionStorage
 * (stables entre rechargements, nouveaux à la prochaine session). Repli en mémoire si le stockage manque.
 */
const KEY = "citizen-news:browse:v1";
const ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-";
const SEED_RE = /^[A-Za-z0-9_-]{16,64}$/;
const MAX_SEEN = 500;

interface Browse {
  seed: string;
  seen: number[];
}

let state: Browse | null = null;
const listeners = new Set<() => void>();

export function makeSeed(length = 24): string {
  const bytes = new Uint8Array(length);
  if (globalThis.crypto?.getRandomValues) globalThis.crypto.getRandomValues(bytes);
  else for (let i = 0; i < length; i++) bytes[i] = Math.floor(Math.random() * 256);
  // 64 symboles : un octet modulo 64, sans biais
  return Array.from(bytes, (b) => ALPHABET[b % 64]).join("");
}

function read(): Browse | null {
  try {
    const raw = window.sessionStorage.getItem(KEY);
    if (!raw) return null;
    const d = JSON.parse(raw) as { seed?: unknown; seen?: unknown } | null;
    if (!d || typeof d.seed !== "string" || !SEED_RE.test(d.seed)) return null;
    const seen = Array.isArray(d.seen)
      ? [...new Set(d.seen.filter((x): x is number => Number.isSafeInteger(x) && (x as number) > 0))]
      : [];
    return { seed: d.seed, seen };
  } catch {
    return null; // illisible ou stockage indisponible : on repart d'une session neuve, gardée en mémoire
  }
}

function write(b: Browse) {
  state = b;
  try {
    window.sessionStorage.setItem(KEY, JSON.stringify(b));
  } catch {
    /* mémoire seulement */
  }
}

/** Lu une fois depuis le stockage, puis tenu en mémoire (et réécrit à chaque changement). */
function current(): Browse {
  if (!state) {
    state = read();
    if (!state) write({ seed: makeSeed(), seen: [] });
  }
  return state!;
}

/** Pour les tests : oublie l'état en mémoire (la « nouvelle session »). */
export function resetBrowse() {
  state = null;
  listeners.forEach((l) => l());
}

export function subscribeSeen(listener: () => void): () => void {
  listeners.add(listener);
  return () => void listeners.delete(listener);
}

export function getSeed(): string {
  return current().seed;
}

/** Même référence tant que la liste ne change pas (useSyncExternalStore). */
export function getSeen(): number[] {
  return current().seen;
}

/** Note un sujet comme vu (à la fin, dans l'ordre de passage). */
export function markSeen(id: number): void {
  const b = current();
  if (b.seen.includes(id)) return;
  write({ ...b, seen: [...b.seen, id].slice(-MAX_SEEN) });
  listeners.forEach((l) => l());
}

/** Vus d'abord (dans l'ordre de passage, ceux qui sont encore au bassin), puis non vus dans l'ordre du serveur. */
export function orderRandom<T extends { id: number }>(items: T[], seen: number[]): T[] {
  const byId = new Map(items.map((t) => [t.id, t]));
  const seenSet = new Set<number>();
  const first: T[] = [];
  for (const id of seen) {
    const t = byId.get(id);
    if (t && !seenSet.has(id)) {
      seenSet.add(id);
      first.push(t);
    }
  }
  return [...first, ...items.filter((t) => !seenSet.has(t.id))];
}
