import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useLocation } from "react-router-dom";
import { AppRoutes } from "../../App";
import type { AdminArticle, AdminSource, AdminTopicRow, Page } from "../../api/types";
import { renderWithProviders } from "../../test/utils";
import { res, stubFetch } from "../../test/api-stub";

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

const article = (id: number, over: Partial<AdminArticle> = {}): AdminArticle => ({
  id,
  title: `Article ${id}`,
  url: `https://m.example/${id}`,
  source: { id: 1, name: "Alpha", active: true },
  published_at: "2026-11-03T10:00:00Z",
  fetched_at: "2026-11-03T11:00:00Z",
  topic: { id: 7, title: "Retraites" },
  grouped: true,
  ...over,
});
const topicRow = (id: number, title: string): AdminTopicRow => ({
  id, title, state: "active", wave: 1, state_changed_at: null, article_count: 1, source_count: 1, vote_count: 0, image_url: null,
});
const SOURCES: AdminSource[] = [
  { id: 1, name: "Alpha", feed_url: "https://a.example/rss", active: true, article_count: 3, last_article_at: null },
  { id: 2, name: "Beta", feed_url: "https://b.example/rss", active: false, article_count: 1, last_article_at: null },
];

/** API factice : enregistre les paramètres de chaque appel à /articles. */
function fakeApi(pageOf: (q: URLSearchParams) => Page<AdminArticle>) {
  const calls: URLSearchParams[] = [];
  const fn = stubFetch({
    "GET /api/admin/me": () => res(200, { authenticated: true }),
    "GET /api/admin/sources": () => res(200, SOURCES),
    "GET /api/admin/topics": () => res(200, { items: [topicRow(7, "Retraites"), topicRow(9, "Canicule")], total: 2, page: 1, page_size: 200 }),
    "GET /api/admin/articles": (_init, url) => {
      const q = new URLSearchParams(url.split("?")[1] ?? "");
      calls.push(q);
      return res(200, pageOf(q));
    },
  });
  return { fn, calls, last: () => calls[calls.length - 1] };
}
const page = (items: AdminArticle[], total = items.length, p = 1): Page<AdminArticle> => ({ items, total, page: p, page_size: 50 });

describe("onglet Articles", () => {
  it("affiche le tableau : titre, source, date, sujet regroupé (lien), non regroupé, source désactivée", async () => {
    fakeApi(() =>
      page([
        article(1),
        article(2, { topic: null, grouped: false, source: { id: 2, name: "Beta", active: false }, published_at: null }),
      ]),
    );
    open("/admin/articles");
    const table = await screen.findByRole("table", { name: /Articles : 2 au total/ });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(within(rows[0]).getByRole("link", { name: "Article 1" })).toHaveAttribute("href", "https://m.example/1");
    expect(within(rows[0]).getByText("regroupé")).toBeInTheDocument();
    expect(within(rows[0]).getByRole("link", { name: "Retraites" })).toHaveAttribute("href", "/admin/sujets/7");
    expect(within(rows[1]).getByText("non regroupé")).toBeInTheDocument();
    expect(within(rows[1]).getByText("source désactivée")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Date inconnue")).toBeInTheDocument();
  });

  it("états : vide, erreur", async () => {
    fakeApi(() => page([]));
    open("/admin/articles");
    expect(await screen.findByText("Aucun article ne correspond à ces filtres.")).toBeInTheDocument();
  });

  it("erreur de chargement : alerte en français", async () => {
    stubFetch({
      "GET /api/admin/me": () => res(200, {}),
      "GET /api/admin/sources": () => res(200, SOURCES),
      "GET /api/admin/topics": () => res(200, { items: [], total: 0, page: 1, page_size: 200 }),
      "GET /api/admin/articles": () => res(500, {}),
    });
    open("/admin/articles");
    expect(await screen.findByRole("alert")).toHaveTextContent("Impossible de charger les articles");
  });

  it("tri par défaut (date, plus récent d’abord) et aria-sort", async () => {
    const api = fakeApi(() => page([article(1)]));
    open("/admin/articles");
    await screen.findByRole("table");
    expect(api.last().get("sort")).toBe("date");
    expect(api.last().get("order")).toBe("desc");
    expect(screen.getByRole("columnheader", { name: /Publié/ })).toHaveAttribute("aria-sort", "descending");
    expect(screen.getByRole("columnheader", { name: /Source/ })).toHaveAttribute("aria-sort", "none");
  });

  it("clic sur un en-tête : trie, inverse au second clic, remet à la page 1, et l’URL le garde", async () => {
    const api = fakeApi(() => page([article(1)], 120));
    open("/admin/articles?page=3");
    await screen.findByRole("table");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Source/ }));
    await waitFor(() => expect(api.last().get("sort")).toBe("source"));
    expect(api.last().get("order")).toBe("asc");
    expect(api.last().get("page")).toBe("1");
    expect(where()).toBe("/admin/articles?sort=source&order=asc");
    expect(await screen.findByRole("columnheader", { name: /Source/ })).toHaveAttribute("aria-sort", "ascending");
    await user.click(screen.getByRole("button", { name: /Source/ }));
    await waitFor(() => expect(api.last().get("order")).toBe("desc"));
    expect(where()).toBe("/admin/articles?sort=source&order=desc");
  });

  it("l’état est restauré depuis l’URL (lien partagé)", async () => {
    const api = fakeApi(() => page([article(1)], 120, 2));
    open("/admin/articles?sort=topic&order=desc&page=2&source_id=2&topic_id=9&date_from=2026-11-01&date_to=2026-11-05");
    await screen.findByRole("table");
    const q = api.last();
    expect(Object.fromEntries(q)).toEqual({
      page: "2", sort: "topic", order: "desc", source_id: "2", topic_id: "9", date_from: "2026-11-01", date_to: "2026-11-05",
    });
    expect(screen.getByRole("columnheader", { name: /Sujet/ })).toHaveAttribute("aria-sort", "descending");
    expect(screen.getByLabelText("Source")).toHaveValue("2");
    await waitFor(() => expect(screen.getByLabelText("Sujet")).toHaveValue("9"));
    expect(screen.getByLabelText("Publié du")).toHaveValue("2026-11-01");
    expect(screen.getByLabelText("au (inclus)")).toHaveValue("2026-11-05");
  });

  it("un tri inconnu dans l’URL retombe sur le tri par défaut", async () => {
    const api = fakeApi(() => page([article(1)]));
    open("/admin/articles?sort=id;drop&order=up&page=abc");
    await screen.findByRole("table");
    expect(Object.fromEntries(api.last())).toEqual({ page: "1", sort: "date", order: "desc" });
  });

  it("pagination : numéro de page, total, précédent/suivant (désactivés aux extrémités)", async () => {
    const api = fakeApi((q) => page([article(Number(q.get("page")))], 120, Number(q.get("page"))));
    open("/admin/articles");
    const nav = await screen.findByRole("navigation", { name: /Pagination/ });
    expect(nav).toHaveTextContent("Page 1 sur 3 — 120 articles");
    expect(within(nav).getByRole("button", { name: "Précédent" })).toBeDisabled();
    const user = userEvent.setup();
    await user.click(within(nav).getByRole("button", { name: "Suivant" }));
    expect(await screen.findByText("Page 2 sur 3 — 120 articles")).toBeInTheDocument();
    expect(where()).toBe("/admin/articles?page=2");
    await user.click(screen.getByRole("button", { name: "Suivant" }));
    expect(await screen.findByText("Page 3 sur 3 — 120 articles")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Suivant" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Précédent" }));
    await waitFor(() => expect(api.last().get("page")).toBe("2"));
  });

  it("page hors bornes : message et retour à la première page", async () => {
    const api = fakeApi((q) => (q.get("page") === "1" ? page([article(1)], 1) : page([], 1, Number(q.get("page")))));
    open("/admin/articles?page=9");
    expect(await screen.findByText(/Cette page n’existe pas/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Revenir à la première page" }));
    expect(await screen.findByRole("table")).toBeInTheDocument();
    expect(api.last().get("page")).toBe("1");
    expect(where()).toBe("/admin/articles");
  });

  it("filtres : source, sujet, dates : envoyés au serveur, page remise à 1, dans l’URL", async () => {
    const api = fakeApi(() => page([article(1)], 120));
    open("/admin/articles?page=2");
    await screen.findByRole("table");
    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText("Source"), "2");
    await waitFor(() => expect(api.last().get("source_id")).toBe("2"));
    expect(api.last().get("page")).toBe("1");
    await waitFor(() => expect(screen.getByLabelText("Sujet")).toContainHTML("Canicule"));
    await user.selectOptions(screen.getByLabelText("Sujet"), "9");
    await waitFor(() => expect(api.last().get("topic_id")).toBe("9"));
    await user.type(screen.getByLabelText("Publié du"), "2026-11-02");
    await waitFor(() => expect(api.last().get("date_from")).toBe("2026-11-02"));
    expect(where()).toBe("/admin/articles?source_id=2&topic_id=9&date_from=2026-11-02");
  });

  it("« non regroupés » : envoie ungrouped, retire et désactive le filtre de sujet", async () => {
    const api = fakeApi(() => page([article(1)]));
    open("/admin/articles?topic_id=7");
    await screen.findByRole("table");
    await waitFor(() => expect(screen.getByLabelText("Sujet")).toHaveValue("7"));
    await userEvent.click(screen.getByRole("checkbox", { name: "Non regroupés seulement" }));
    await waitFor(() => expect(api.last().get("ungrouped")).toBe("true"));
    expect(api.last().has("topic_id")).toBe(false);
    expect(screen.getByLabelText("Sujet")).toBeDisabled();
    expect(where()).toBe("/admin/articles?ungrouped=true");
    await userEvent.click(screen.getByRole("checkbox", { name: "Non regroupés seulement" }));
    await waitFor(() => expect(api.last().has("ungrouped")).toBe(false));
  });
});
