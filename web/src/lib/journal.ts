import type { RecentAction } from "../api/types";

/**
 * Journal du parcours récent : les 20 dernières actions de la visite (page ouverte, sujet ajouté ou retiré de la une,
 * connexion), gardées dans sessionStorage — donc pour la durée de la visite seulement. Aucun appel réseau ici : le
 * parcours ne quitte le navigateur que joint à un avis, si l'utilisateur le veut.
 */
export const MAX_ACTIONS = 20;
const KEY = "cn.journey";
const TYPES = new Set(["page", "topic_added", "topic_removed", "login"]);

export type ActionInput = Omit<RecentAction, "at">;

function valid(a: unknown): a is RecentAction {
  return typeof a === "object" && a !== null && TYPES.has((a as RecentAction).type) && typeof (a as RecentAction).at === "string";
}

function load(): RecentAction[] {
  try {
    const parsed: unknown = JSON.parse(window.sessionStorage.getItem(KEY) ?? "[]");
    return Array.isArray(parsed) ? parsed.filter(valid).slice(-MAX_ACTIONS) : [];
  } catch {
    return [];
  }
}

let actions: RecentAction[] = load();

export const journal = {
  record(action: ActionInput) {
    actions = [...actions, { ...action, at: new Date().toISOString() }].slice(-MAX_ACTIONS);
    try {
      window.sessionStorage.setItem(KEY, JSON.stringify(actions));
    } catch {
      /* stockage indisponible : le journal reste en mémoire pour la visite */
    }
  },
  get: (): RecentAction[] => actions,
  /** Relit le stockage (tests : nouvelle visite). */
  reload() {
    actions = load();
  },
  /** Oublie tout (tests). */
  reset() {
    actions = [];
    try {
      window.sessionStorage.removeItem(KEY);
    } catch {
      /* rien à effacer */
    }
  },
};
