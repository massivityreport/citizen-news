import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useLocation } from "react-router-dom";
import { AppRoutes } from "../../App";
import type { AdminTopicDetail, AdminTopicRow, AdminVote, Page } from "../../api/types";
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
  id, title: `Sujet ${id}`, state: "active", wave: 1, state_changed_at: "2026-11-02T08:00:00Z",
  article_count: 4, source_count: 3, vote_count: 12, image_url: null, ...over,
});
const list = (items: AdminTopicRow[], total = items.length, page = 1): Page<AdminTopicRow> => ({ items, total, page, page_size: 50 });

describe("onglet Sujets", () => {
  it("liste : agrégats, état en français, lien vers le détail", async () => {
    stubFetch({ ...ME, "GET /api/admin/topics": () => res(200, list([row(1), row(2, { state: "reserve", state_changed_at: null, vote_count: 0 })])) });
    open("/admin/sujets");
    const table = await screen.findByRole("table", { name: /Sujets : 2 au total/ });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(within(rows[0]).getByRole("link", { name: "Sujet 1" })).toHaveAttribute("href", "/admin/sujets/1");
    expect(rows[0]).toHaveTextContent("Actif");
    expect(rows[0]).toHaveTextContent("vague 1");
    expect(within(rows[0]).getAllByRole("cell").map((c) => c.textContent).slice(1, 4)).toEqual(["4", "3", "12"]);
    expect(rows[1]).toHaveTextContent("En réserve");
  });

  it("tri (défaut : votes décroissant), filtre d’état et page dans l’URL", async () => {
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
    expect(Object.fromEntries(last())).toEqual({ page: "1", sort: "votes", order: "desc" });
    expect(screen.getByRole("columnheader", { name: /Votes/ })).toHaveAttribute("aria-sort", "descending");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Titre/ }));
    await waitFor(() => expect(last().get("sort")).toBe("title"));
    expect(last().get("order")).toBe("asc");
    await user.selectOptions(screen.getByLabelText("État"), "reserve");
    await waitFor(() => expect(last().get("state")).toBe("reserve"));
    expect(where()).toBe("/admin/sujets?sort=title&order=asc&state=reserve");
    await user.click(screen.getByRole("button", { name: "Suivant" }));
    await waitFor(() => expect(last().get("page")).toBe("2"));
    expect(where()).toBe("/admin/sujets?sort=title&order=asc&state=reserve&page=2");
    expect(await screen.findByText("Page 2 sur 3 — 120 sujets")).toBeInTheDocument();
  });

  it("vide et erreur", async () => {
    stubFetch({ ...ME, "GET /api/admin/topics": () => res(200, list([])) });
    const { unmount } = open("/admin/sujets");
    expect(await screen.findByText("Aucun sujet ne correspond.")).toBeInTheDocument();
    unmount();
    stubFetch({ ...ME, "GET /api/admin/topics": () => res(500, {}) });
    open("/admin/sujets");
    expect(await screen.findByRole("alert")).toHaveTextContent("Impossible de charger les sujets");
  });
});

const detail = (over: Partial<AdminTopicDetail> = {}): AdminTopicDetail => ({
  id: 7, title: "Retraites", summary: "Le débat reprend.", state: "emerged", wave: 3,
  first_seen_at: "2026-11-01T08:00:00Z", updated_at: "2026-11-26T08:00:00Z",
  state_changed_at: "2026-11-20T09:30:00Z", evaluated_at: "2026-11-20T09:30:00Z",
  article_count: 2, source_count: 2,
  support: { score: 0.61234, level: "high", votes_count: 40 },
  front: { on_front: true, reason: { code: "strong_mobilisation", label: "Forte mobilisation" } },
  votes: {
    more: 30, not_priority: 6, unknown: 4, total: 40, voters: 40, first_vote_at: "2026-11-24T10:00:00Z",
    daily: [
      { date: "2026-11-24", more: 10, not_priority: 2, unknown: 0, total: 12 },
      { date: "2026-11-25", more: 0, not_priority: 0, unknown: 0, total: 0 },
      { date: "2026-11-26", more: 20, not_priority: 4, unknown: 4, total: 28 },
    ],
  },
  articles: [
    { id: 1, title: "Article A", url: "https://a.example/1", source: { id: 1, name: "Alpha", active: true }, published_at: "2026-11-25T10:00:00Z" },
    { id: 2, title: "Article B", url: "https://b.example/2", source: { id: 2, name: "Beta", active: false }, published_at: null },
  ],
  articles_truncated: false,
  ...over,
});
const votePage = (page: number, total: number): Page<AdminVote> => ({
  items: [
    { date: "2026-11-26T10:00:00Z", choice: "more", account_id: 100 + page },
    { date: "2026-11-26T09:00:00Z", choice: "not_priority", account_id: 200 + page },
  ],
  total, page, page_size: 50,
});

describe("détail d’un sujet", () => {
  it("statut, raison à la une, totaux, courbe, votes avec numéro de compte, articles", async () => {
    stubFetch({
      ...ME,
      "GET /api/admin/topics/7": () => res(200, detail()),
      "GET /api/admin/topics/7/votes": (_i, url) => res(200, votePage(Number(new URLSearchParams(url.split("?")[1]).get("page")), 120)),
    });
    open("/admin/sujets/7");
    expect(await screen.findByRole("heading", { level: 1, name: "Retraites" })).toBeInTheDocument();
    const stat = (label: string) => screen.getByText(label, { selector: "dt" }).parentElement!;
    expect(stat("État")).toHaveTextContent("Émergé");
    expect(stat("État")).toHaveTextContent("vague 3");
    expect(stat("Dernier changement d’état")).toHaveTextContent("Seul le dernier changement est conservé");
    expect(stat("Soutien")).toHaveTextContent("élevé");
    expect(stat("Soutien")).toHaveTextContent("score 0.61");
    expect(stat("À la une")).toHaveTextContent("Oui");
    expect(stat("À la une")).toHaveTextContent("Raison affichée : Forte mobilisation");
    expect(stat("Il faut en parler")).toHaveTextContent("30");
    expect(stat("Pas prioritaire")).toHaveTextContent("6");
    expect(stat("Je ne sais pas")).toHaveTextContent("4");
    expect(stat("Votants")).toHaveTextContent("40");
    // courbe : trois séries, une par choix
    const legend = screen.getByRole("list", { name: "Légende" });
    expect(within(legend).getAllByRole("listitem").map((l) => l.textContent)).toEqual(["Il faut en parler", "Pas prioritaire", "Je ne sais pas"]);
    // votes : numéros de compte, jamais d’adresse
    const votes = await screen.findByRole("table", { name: /Votes, du plus récent/ });
    expect(within(votes).getByRole("columnheader", { name: "Numéro de compte" })).toBeInTheDocument();
    expect(within(votes).getByText("101")).toBeInTheDocument();
    expect(within(votes).getAllByRole("row")).toHaveLength(3);
    await userEvent.click(screen.getByRole("button", { name: "Suivant" }));
    expect(await within(await screen.findByRole("table", { name: /Votes, du plus récent/ })).findByText("102")).toBeInTheDocument();
    expect(screen.getByText("Page 2 sur 3 — 120 votes")).toBeInTheDocument();
    // articles
    const articles = screen.getByRole("table", { name: /Articles du sujet \(2\)/ });
    expect(within(articles).getByRole("link", { name: "Article A" })).toHaveAttribute("href", "https://a.example/1");
    expect(within(articles).getByText("source désactivée")).toBeInTheDocument();
  });

  it("sujet pas à la une et sans vote : indicateur, courbe vide", async () => {
    stubFetch({
      ...ME,
      "GET /api/admin/topics/7": () =>
        res(200, detail({
          state: "new", wave: 0, state_changed_at: null, evaluated_at: null,
          support: { score: 0, level: "low", votes_count: 0 },
          front: { on_front: false, reason: null },
          votes: { more: 0, not_priority: 0, unknown: 0, total: 0, voters: 0, first_vote_at: null, daily: [] },
          articles: [],
        })),
      "GET /api/admin/topics/7/votes": () => res(200, { items: [], total: 0, page: 1, page_size: 50 }),
    });
    open("/admin/sujets/7");
    await screen.findByRole("heading", { level: 1, name: "Retraites" });
    expect(screen.getByText("À la une", { selector: "dt" }).parentElement).toHaveTextContent("N’est pas à la une");
    expect(screen.getByText("Aucun vote pour le moment.", { selector: "text" })).toBeInTheDocument();
    expect(await screen.findByText("Aucun vote.")).toBeInTheDocument();
    expect(screen.getByText("Aucun article.")).toBeInTheDocument();
  });

  it("sujet inconnu (404) : message et lien de retour", async () => {
    stubFetch({ ...ME, "GET /api/admin/topics/9": () => res(404, { detail: "Sujet introuvable." }), "GET /api/admin/topics/9/votes": () => res(404, {}) });
    open("/admin/sujets/9");
    expect(await screen.findByRole("heading", { level: 1, name: "Sujet introuvable" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "← Tous les sujets" })).toHaveAttribute("href", "/admin/sujets");
  });

  it("erreur serveur : alerte", async () => {
    stubFetch({ ...ME, "GET /api/admin/topics/7": () => res(500, {}), "GET /api/admin/topics/7/votes": () => res(500, {}) });
    open("/admin/sujets/7");
    expect(await screen.findByRole("alert")).toHaveTextContent("Impossible de charger le sujet");
  });
});
