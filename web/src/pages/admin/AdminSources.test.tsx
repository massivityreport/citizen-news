import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { AdminSource } from "../../api/types";
import { renderApp } from "../../test/utils";
import { bodiesOf, res, stubFetch, type Handler } from "../../test/api-stub";

afterEach(() => vi.unstubAllGlobals());

const src = (over: Partial<AdminSource> & { id: number }): AdminSource => ({
  name: `Média ${over.id}`,
  feed_url: `https://m${over.id}.example/rss`,
  active: true,
  article_count: 0,
  last_article_at: null,
  ...over,
});

/** API admin factice avec état : la liste reflète les ajouts, changements d’état et suppressions. */
function fakeAdmin(initial: AdminSource[], extra: Record<string, Handler> = {}) {
  let list = initial;
  const fn = stubFetch({
    "GET /api/admin/me": () => res(200, { authenticated: true }),
    "GET /api/admin/sources": () => res(200, list),
    "POST /api/admin/sources": (init) => {
      const body = JSON.parse(init!.body as string);
      const created = src({ id: 100, name: body.name, feed_url: body.feed_url });
      list = [...list, created];
      return res(201, created);
    },
    ...extra,
  });
  return {
    fn,
    set: (l: AdminSource[]) => (list = l),
    get: () => list,
  };
}

const ALPHA = src({ id: 1, name: "Alpha", article_count: 3, last_article_at: "2020-03-05T10:00:00Z" });
const BETA = src({ id: 2, name: "Beta", active: false, article_count: 1 });

async function openSources() {
  renderApp("/admin/sources");
  return screen.findByRole("heading", { level: 1, name: "Sources" });
}

describe("onglet Sources", () => {
  it("liste les sources avec état, nombre d’articles et date du dernier article", async () => {
    fakeAdmin([ALPHA, BETA, src({ id: 3, name: "Gamma" })]);
    await openSources();
    const table = await screen.findByRole("table");
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(3);
    const alpha = within(rows[0]);
    expect(alpha.getByRole("rowheader")).toHaveTextContent("Alpha");
    expect(alpha.getByText("https://m1.example/rss")).toBeInTheDocument();
    expect(alpha.getByText("Actif")).toBeInTheDocument();
    expect(alpha.getByText("3")).toBeInTheDocument();
    expect(alpha.getByText("5 mars 2020")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Inactif")).toBeInTheDocument();
    expect(within(rows[2]).getByText("Aucun article")).toBeInTheDocument();
  });

  it("liste vide", async () => {
    fakeAdmin([]);
    await openSources();
    expect(await screen.findByText("Aucune source pour le moment.")).toBeInTheDocument();
  });

  it("erreur de chargement : alerte", async () => {
    stubFetch({ "GET /api/admin/me": () => res(200, {}), "GET /api/admin/sources": () => res(500, {}) });
    await openSources();
    expect(await screen.findByRole("alert")).toHaveTextContent("Impossible de charger les sources");
  });

  it("ajout réussi : envoie nom et URL, vide le formulaire, rafraîchit la liste", async () => {
    const api = fakeAdmin([ALPHA]);
    await openSources();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Nom de la source"), "Le Nouveau");
    await user.type(screen.getByLabelText("Adresse du flux (RSS ou Atom)"), "https://nouveau.example/rss");
    await user.click(screen.getByRole("button", { name: "Ajouter la source" }));
    expect(await screen.findByRole("status")).toHaveTextContent("La source « Le Nouveau » a été ajoutée.");
    expect(bodiesOf(api.fn, "POST /api/admin/sources")).toEqual([
      { name: "Le Nouveau", feed_url: "https://nouveau.example/rss" },
    ]);
    expect(await screen.findByRole("rowheader", { name: "Le Nouveau" })).toBeInTheDocument();
    expect(screen.getByLabelText("Nom de la source")).toHaveValue("");
  });

  it("ajout : état de chargement pendant la vérification, un seul envoi", async () => {
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    const api = fakeAdmin([], {
      "POST /api/admin/sources": async () => {
        await gate;
        return res(201, src({ id: 5 }));
      },
    });
    await openSources();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Nom de la source"), "X");
    await user.type(screen.getByLabelText("Adresse du flux (RSS ou Atom)"), "https://x.example/rss");
    await user.click(screen.getByRole("button", { name: "Ajouter la source" }));
    const busy = await screen.findByRole("button", { name: "Vérification du flux…" });
    expect(busy).toBeDisabled();
    release();
    await screen.findByRole("status");
    expect(bodiesOf(api.fn, "POST /api/admin/sources")).toHaveLength(1);
  });

  it("ajout refusé : message du serveur en français dans une alerte, formulaire conservé", async () => {
    fakeAdmin([], {
      "POST /api/admin/sources": () =>
        res(422, { detail: "Cette adresse est refusée ou injoignable. Vérifiez l’adresse du flux." }),
    });
    await openSources();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Nom de la source"), "Interne");
    await user.type(screen.getByLabelText("Adresse du flux (RSS ou Atom)"), "http://localhost/rss");
    await user.click(screen.getByRole("button", { name: "Ajouter la source" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Cette adresse est refusée ou injoignable.");
    expect(screen.getByLabelText("Adresse du flux (RSS ou Atom)")).toHaveValue("http://localhost/rss");
    expect(screen.getByLabelText("Adresse du flux (RSS ou Atom)")).toHaveAttribute("aria-invalid", "true");
  });

  it("ajout : doublon (409), erreur serveur sans message", async () => {
    let status = 409;
    fakeAdmin([], {
      "POST /api/admin/sources": () =>
        status === 409 ? res(409, { detail: "Cette source existe déjà (elle est peut-être désactivée)." }) : res(500, {}),
    });
    await openSources();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Nom de la source"), "X");
    await user.type(screen.getByLabelText("Adresse du flux (RSS ou Atom)"), "https://x.example/rss");
    await user.click(screen.getByRole("button", { name: "Ajouter la source" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("existe déjà");
    status = 500;
    await user.click(screen.getByRole("button", { name: "Ajouter la source" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("n’a pas pu être ajoutée"));
  });

  it("désactiver puis réactiver", async () => {
    const api = fakeAdmin([ALPHA], {
      "POST /api/admin/sources/1/deactivate": () => (api.set([{ ...ALPHA, active: false }]), res(200, {})),
      "POST /api/admin/sources/1/reactivate": () => (api.set([ALPHA]), res(200, {})),
    });
    await openSources();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Désactiver Alpha" }));
    expect(await screen.findByText("Inactif")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Réactiver Alpha" }));
    expect(await screen.findByText("Actif")).toBeInTheDocument();
    expect(api.fn.mock.calls.map(([u, i]) => `${i?.method ?? "GET"} ${u}`)).toEqual(
      expect.arrayContaining(["POST /api/admin/sources/1/deactivate", "POST /api/admin/sources/1/reactivate"]),
    );
  });

  it("échec de désactivation : alerte", async () => {
    fakeAdmin([ALPHA], { "POST /api/admin/sources/1/deactivate": () => res(404, { detail: "Source introuvable." }) });
    await openSources();
    await userEvent.setup().click(await screen.findByRole("button", { name: "Désactiver Alpha" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Source introuvable.");
  });
});

describe("suppression définitive", () => {
  it("demande une confirmation explicite avec le nombre d’articles, puis supprime", async () => {
    const api = fakeAdmin([ALPHA, BETA], {
      "DELETE /api/admin/sources/1": () => (api.set([BETA]), res(200, { id: 1, deleted_articles: 3 })),
    });
    await openSources();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Supprimer définitivement Alpha" }));
    const dialog = await screen.findByRole("dialog", { name: /Supprimer définitivement « Alpha »/ });
    expect(dialog).toHaveTextContent("3 articles seront supprimés définitivement");
    const confirm = within(dialog).getByRole("button", { name: "Supprimer définitivement" });
    expect(confirm).toBeDisabled();
    expect(within(dialog).getByLabelText(/saisissez le nom de la source/i)).toHaveFocus();
    await user.type(within(dialog).getByLabelText(/saisissez le nom/i), "Alph");
    expect(confirm).toBeDisabled();
    await user.type(within(dialog).getByLabelText(/saisissez le nom/i), "a");
    expect(confirm).toBeEnabled();
    await user.click(confirm);
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(screen.queryByRole("rowheader", { name: "Alpha" })).toBeNull();
    expect(screen.getByRole("rowheader", { name: "Beta" })).toBeInTheDocument();
  });

  it("envoie le nombre d’articles affiché comme confirmation", async () => {
    const calls: string[] = [];
    let list = [ALPHA];
    stubFetch({
      "GET /api/admin/me": () => res(200, {}),
      "GET /api/admin/sources": () => res(200, list),
      "DELETE /api/admin/sources/1": (_i, url) => ((list = []), calls.push(url), res(200, { id: 1, deleted_articles: 3 })),
    });
    await openSources();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Supprimer définitivement Alpha" }));
    await user.type(await screen.findByLabelText(/saisissez le nom/i), "Alpha{Enter}");
    await waitFor(() => expect(calls).toEqual(["/api/admin/sources/1?confirm=3"]));
  });

  it("annuler (bouton ou Échap) ne supprime rien", async () => {
    const api = fakeAdmin([ALPHA]);
    await openSources();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Supprimer définitivement Alpha" }));
    await user.click(await screen.findByRole("button", { name: "Annuler" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Supprimer définitivement Alpha" }));
    await screen.findByRole("dialog");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(api.fn.mock.calls.some(([, i]) => i?.method === "DELETE")).toBe(false);
  });

  it("le serveur refuse (le nombre d’articles a changé) : message, liste rechargée, saisie à refaire", async () => {
    let list = [ALPHA];
    stubFetch({
      "GET /api/admin/me": () => res(200, {}),
      "GET /api/admin/sources": () => res(200, list),
      "DELETE /api/admin/sources/1": () => {
        list = [{ ...ALPHA, article_count: 4 }];
        return res(409, { detail: "Confirmation invalide : la suppression effacerait 4 articles. Rechargez la liste et confirmez le nombre exact." });
      },
    });
    await openSources();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Supprimer définitivement Alpha" }));
    await user.type(await screen.findByLabelText(/saisissez le nom/i), "Alpha");
    await user.click(screen.getByRole("button", { name: "Supprimer définitivement" }));
    const dialog = screen.getByRole("dialog");
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Confirmation invalide");
    await waitFor(() => expect(dialog).toHaveTextContent("4 articles seront supprimés définitivement"));
    expect(within(dialog).getByLabelText(/saisissez le nom/i)).toHaveValue("");
    expect(within(dialog).getByRole("button", { name: "Supprimer définitivement" })).toBeDisabled();
  });
});
