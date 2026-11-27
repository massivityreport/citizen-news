import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderApp } from "../test/utils";
import { res, stubFetch } from "../test/api-stub";
import type { Edition } from "../api/types";

const edition: Edition = {
  date: "2026-11-26",
  published_at: "2026-11-26T16:00:00Z",
  participants: 120,
  topics: [
    {
      rank: 1, topic_id: 12, title: "Pénurie de médecins", summary: "Des délais.", sources: [],
      source_count: 5, article_count: 9, approvals: 80, proportion: 0.667, image_url: null,
    },
  ],
};

const base = { "GET /api/me": () => res(401, {}) };

afterEach(() => {
  vi.unstubAllGlobals();
  Reflect.deleteProperty(navigator, "share");
  Reflect.deleteProperty(navigator, "clipboard");
});

function setNav(key: "share" | "clipboard", value: unknown) {
  Object.defineProperty(navigator, key, { value, configurable: true });
}

describe("Permalien /une/:date", () => {
  it("affiche l'édition demandée, sans lien permanent redondant", async () => {
    const fn = stubFetch({ ...base, "GET /api/editions/2026-11-26": () => res(200, edition) });
    renderApp("/une/2026-11-26");
    expect(await screen.findByRole("heading", { level: 1, name: "La une du 26 novembre 2026" })).toBeInTheDocument();
    expect(await screen.findByRole("article", { name: "Pénurie de médecins" })).toBeInTheDocument();
    expect(document.title).toBe("La une du 26 novembre 2026 — Citizen News");
    expect(screen.queryByText(/Lien permanent/)).toBeNull();
    expect(fn.mock.calls.some(([u]) => u === "/api/editions/2026-11-26")).toBe(true);
  });

  it("404 : page « Édition introuvable »", async () => {
    stubFetch({ ...base, "GET /api/editions/2026-01-01": () => res(404, { detail: "Édition introuvable." }) });
    renderApp("/une/2026-01-01");
    expect(await screen.findByRole("heading", { level: 1, name: "Édition introuvable" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Voir toutes les unes/ })).toHaveAttribute("href", "/archives");
    expect(document.title).toBe("Édition introuvable — Citizen News");
  });

  it("date mal formée : introuvable, sans appel à l'API", async () => {
    const fn = stubFetch(base);
    renderApp("/une/hier");
    expect(await screen.findByRole("heading", { level: 1, name: "Édition introuvable" })).toBeInTheDocument();
    expect(fn.mock.calls.some(([u]) => String(u).startsWith("/api/editions"))).toBe(false);
  });

  it("erreur serveur : message et réessai (pas « introuvable »)", async () => {
    stubFetch({ ...base, "GET /api/editions/2026-11-26": () => res(500, {}) });
    renderApp("/une/2026-11-26");
    expect(await screen.findByRole("alert")).toHaveTextContent(/Impossible de charger/);
    expect(screen.queryByText("Édition introuvable")).toBeNull();
  });
});

describe("Partager", () => {
  const open = async () => {
    stubFetch({ ...base, "GET /api/editions/2026-11-26": () => res(200, edition) });
    renderApp("/une/2026-11-26");
    return screen.findByRole("button", { name: "Partager cette une" });
  };

  it("Web Share API quand elle existe", async () => {
    const share = vi.fn().mockResolvedValue(undefined);
    setNav("share", share);
    await userEvent.click(await open());
    expect(share).toHaveBeenCalledWith({
      title: "La une citoyenne du 26 novembre 2026",
      url: `${window.location.origin}/une/2026-11-26`,
    });
    expect(await screen.findByText(/Merci d’avoir partagé/)).toBeInTheDocument();
  });

  it("sinon copie le lien avec un retour visuel", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    setNav("clipboard", { writeText });
    await userEvent.click(await open());
    expect(writeText).toHaveBeenCalledWith(`${window.location.origin}/une/2026-11-26`);
    expect(await screen.findByText("Lien copié ✓")).toBeInTheDocument();
  });

  it("partage annulé : aucun message, pas de copie", async () => {
    const writeText = vi.fn();
    setNav("clipboard", { writeText });
    setNav("share", vi.fn().mockRejectedValue(new DOMException("annulé", "AbortError")));
    await userEvent.click(await open());
    expect(writeText).not.toHaveBeenCalled();
    expect(screen.queryByText(/copié|partagé/)).toBeNull();
  });

  it("copie impossible : affiche le lien à copier à la main", async () => {
    setNav("clipboard", { writeText: vi.fn().mockRejectedValue(new Error("refusé")) });
    await userEvent.click(await open());
    await waitFor(() => expect(screen.getByText(/Copie impossible/)).toHaveTextContent("/une/2026-11-26"));
  });
});

describe("Archives", () => {
  it("liste les éditions avec leurs permaliens", async () => {
    const fn = stubFetch({
      ...base,
      "GET /api/editions": () =>
        res(200, {
          items: [
            { date: "2026-11-26", published_at: "2026-11-26T16:00:00Z", participants: 120, topic_count: 10 },
            { date: "2026-11-25", published_at: "2026-11-25T16:00:00Z", participants: 0, topic_count: 0 },
          ],
        }),
    });
    renderApp("/archives");
    const link = await screen.findByRole("link", { name: "26 novembre 2026" });
    expect(link).toHaveAttribute("href", "/une/2026-11-26");
    const item = link.closest("li")!;
    expect(within(item).getByText(/120 participants · 10 sujets/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "25 novembre 2026" })).toHaveAttribute("href", "/une/2026-11-25");
    expect(fn.mock.calls.some(([u]) => u === "/api/editions?limit=30")).toBe(true);
  });

  it("aucune édition : message", async () => {
    stubFetch({ ...base, "GET /api/editions": () => res(200, { items: [] }) });
    renderApp("/archives");
    expect(await screen.findByText(/Aucune une n’a encore été publiée/)).toBeInTheDocument();
  });

  it("erreur : message et réessai", async () => {
    stubFetch({ ...base, "GET /api/editions": () => res(500, {}) });
    renderApp("/archives");
    expect(await screen.findByRole("alert")).toHaveTextContent(/archives/);
  });
});
