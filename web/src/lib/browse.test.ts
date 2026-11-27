import { beforeEach, describe, expect, it } from "vitest";
import { getSeed, getSeen, makeSeed, markSeen, orderRandom, resetBrowse } from "./browse";

beforeEach(() => {
  window.sessionStorage.clear();
  resetBrowse();
});

describe("graine de session", () => {
  it("fait 16 caractères ou plus dans [A-Za-z0-9_-]", () => {
    for (let i = 0; i < 20; i++) expect(makeSeed()).toMatch(/^[A-Za-z0-9_-]{16,64}$/);
    expect(makeSeed()).not.toBe(makeSeed());
  });

  it("est stable entre appels (rechargement) et nouvelle pour une nouvelle session", () => {
    const a = getSeed();
    expect(getSeed()).toBe(a);
    window.sessionStorage.clear(); // nouvelle session de navigation
    resetBrowse();
    expect(getSeed()).not.toBe(a);
  });

  it("ignore une graine invalide stockée", () => {
    window.sessionStorage.setItem("citizen-news:browse:v1", JSON.stringify({ seed: "court", seen: [1] }));
    resetBrowse();
    expect(getSeed()).toMatch(/^[A-Za-z0-9_-]{16,}$/);
  });
});

describe("sujets vus", () => {
  it("garde l'ordre de passage sans doublon, stable au rechargement", () => {
    markSeen(5);
    markSeen(2);
    markSeen(5);
    expect(getSeen()).toEqual([5, 2]);
    resetBrowse(); // rechargement : relu depuis sessionStorage
    expect(getSeen()).toEqual([5, 2]);
  });
});

describe("orderRandom", () => {
  const items = [{ id: 1 }, { id: 2 }, { id: 3 }, { id: 4 }];

  it("vus d'abord dans l'ordre de passage, puis non vus dans l'ordre du serveur, sans répétition", () => {
    const out = orderRandom(items, [3, 1]).map((t) => t.id);
    expect(out).toEqual([3, 1, 2, 4]);
    expect(new Set(out).size).toBe(4);
  });

  it("un sujet apparu en cours de journée s'insère parmi les non vus ; un sujet disparu est ignoré", () => {
    const later = [{ id: 1 }, { id: 9 }, { id: 3 }, { id: 4 }];
    expect(orderRandom(later, [3, 2, 1]).map((t) => t.id)).toEqual([3, 1, 9, 4]);
  });
});
