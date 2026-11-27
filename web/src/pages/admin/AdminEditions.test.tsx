import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AppRoutes } from "../../App";
import type { Edition } from "../../api/types";
import { renderWithProviders } from "../../test/utils";
import { res, stubFetch, type Handler } from "../../test/api-stub";

afterEach(() => vi.unstubAllGlobals());

const ME: Record<string, Handler> = { "GET /api/admin/me": () => res(200, { authenticated: true }) };
const open = (route: string) => renderWithProviders(<AppRoutes />, route);

const edition = (over: Partial<Edition> = {}): Edition => ({
  date: "2026-11-26",
  published_at: "2026-11-26T16:00:00Z",
  participants: 120,
  topics: [
    { rank: 1, topic_id: 12, title: "Retraites", summary: "", sources: [], source_count: 5, article_count: 9, approvals: 80, proportion: 0.667, image_url: null },
    { rank: 2, topic_id: null, title: "Sujet supprimé", summary: "", sources: [], source_count: 3, article_count: 4, approvals: 30, proportion: 0.25, image_url: null },
  ],
  ...over,
});

describe("onglet Éditions", () => {
  it("liste : date, publication, participants, sujets ; entrée de menu", async () => {
    stubFetch({
      ...ME,
      "GET /api/admin/editions": () =>
        res(200, { items: [{ date: "2026-11-26", published_at: "2026-11-26T16:00:00Z", participants: 120, topic_count: 10 }], total: 1, page: 1, page_size: 50 }),
    });
    open("/admin/editions");
    const table = await screen.findByRole("table", { name: /Éditions publiées : 1, page 1/ });
    const row = within(table).getAllByRole("row")[1];
    expect(within(row).getByRole("link", { name: "26 novembre 2026" })).toHaveAttribute("href", "/admin/editions/2026-11-26");
    expect(within(row).getAllByRole("cell").map((c) => c.textContent).slice(1)).toEqual(["120", "10"]);
    expect(within(screen.getByRole("navigation", { name: /administration/i })).getByRole("link", { name: "Éditions" })).toHaveAttribute(
      "href",
      "/admin/editions",
    );
  });

  it("liste vide et erreur", async () => {
    stubFetch({ ...ME, "GET /api/admin/editions": () => res(200, { items: [], total: 0, page: 1, page_size: 50 }) });
    const { unmount } = open("/admin/editions");
    expect(await screen.findByText("Aucune édition n’a encore été publiée.")).toBeInTheDocument();
    unmount();
    stubFetch({ ...ME, "GET /api/admin/editions": () => res(500, {}) });
    open("/admin/editions");
    expect(await screen.findByRole("alert")).toHaveTextContent("Impossible de charger les éditions");
  });

  it("pagination : page et page_size dans l’appel, jamais limit", async () => {
    const calls: URLSearchParams[] = [];
    const items = [{ date: "2026-11-26", published_at: "2026-11-26T16:00:00Z", participants: 1, topic_count: 1 }];
    stubFetch({
      ...ME,
      "GET /api/admin/editions": (_i, url) => {
        const q = new URLSearchParams(url.split("?")[1] ?? "");
        calls.push(q);
        return res(200, { items, total: 120, page: Number(q.get("page")), page_size: 50 });
      },
    });
    open("/admin/editions");
    await screen.findByRole("table");
    expect(calls[0].get("page")).toBe("1");
    expect(calls[0].has("limit")).toBe(false);
    await userEvent.click(screen.getByRole("button", { name: "Suivant" }));
    expect(await screen.findByText("Page 2 sur 3 — 120 éditions")).toBeInTheDocument();
    expect(calls[calls.length - 1].get("page")).toBe("2");
  });

  it("détail : approbations, proportion, lien vers le sujet (sauf sujet supprimé)", async () => {
    stubFetch({ ...ME, "GET /api/admin/editions/2026-11-26": () => res(200, edition()) });
    open("/admin/editions/2026-11-26");
    expect(await screen.findByRole("heading", { level: 1, name: "Édition du 26 novembre 2026" })).toBeInTheDocument();
    expect(screen.getByText("Participants", { selector: "dt" }).parentElement).toHaveTextContent("120");
    const rows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    expect(within(rows[0]).getByRole("link", { name: "Retraites" })).toHaveAttribute("href", "/admin/sujets/12");
    expect(rows[0]).toHaveTextContent("80");
    expect(rows[0]).toHaveTextContent("67 %");
    expect(within(rows[1]).queryByRole("link")).not.toBeInTheDocument();
  });

  it("détail : édition sans participants, introuvable (404)", async () => {
    stubFetch({ ...ME, "GET /api/admin/editions/2026-11-26": () => res(200, edition({ participants: 0, topics: [] })) });
    const { unmount } = open("/admin/editions/2026-11-26");
    expect(await screen.findByText("Aucun sujet retenu : aucune approbation.")).toBeInTheDocument();
    unmount();
    stubFetch({ ...ME, "GET /api/admin/editions/2026-01-01": () => res(404, { detail: "Édition introuvable." }) });
    open("/admin/editions/2026-01-01");
    expect(await screen.findByRole("heading", { level: 1, name: "Édition introuvable" })).toBeInTheDocument();
  });

  it("détail : erreur 500, h1 et titre de document conservés", async () => {
    stubFetch({ ...ME, "GET /api/admin/editions/2026-11-26": () => res(500, {}) });
    open("/admin/editions/2026-11-26");
    expect(await screen.findByRole("alert")).toHaveTextContent("Impossible de charger l’édition");
    expect(screen.getByRole("heading", { level: 1, name: "Édition" })).toBeInTheDocument();
    expect(document.title).toBe("Édition — Citizen News");
  });

  it("détail : chargement avec un h1", async () => {
    stubFetch({ ...ME, "GET /api/admin/editions/2026-11-26": () => new Promise<Response>(() => {}) });
    open("/admin/editions/2026-11-26");
    expect(await screen.findByText("Chargement de l’édition…")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Édition" })).toBeInTheDocument();
  });

  it("détail : date invalide, aucun appel à l’API", async () => {
    const fn = stubFetch({ ...ME });
    open("/admin/editions/abc");
    expect(await screen.findByRole("heading", { level: 1, name: "Édition introuvable" })).toBeInTheDocument();
    expect(document.title).toBe("Édition introuvable — Citizen News");
    expect(fn.mock.calls.some(([u]) => String(u).includes("/admin/editions/"))).toBe(false);
  });
});
