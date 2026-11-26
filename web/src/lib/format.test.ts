import { describe, expect, it } from "vitest";
import { formatDate, safeHref } from "./format";

const NOW = Date.parse("2026-11-26T12:00:00Z");
const ago = (ms: number) => new Date(NOW - ms).toISOString();

describe("formatDate", () => {
  it("moins d'une minute : « à l’instant »", () => {
    expect(formatDate(ago(30_000), NOW)).toBe("à l’instant");
  });
  it("heures et minutes en relatif", () => {
    expect(formatDate(ago(3 * 3_600_000), NOW)).toBe("il y a 3 heures");
    expect(formatDate(ago(5 * 60_000), NOW)).toBe("il y a 5 minutes");
  });
  it("une semaine ou plus : date complète", () => {
    expect(formatDate(ago(7 * 86_400_000), NOW)).toBe("19 novembre 2026");
    expect(formatDate(ago(6 * 86_400_000), NOW)).toMatch(/il y a 6 jours/);
  });
  it("date future : date complète", () => {
    expect(formatDate(new Date(NOW + 3_600_000).toISOString(), NOW)).toBe("26 novembre 2026");
  });
  it("date invalide : chaîne vide", () => {
    expect(formatDate("pas une date", NOW)).toBe("");
  });
});

describe("safeHref", () => {
  it("accepte http et https", () => {
    expect(safeHref("https://example.org/a")).toBe("https://example.org/a");
    expect(safeHref("http://example.org/")).toBe("http://example.org/");
  });
  it("refuse les autres schémas et les URL invalides", () => {
    expect(safeHref("javascript:alert(1)")).toBeUndefined();
    expect(safeHref("data:text/html,x")).toBeUndefined();
    expect(safeHref("ftp://example.org")).toBeUndefined();
    expect(safeHref("/relatif")).toBeUndefined();
  });
});
