import { afterEach, describe, expect, it, vi } from "vitest";
import { LEGACY_VOTES_KEY, purgeLegacyVotes } from "./legacy";

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("purgeLegacyVotes", () => {
  it("supprime l'ancienne clé et laisse les autres", () => {
    localStorage.setItem(LEGACY_VOTES_KEY, "[]");
    localStorage.setItem("autre", "1");
    purgeLegacyVotes();
    expect(localStorage.getItem(LEGACY_VOTES_KEY)).toBeNull();
    expect(localStorage.getItem("autre")).toBe("1");
  });

  it("ne lève rien si le stockage est indisponible", () => {
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });
    expect(() => purgeLegacyVotes()).not.toThrow();
  });
});
