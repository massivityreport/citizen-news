import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useLocation } from "react-router-dom";
import { AppRoutes } from "../../App";
import type { AdminTopicDetail, AdminTopicRow, Page } from "../../api/types";
import { renderWithProviders } from "../../test/utils";
import { res, stubFetch, type Handler } from "../../test/api-stub";

afterEach(() => vi.unstubAllGlobals());

function Where() {
  const l = useLocation();
  return <output data-testid="where">{l.pathname + l.search}</output>;
}
const open = (route: string) =>
  renderWithProviders(
    <>
      <AppRoutes />
      <Where />
    </>,
    route,
  );
const where = () => screen.getByTestId("where").textContent;
const ME: Record<string, Handler> = { "GET /api/admin/me": () => res(200, { authenticated: true }) };

const row = (id: number, over: Partial<AdminTopicRow> = {}): AdminTopicRow => ({
  id, title: `Sujet ${id}`, article_count: 4, source_count: 3, updated_at: "2026-11-26T08:00:00Z", approvals: 12, ...over,
});
const list = (items: AdminTopicRow[], total = items.length, page = 1): Page<AdminTopicRow> => ({ items, total, page, page_size: 50 });

describe("onglet Sujets", () => {
  it("liste : articles, médias, mise à jour, approbations, lien vers le détail, aucun vocabulaire de vote", async () => {
    stubFetch({ ...ME, "GET /api/admin/topics": () => res(200, list([row(1), row(2, { approvals: 0 })])) });
    open("/admin/sujets");
    const table = await screen.findByRole("table", { name: /Sujets : 2 au total/ });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(within(rows[0]).getByRole("link", { name: "Sujet 1" })).toHaveAttribute("href", "/admin/sujets/1");
    const cells = within(rows[0]).getAllByRole("cell").map((c) => c.textContent);
    expect([cells[0], cells[1], cells[3]]).toEqual(["4", "3", "12"]);
    expect(within(rows[1]).getAllByRole("cell")[3]).toHaveTextContent("0");
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent?.replace(/[▲▼↕\s]+$/, ""))).toEqual([
      "Titre", "Articles", "Médias", "Mise à jour", "Approbations",
    ]);
    expect(document.body.textContent).not.toMatch(/vote|vague|état/i);
    expect(screen.queryByLabelText("État")).not.toBeInTheDocument();
  });

  it("tri (défaut : approbations décroissant) et page dans l’URL, sans filtre d’état", async () => {
    const calls: URLSearchParams[] = [];
    stubFetch({
      ...ME,
      "GET /api/admin/topics": (_i, url) => {
        const q = new URLSearchParams(url.split("?")[1] ?? "");
        calls.push(q);
        return res(200, list([row(1)], 120, Number(q.get("page"))));
      },
    });
    open("/admin/sujets");
    await screen.findByRole("table");
    const last = () => calls[calls.length - 1];
    expect(Object.fromEntries(last())).toEqual({ page: "1", sort: "approvals", order: "desc" });
    expect(screen.getByRole("columnheader", { name: /Approbations/ })).toHaveAttribute("aria-sort", "descending");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Titre/ }));
    await waitFor(() => expect(last().get("sort")).toBe("title"));
    expect(last().get("order")).toBe("asc");
    await user.click(screen.getByRole("button", { name: /Mise à jour/ }));
    await waitFor(() => expect(last().get("sort")).toBe("updated"));
    expect(last().get("order")).toBe("desc");
    await user.click(screen.getByRole("button", { name: "Suivant" }));
    await waitFor(() => expect(last().get("page")).toBe("2"));
    expect(where()).toBe("/admin/sujets?sort=updated&order=desc&page=2");
    expect(last().has("state")).toBe(false);
    expect(await screen.findByText("Page 2 sur 3 — 120 sujets")).toBeInTheDocument();
  });

  it("un ancien tri (votes) dans l’URL retombe sur le tri par défaut", async () => {
    const calls: URLSearchParams[] = [];
    stubFetch({ ...ME, "GET /api/admin/topics": (_i, url) => (calls.push(new URLSearchParams(url.split("?")[1])), res(200, list([row(1)]))) });
    open("/admin/sujets?sort=votes");
    await screen.findByRole("table");
    expect(calls[0].get("sort")).toBe("approvals");
  });

  it("vide et erreur", async () => {
    stubFetch({ ...ME, "GET /api/admin/topics": () => res(200, list([])) });
    const { unmount } = open("/admin/sujets");
    expect(await screen.findByText("Aucun sujet pour le moment.")).toBeInTheDocument();
    unmount();
    stubFetch({ ...ME, "GET /api/admin/topics": () => res(500, {}) });
    open("/admin/sujets");
    expect(await screen.findByRole("alert")).toHaveTextContent("Impossible de charger les sujets");
  });
});

const detail = (over: Partial<AdminTopicDetail> = {}): AdminTopicDetail => ({
  id: 7, title: "Retraites", summary: "Le débat reprend.",
  first_seen_at: "2026-11-01T08:00:00Z", updated_at: "2026-11-26T08:00:00Z",
  article_count: 2, source_count: 2, approvals: 14,
  history: [
    { date: "2026-11-26", approvals: 80, proportion: 0.667, rank: 1 },
    { date: "2026-11-25", approvals: 9, rank: null },
  ],
  articles: [
    { id: 1, title: "Article A", url: "https://a.example/1", source: { id: 1, name: "Alpha", active: true }, published_at: "2026-11-25T10:00:00Z" },
    { id: 2, title: "Article B", url: "https://b.example/2", source: { id: 2, name: "Beta", active: false }, published_at: null },
  ],
  articles_truncated: false,
  ...over,
});

describe("détail d’un sujet", () => {
  it("approbations en cours, historique par édition, articles", async () => {
    stubFetch({ ...ME, "GET /api/admin/topics/7": () => res(200, detail()) });
    open("/admin/sujets/7");
    expect(await screen.findByRole("heading", { level: 1, name: "Retraites" })).toBeInTheDocument();
    const stat = (label: string) => screen.getByText(label, { selector: "dt" }).parentElement!;
    expect(stat("Approbations (édition en cours)")).toHaveTextContent("14");
    expect(stat("Médias distincts")).toHaveTextContent("2");
    const history = screen.getByRole("table", { name: /Approbations par édition publiée/ });
    const rows = within(history).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByRole("link")).toHaveAttribute("href", "/admin/editions/2026-11-26");
    expect(rows[0]).toHaveTextContent("80");
    expect(rows[0]).toHaveTextContent("67 %");
    expect(rows[1]).toHaveTextContent("—");
    const articles = screen.getByRole("table", { name: /Articles du sujet \(2\)/ });
    expect(within(articles).getByRole("link", { name: "Article A" })).toHaveAttribute("href", "https://a.example/1");
    expect(within(articles).getByText("source désactivée")).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/vote|soutien|vague/i);
  });

  it("sujet jamais publié et sans article", async () => {
    stubFetch({ ...ME, "GET /api/admin/topics/7": () => res(200, detail({ approvals: 0, history: [], articles: [] })) });
    open("/admin/sujets/7");
    await screen.findByRole("heading", { level: 1, name: "Retraites" });
    expect(screen.getByText("Ce sujet n’a figuré dans aucune édition publiée.")).toBeInTheDocument();
    expect(screen.getByText("Aucun article.")).toBeInTheDocument();
  });

  it("sujet inconnu (404) : message et lien de retour", async () => {
    stubFetch({ ...ME, "GET /api/admin/topics/9": () => res(404, { detail: "Sujet introuvable." }) });
    open("/admin/sujets/9");
    expect(await screen.findByRole("heading", { level: 1, name: "Sujet introuvable" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "← Tous les sujets" })).toHaveAttribute("href", "/admin/sujets");
  });

  it("erreur serveur : alerte", async () => {
    stubFetch({ ...ME, "GET /api/admin/topics/7": () => res(500, {}) });
    open("/admin/sujets/7");
    expect(await screen.findByRole("alert")).toHaveTextContent("Impossible de charger le sujet");
  });
});
