import { clearDraft, loadDraft, saveDraft, type Draft } from "./draft";

/** Brouillon local partagé (useSyncExternalStore) : lu une fois, puis tenu en mémoire et écrit dans localStorage. */
let state: Draft = loadDraft();
const listeners = new Set<() => void>();

export const draftStore = {
  get: () => state,
  subscribe(listener: () => void) {
    listeners.add(listener);
    return () => void listeners.delete(listener);
  },
  set(next: Draft) {
    state = next;
    saveDraft(next);
    listeners.forEach((l) => l());
  },
  clear() {
    state = { editionDate: null, ids: [] };
    clearDraft();
    listeners.forEach((l) => l());
  },
  /** Pour les tests : relit le stockage. */
  reload() {
    state = loadDraft();
    listeners.forEach((l) => l());
  },
};
