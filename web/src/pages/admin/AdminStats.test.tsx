import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AppRoutes } from "../../App";
import type { AdminStats } from "../../api/types";
import { renderWithProviders } from "../../test/utils";
import { res, stubFetch } from "../../test/api-stub";

afterEach(() => vi.unstubAllGlobals());

const ME = { "GET /api/admin/me": () => res(200, { authenticated: true }) };
const series = (f: (i: number) => number) =>
  Array.from({ length: 30 }, (_, i) => ({
    date: new Date(Date.UTC(2026, 9, 29 + i)).toISOString().slice(0, 10),
    articles: f(i),
    votes: f(i) * 2,
    voters: f(i),
  }));
const stats = (over: Partial<AdminStats> = {}): AdminStats => ({
  last_24h: { articles: 1234, votes: 56, voters: 7 },
  total: { articles: 1234567, votes: 8901, voters: 234 },
  series: series((i) => i),
  ...over,
});
const open = () => renderWithProviders(<AppRoutes />, "/admin");

describe("accueil du backoffice", () => {
  it("tuiles avec séparateurs de milliers et trois courbes", async () => {
    stubFetch({ ...ME, "GET /api/admin/stats": () => res(200, stats()) });
    open();
    const tile = async (label: string) => (await screen.findByText(label)).closest("div")!;
    expect(within(await tile("Articles (24 h)")).getByText(/^1\s234$/)).toBeInTheDocument();
    expect(within(await tile("Articles (total)")).getByText(/^1\s234\s567$/)).toBeInTheDocument();
    expect(within(await tile("Votes (24 h)")).getByText("56")).toBeInTheDocument();
    expect(within(await tile("Votes (total)")).getByText(/^8\s901$/)).toBeInTheDocument();
    expect(within(await tile("Votants (24 h)")).getByText("7")).toBeInTheDocument();
    expect(within(await tile("Votants (total)")).getByText("234")).toBeInTheDocument();
    expect(screen.getAllByRole("img")).toHaveLength(3);
    expect(screen.getByRole("img", { name: /Votants distincts par jour/ })).toBeInTheDocument();
    expect(screen.getByText(/on ne peut pas additionner les jours/)).toBeInTheDocument();
  });

  it("série vide : tuiles à 0 et message en français", async () => {
    const zero = { articles: 0, votes: 0, voters: 0 };
    stubFetch({ ...ME, "GET /api/admin/stats": () => res(200, stats({ last_24h: zero, total: zero, series: series(() => 0) })) });
    open();
    expect((await screen.findAllByText("Aucune donnée sur les 30 derniers jours.")).length).toBeGreaterThanOrEqual(3);
  });

  it("erreur : message et nouvel essai avec « Actualiser »", async () => {
    let ok = false;
    const fn = stubFetch({ ...ME, "GET /api/admin/stats": () => (ok ? res(200, stats()) : res(500, { detail: "boom" })) });
    open();
    expect(await screen.findByRole("alert")).toHaveTextContent("Impossible de charger les statistiques");
    ok = true;
    await userEvent.click(screen.getByRole("button", { name: "Actualiser" }));
    expect(await screen.findByText("Articles (24 h)")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(fn.mock.calls.filter(([u]) => String(u).endsWith("/admin/stats"))).toHaveLength(2);
  });

  it("« Actualiser » recharge les chiffres", async () => {
    let n = 0;
    stubFetch({ ...ME, "GET /api/admin/stats": () => res(200, stats({ last_24h: { articles: ++n, votes: 0, voters: 0 } })) });
    open();
    const tile = async () => (await screen.findByText("Articles (24 h)")).closest("div")!;
    expect(within(await tile()).getByText("1")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Actualiser" }));
    await waitFor(() => expect(within(screen.getByText("Articles (24 h)").closest("div")!).getByText("2")).toBeInTheDocument());
  });
});
