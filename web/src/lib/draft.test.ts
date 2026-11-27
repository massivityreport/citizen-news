import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DRAFT_KEY, cleanIds, clearDraft, loadDraft, saveDraft } from "./draft";

beforeEach(() => window.localStorage.clear());
afterEach(() => vi.restoreAllMocks());

describe("brouillon local", () => {
  it("valide, dédoublonne et plafonne à dix", () => {
    expect(cleanIds([3, 3, "4", -1, 0, 1.5, null, 5])).toEqual([3, 5]);
    expect(cleanIds(Array.from({ length: 15 }, (_, i) => i + 1))).toHaveLength(10);
    expect(cleanIds("pas un tableau")).toEqual([]);
  });

  it("garde et relit les ids avec l'édition", () => {
    saveDraft({ editionDate: "2026-11-27", ids: [4, 9] });
    expect(loadDraft()).toEqual({ editionDate: "2026-11-27", ids: [4, 9] });
  });

  it("nettoie un contenu corrompu au chargement", () => {
    window.localStorage.setItem(DRAFT_KEY, JSON.stringify({ v: 1, ids: [1, 1, "x", 2, Number.MAX_VALUE] }));
    expect(loadDraft().ids).toEqual([1, 2]);
    window.localStorage.setItem(DRAFT_KEY, "{pas du json");
    expect(loadDraft().ids).toEqual([]);
    window.localStorage.setItem(DRAFT_KEY, JSON.stringify({ v: 2, ids: [1] }));
    expect(loadDraft().ids).toEqual([]);
  });

  it("une une vide supprime la clé", () => {
    saveDraft({ editionDate: null, ids: [1] });
    clearDraft();
    expect(window.localStorage.getItem(DRAFT_KEY)).toBeNull();
  });

  it("tolère un stockage indisponible", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("bloqué");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("bloqué");
    });
    expect(loadDraft().ids).toEqual([]);
    expect(() => saveDraft({ editionDate: null, ids: [1] })).not.toThrow();
    expect(() => clearDraft()).not.toThrow();
  });
});
