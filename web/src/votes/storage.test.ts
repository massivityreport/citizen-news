import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { clearLocalVotes, readLocalVotes, saveLocalVote, STORAGE_KEY } from "./storage";

beforeEach(() => localStorage.clear());
afterEach(() => vi.restoreAllMocks());

describe("votes locaux", () => {
  it("liste vide par défaut", () => {
    expect(readLocalVotes()).toEqual([]);
  });

  it("ignore les entrées invalides d'un tableau valide", () => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify([
        { topic_id: 1, choice: "more", extra: "x" },
        { topic_id: "2", choice: "more" },
        { topic_id: 3, choice: "autre" },
        { topic_id: 1.5, choice: "unknown" },
        null,
        "texte",
        { topic_id: 4, choice: "not_priority" },
      ]),
    );
    expect(readLocalVotes()).toEqual([
      { topic_id: 1, choice: "more" },
      { topic_id: 4, choice: "not_priority" },
    ]);
  });

  it("ignore un contenu qui n'est pas un tableau", () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ topic_id: 1, choice: "more" }));
    expect(readLocalVotes()).toEqual([]);
  });

  it("dédoublonne par topic_id : le dernier vote remplace", () => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify([
        { topic_id: 1, choice: "more" },
        { topic_id: 1, choice: "unknown" },
      ]),
    );
    expect(readLocalVotes()).toEqual([{ topic_id: 1, choice: "unknown" }]);
    expect(saveLocalVote({ topic_id: 1, choice: "not_priority" })).toBe(true);
    expect(readLocalVotes()).toEqual([{ topic_id: 1, choice: "not_priority" }]);
  });

  it("clearLocalVotes vide la liste", () => {
    saveLocalVote({ topic_id: 1, choice: "more" });
    clearLocalVotes();
    expect(readLocalVotes()).toEqual([]);
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("ne lève jamais si le stockage est indisponible", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("quota");
    });
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new Error("denied");
    });
    expect(saveLocalVote({ topic_id: 1, choice: "more" })).toBe(false);
    expect(() => clearLocalVotes()).not.toThrow();
  });
});
