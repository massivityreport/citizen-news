import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AppRoutes } from "../../App";
import type { AdminPreview, AdminPreviewItem } from "../../api/types";
import { renderWithProviders } from "../../test/utils";
import { res, stubFetch, type Handler } from "../../test/api-stub";

afterEach(() => vi.unstubAllGlobals());

const ME: Record<string, Handler> = { "GET /api/admin/me": () => res(200, { authenticated: true }) };
const open = () => renderWithProviders(<AppRoutes />, "/admin/apercu");

const item = (rank: number, over: Partial<AdminPreviewItem> = {}): AdminPreviewItem => ({
  rank, topic_id: rank, title: `Sujet ${rank}`, approvals: 100 - rank, proportion: (100 - rank) / 200, source_count: 4,
  article_count: 8, updated_at: "2026-11-27T08:00:00Z", tied_with: [], broken_by: null, ...over,
});
const range = (from: number, to: number) => Array.from({ length: to - from + 1 }, (_, i) => item(from + i));
const preview = (over: Partial<AdminPreview> = {}): AdminPreview => ({
  computed_at: "2026-11-27T12:30:00Z", edition_date: "2026-11-27", participants: 200,
  topics: range(1, 10), next: range(11, 20), ties: [], ...over,
});

describe("aperçu de la une", () => {
  it("bandeau, participants, dix sujets avec rang, approbations, % et médias, séparateur puis rangs 11 à 20", async () => {
    stubFetch({ ...ME, "GET /api/admin/edition/preview": () => res(200, preview()) });
    open();
    expect(await screen.findByRole("heading", { level: 1, name: "Prévisualisation de la une" })).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent("Prévisualisation — rien n’est publié ni figé, réservé à l’administration");
    expect((await screen.findByText("Participants", { selector: "dt" })).parentElement).toHaveTextContent("200");
    expect(screen.getByText(/Calculé à/)).toBeInTheDocument();
    const [top, next] = screen.getAllByRole("table");
    const rows = within(top).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(10);
    expect(within(rows[0]).getAllByRole("cell").map((c) => c.textContent)).toEqual(["1", "99", "50 %", "4", "—"]);
    expect(within(next).getAllByRole("row").slice(1).map((r) => within(r).getAllByRole("cell")[0].textContent)).toEqual(
      range(11, 20).map((i) => String(i.rank)),
    );
    // le séparateur « coupure » est entre les deux tableaux
    const cut = screen.getByRole("separator");
    expect(top.compareDocumentPosition(cut) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(cut.compareDocumentPosition(next) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(cut).toHaveTextContent("Coupure");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/@/);
  });

  it("égalités : critère de départage en français, sans alerte quand elle ne franchit pas la coupure", async () => {
    const topics = range(1, 10);
    topics[2] = item(3, { approvals: 50, tied_with: [4], broken_by: "source_count" });
    topics[3] = item(4, { approvals: 50, tied_with: [3], broken_by: "source_count" });
    topics[5] = item(6, { approvals: 40, tied_with: [7], broken_by: "updated_at" });
    topics[6] = item(7, { approvals: 40, tied_with: [6], broken_by: "updated_at" });
    stubFetch({
      ...ME,
      "GET /api/admin/edition/preview": () =>
        res(200, preview({
          topics,
          ties: [
            { approvals: 50, topic_ids: [3, 4], broken_by: "source_count", crosses_cut: false },
            { approvals: 40, topic_ids: [6, 7], broken_by: "id", crosses_cut: false },
          ],
        })),
    });
    open();
    const list = within(await screen.findByRole("heading", { level: 2, name: "Sujets à égalité" }).then((h) => h.nextElementSibling as HTMLElement));
    const items = list.getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Sujet 3 · Sujet 4");
    expect(items[0]).toHaveTextContent("Départagés par le nombre de médias");
    expect(items[1]).toHaveTextContent("l’identifiant du sujet (ordre fixe)");
    const rows = within(screen.getAllByRole("table")[0]).getAllByRole("row");
    expect(rows[3]).toHaveTextContent("Égalité avec Sujet 4");
    expect(rows[3]).toHaveTextContent("départagé par le nombre de médias");
    expect(rows[6]).toHaveTextContent("départagé par la mise à jour la plus récente");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("égalité qui franchit la coupure 10/11 : alerte spéciale", async () => {
    const topics = range(1, 10);
    topics[9] = item(10, { approvals: 30, tied_with: [11], broken_by: "updated_at" });
    const next = range(11, 20);
    next[0] = item(11, { approvals: 30, tied_with: [10], broken_by: "updated_at" });
    stubFetch({
      ...ME,
      "GET /api/admin/edition/preview": () =>
        res(200, preview({ topics, next, ties: [{ approvals: 30, topic_ids: [10, 11], broken_by: "updated_at", crosses_cut: true }] })),
    });
    open();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("franchit la coupure");
    expect(alert).toHaveTextContent(/10e et le 11e rang/);
  });

  it("aucune une enregistrée : état vide", async () => {
    stubFetch({ ...ME, "GET /api/admin/edition/preview": () => res(200, preview({ participants: 0, topics: [], next: [] })) });
    open();
    expect(await screen.findByText(/Aucune une enregistrée/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.getByRole("note")).toBeInTheDocument();
  });

  it("moins de dix sujets, pas de rangs 11 à 20", async () => {
    stubFetch({ ...ME, "GET /api/admin/edition/preview": () => res(200, preview({ topics: range(1, 3), next: [] })) });
    open();
    expect(await screen.findByText("Aucun autre sujet n’a d’approbation.")).toBeInTheDocument();
    expect(screen.getAllByRole("table")).toHaveLength(1);
  });

  it("« Recalculer » refait l’appel, désactivé pendant le chargement", async () => {
    let n = 0;
    let release: () => void = () => {};
    const fn = stubFetch({
      ...ME,
      "GET /api/admin/edition/preview": async () => {
        n += 1;
        if (n === 2) await new Promise<void>((r) => (release = r));
        return res(200, preview({ participants: 100 * n }));
      },
    });
    open();
    const dd = async (text: string) => await screen.findByText(text, { selector: "dd" });
    await dd("100");
    const button = screen.getByRole("button", { name: "Recalculer" });
    expect(button).toBeEnabled();
    await userEvent.click(button);
    expect(await screen.findByRole("button", { name: "Calcul…" })).toBeDisabled();
    release();
    await dd("200");
    expect(screen.getByRole("button", { name: "Recalculer" })).toBeEnabled();
    expect(fn.mock.calls.filter(([u]) => String(u).endsWith("/admin/edition/preview"))).toHaveLength(2);
  });

  it("erreur au premier calcul puis nouvel essai", async () => {
    let ok = false;
    stubFetch({ ...ME, "GET /api/admin/edition/preview": () => (ok ? res(200, preview()) : res(500, {})) });
    open();
    expect(await screen.findByRole("alert")).toHaveTextContent("Impossible de calculer l’aperçu");
    ok = true;
    await userEvent.click(screen.getByRole("button", { name: "Recalculer" }));
    expect(await screen.findByRole("heading", { level: 2, name: "Les dix sujets de la une" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("recalcul en échec : anciennes données conservées et message", async () => {
    let n = 0;
    stubFetch({ ...ME, "GET /api/admin/edition/preview": () => (++n === 1 ? res(200, preview({ participants: 321 })) : res(500, {})) });
    open();
    await screen.findByText("321", { selector: "dd" });
    await userEvent.click(screen.getByRole("button", { name: "Recalculer" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Le recalcul a échoué");
    expect(screen.getByText("321", { selector: "dd" })).toBeInTheDocument();
    expect(screen.getAllByRole("table")).toHaveLength(2);
  });

  it("plusieurs égalités qui franchissent la coupure : une seule alerte", async () => {
    stubFetch({
      ...ME,
      "GET /api/admin/edition/preview": () =>
        res(200, preview({
          ties: [
            { approvals: 30, topic_ids: [10, 11], broken_by: "updated_at", crosses_cut: true },
            { approvals: 30, topic_ids: [10, 12], broken_by: "id", crosses_cut: true },
          ],
        })),
    });
    open();
    await screen.findByRole("alert");
    expect(screen.getAllByRole("alert")).toHaveLength(1);
  });

  it("401 : retour à la connexion", async () => {
    let authed = true;
    stubFetch({
      "GET /api/admin/me": () => (authed ? res(200, { authenticated: true }) : res(401, {})),
      "GET /api/admin/edition/preview": () => {
        authed = false;
        return res(401, { detail: "Non autorisé." });
      },
    });
    open();
    await waitFor(() => expect(screen.getByLabelText(/mot de passe/i)).toBeInTheDocument());
  });

  it("entrée de menu vers l’aperçu", async () => {
    stubFetch({ ...ME, "GET /api/admin/edition/preview": () => res(200, preview()) });
    open();
    expect(
      within(await screen.findByRole("navigation", { name: /administration/i })).getByRole("link", { name: "Aperçu de la une" }),
    ).toHaveAttribute("href", "/admin/apercu");
  });
});
