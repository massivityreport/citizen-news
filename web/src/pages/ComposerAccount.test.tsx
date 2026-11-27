import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { AppRoutes } from "../App";
import type { Une } from "../api/types";
import { bodiesOf, res, stubFetch, type Handler } from "../test/api-stub";
import { pool, une } from "../test/topics";
import { draftStore } from "../lib/draftStore";

afterEach(() => vi.unstubAllGlobals());

const IDS = [1, 2, 3, 4, 5, 6];

function mount(opts: { me?: boolean; une?: Une; routes?: Record<string, Handler>; closed?: boolean } = {}) {
  const fn = stubFetch({
    "GET /api/me": () => (opts.me === false ? res(401, {}) : res(200, { email: "a@b.fr" })),
    "GET /api/topics/pool": () => res(200, pool(IDS, { open: !opts.closed })),
    "GET /api/me/une": () => res(200, opts.une ?? une([])),
    ...opts.routes,
  });
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/composer"]}>
        <AppRoutes />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return fn;
}

const heading = (n: number) => screen.findByRole("heading", { level: 3, name: `Sujet ${n}` });
const saved = () => screen.findByText("Enregistrée");
const review = () => screen.getByRole("region", { name: "Revoir et valider" });
const click = (name: string | RegExp) => userEvent.click(screen.getByRole("button", { name }));

describe("Composer avec compte", () => {
  it("la une vient du serveur : « Enregistrée », aperçu, carte marquée", async () => {
    mount({ une: une([1, 3]) });
    await heading(1);
    expect(await screen.findByText("Enregistrée")).toBeInTheDocument();
    expect(screen.queryByText("Non enregistrée")).not.toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "2/10 sujets" })).toBeInTheDocument();
    expect(screen.getByText("Dans ma une")).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: /Aperçu/ })).getAllByRole("listitem")[1]).toHaveTextContent("Sujet 3");
  });

  it("ajouter appelle PUT (optimiste) et retirer appelle DELETE", async () => {
    let putResolve: (r: Response) => void = () => {};
    const fn = mount({
      une: une([]),
      routes: {
        "PUT /api/me/une/topics/1": () => new Promise<Response>((r) => (putResolve = r)),
        "DELETE /api/me/une/topics/1": () => res(200, une([])),
      },
    });
    await heading(1);
    await click("Ajouter à ma une");
    // optimiste : visible avant la réponse
    expect(screen.getByRole("progressbar", { name: "1/10 sujets" })).toBeInTheDocument();
    expect(screen.getByText("Enregistrement…")).toBeInTheDocument();
    putResolve(res(200, une([1])));
    expect(await screen.findByText("Enregistrée")).toBeInTheDocument();
    await click("Retirer de ma une");
    await waitFor(() => expect(screen.getByRole("progressbar", { name: "0/10 sujets" })).toBeInTheDocument());
    expect(fn.mock.calls.some(([u, i]) => u === "/api/me/une/topics/1" && i?.method === "DELETE")).toBe(true);
    expect(JSON.stringify(localStorage)).not.toContain("citizen-news:draft");
  });

  it("erreur serveur : retour arrière et message", async () => {
    mount({ routes: { "PUT /api/me/une/topics/1": () => res(500, { detail: "Panne." }) } });
    await heading(1);
    await click("Ajouter à ma une");
    expect(await screen.findAllByText("Panne.")).not.toHaveLength(0);
    expect(screen.getByRole("progressbar", { name: "0/10 sujets" })).toBeInTheDocument();
    expect(screen.queryByText("Dans ma une")).not.toBeInTheDocument();
  });

  it("409 clôture : retour arrière, bannière « La clôture est passée » et lecture seule", async () => {
    mount({
      routes: {
        "PUT /api/me/une/topics/1": () =>
          res(409, { detail: "La clôture est passée, la une du jour n'est plus modifiable" }),
      },
    });
    await heading(1);
    await click("Ajouter à ma une");
    expect(await screen.findByText(/La clôture est passée : votre une est en lecture seule/)).toBeInTheDocument();
    expect(screen.getByText(/La prochaine une repart vide/)).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "0/10 sujets" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ajouter à ma une" })).toBeDisabled();
  });

  it("une déjà fermée à l'ouverture : lecture seule", async () => {
    mount({ une: une([2], { open: false }), closed: true });
    await heading(1);
    expect(await screen.findByText(/La prochaine une repart vide/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ajouter à ma une" })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Suivant/ })).toBeEnabled();
  });

  it("409 « une complète » côté serveur : message de remplacement", async () => {
    mount({ routes: { "PUT /api/me/une/topics/1": () => res(409, { detail: "Votre une est complète" }) } });
    await heading(1);
    await click("Ajouter à ma une");
    expect(await screen.findByText(/Pour ajouter ce sujet/)).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "0/10 sujets" })).toBeInTheDocument();
  });

  it("401 sur la une : repasse au brouillon local", async () => {
    mount({ routes: { "GET /api/me/une": () => res(401, { detail: "x" }) } });
    expect(await screen.findByText("Non enregistrée")).toBeInTheDocument();
  });
});

describe("Composer : fusion automatique du brouillon local", () => {
  const MERGE = "POST /api/me/une/merge";

  it("à la connexion, fusionne seul (une fois, sans ce qui est déjà dans la une), le dit et vide le brouillon", async () => {
    draftStore.set({ editionDate: "2026-11-27", ids: [1, 2, 3] });
    const fn = mount({ une: une([1]), routes: { [MERGE]: () => res(200, { added: 1, ignored: 1, une: une([1, 2]) }) } });
    await heading(1);
    expect(await screen.findByText(/1 sujet ajouté à votre une, 1 ignoré/)).toBeInTheDocument();
    expect(bodiesOf(fn, MERGE)).toEqual([{ topic_ids: [2, 3] }]);
    expect(draftStore.get().ids).toEqual([]);
    expect(screen.getByRole("progressbar", { name: "2/10 sujets" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /fusion/i })).not.toBeInTheDocument();
  });

  it("tout est déjà dans la une : aucun appel, brouillon vidé", async () => {
    draftStore.set({ editionDate: "2026-11-27", ids: [1] });
    const fn = mount({ une: une([1]) });
    await heading(1);
    await waitFor(() => expect(draftStore.get().ids).toEqual([]));
    expect(bodiesOf(fn, MERGE)).toEqual([]);
  });

  it("échec réseau : le brouillon reste, reprise manuelle, un seul envoi même au double clic", async () => {
    draftStore.set({ editionDate: "2026-11-27", ids: [2] });
    let fail = true;
    let release: (r: Response) => void = () => {};
    const fn = mount({
      une: une([]),
      routes: {
        [MERGE]: () => (fail ? res(500, { detail: "Panne." }) : new Promise<Response>((r) => (release = r))),
      },
    });
    await heading(1);
    const retry = await screen.findByRole("button", { name: "Réessayer la fusion" });
    expect(draftStore.get().ids).toEqual([2]);
    expect(bodiesOf(fn, MERGE)).toHaveLength(1); // l'envoi automatique n'est pas rejoué
    fail = false;
    await userEvent.dblClick(retry);
    expect(bodiesOf(fn, MERGE)).toHaveLength(2);
    release(res(200, { added: 1, ignored: 0, une: une([2]) }));
    expect(await screen.findByText(/1 sujet ajouté à votre une/)).toBeInTheDocument();
    expect(draftStore.get().ids).toEqual([]);
  });

  it("« Supprimer le brouillon » après un échec l'efface sans nouvel appel", async () => {
    draftStore.set({ editionDate: "2026-11-27", ids: [2] });
    const fn = mount({ une: une([]), routes: { [MERGE]: () => res(500, { detail: "x" }) } });
    await heading(1);
    await userEvent.click(await screen.findByRole("button", { name: "Supprimer le brouillon" }));
    expect(draftStore.get().ids).toEqual([]);
    expect(bodiesOf(fn, MERGE)).toHaveLength(1);
  });

  it("une fermée : pas de fusion", async () => {
    draftStore.set({ editionDate: "2026-11-27", ids: [2] });
    const fn = mount({ une: une([], { open: false }), closed: true });
    await heading(1);
    await saved();
    expect(bodiesOf(fn, MERGE)).toEqual([]);
    expect(draftStore.get().ids).toEqual([2]);
  });
});

describe("Fusion : garde-fous", () => {
  const MERGE = "POST /api/me/une/merge";

  it("un brouillon d'une autre édition est ignoré et vidé, jamais fusionné", async () => {
    draftStore.set({ editionDate: "2026-11-26", ids: [2, 3] });
    const fn = mount({ une: une([1]) });
    await heading(1);
    await waitFor(() => expect(draftStore.get().ids).toEqual([]));
    expect(bodiesOf(fn, MERGE)).toEqual([]);
    expect(screen.getByRole("progressbar", { name: "1/10 sujets" })).toBeInTheDocument();
  });

  it("ne vide rien tant que la une du compte n'est pas chargée", async () => {
    draftStore.set({ editionDate: "2026-11-27", ids: [1] });
    let release: (r: Response) => void = () => {};
    mount({ routes: { "GET /api/me/une": () => new Promise<Response>((r) => (release = r)) } });
    await heading(1);
    await new Promise((r) => setTimeout(r, 50));
    expect(draftStore.get().ids).toEqual([1]);
    release(res(200, une([1])));
    await waitFor(() => expect(draftStore.get().ids).toEqual([]));
  });

  it("le message de fusion disparaît à la déconnexion", async () => {
    draftStore.set({ editionDate: "2026-11-27", ids: [2] });
    mount({
      une: une([]),
      routes: {
        [MERGE]: () => res(200, { added: 1, ignored: 0, une: une([2]) }),
        "POST /api/auth/logout": () => res(204),
      },
    });
    await heading(1);
    expect(await screen.findByText(/1 sujet ajouté à votre une/)).toBeInTheDocument();
    await click("Se déconnecter");
    await waitFor(() => expect(screen.queryByText(/1 sujet ajouté à votre une/)).not.toBeInTheDocument());
    expect(screen.getByText("Non enregistrée")).toBeInTheDocument();
  });
});

describe("Sujet de la une absent du bassin", () => {
  it("le dit clairement et permet de le retirer", async () => {
    mount({ une: une([99]), routes: { "DELETE /api/me/une/topics/99": () => res(200, une([])) } });
    await heading(1);
    await saved();
    expect(within(screen.getByRole("list", { name: /Aperçu/ })).getAllByRole("listitem")[0]).toHaveTextContent("Ce sujet n’est plus au bassin du jour");
    await click("Revoir et valider");
    expect(within(review()).getByRole("heading", { level: 3 })).toHaveTextContent("Ce sujet n’est plus au bassin du jour");
    await click(/Retirer la place 1/);
    await waitFor(() => expect(screen.getByText(/0\/10 sujets dans votre une/)).toBeInTheDocument());
  });
});

describe("Revoir et valider", () => {
  it("sans compte : explication, e-mail, POST magic-link avec le brouillon, message d'envoi", async () => {
    draftStore.set({ editionDate: "2026-11-27", ids: [2, 4] });
    const fn = mount({ me: false, routes: { "POST /api/auth/magic-link": () => res(202) } });
    await heading(1);
    await click("Revoir et valider");
    expect(screen.getByRole("heading", { level: 2, name: "Revoir et valider" })).toBeInTheDocument();
    expect(screen.getByText(/Pour que votre une compte, enregistrez-la avec votre e-mail/)).toBeInTheDocument();
    expect(within(review()).getAllByRole("listitem")).toHaveLength(10);
    await userEvent.type(screen.getByLabelText("Adresse e-mail"), "moi@exemple.fr");
    await click("Recevoir un lien");
    expect(await screen.findByText(/Un lien vous a été envoyé : ouvrez-le \(même dans un autre navigateur, votre brouillon est joint\)/)).toBeInTheDocument();
    expect(bodiesOf(fn, "POST /api/auth/magic-link")).toEqual([{ email: "moi@exemple.fr", draft: { topic_ids: [2, 4] } }]);
  });

  it("e-mail invalide : message, aucun appel", async () => {
    const fn = mount({ me: false });
    await heading(1);
    await click("Revoir et valider");
    await userEvent.type(screen.getByLabelText("Adresse e-mail"), "pas-un-mail");
    await click("Recevoir un lien");
    expect(await screen.findByRole("alert")).toHaveTextContent(/adresse e-mail valide/);
    expect(bodiesOf(fn, "POST /api/auth/magic-link")).toEqual([]);
  });

  it("avec compte : pas de bouton Enregistrer, confirmation et lien d'aide", async () => {
    mount({ une: une([1]) });
    await heading(1);
    await saved();
    await click("Revoir et valider");
    expect(screen.getByText(/Votre une est enregistrée, modifiable jusqu’à \d+ h/)).toBeInTheDocument();
    expect(within(review()).getByRole("link", { name: /Comment ça marche/ })).toHaveAttribute("href", "/comment-ca-marche");
    expect(screen.queryByRole("button", { name: /Enregistrer/ })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Adresse e-mail")).not.toBeInTheDocument();
  });

  it("retirer depuis la vue détaillée", async () => {
    mount({ une: une([1, 2]), routes: { "DELETE /api/me/une/topics/1": () => res(200, une([2])) } });
    await heading(1);
    await saved();
    await click("Revoir et valider");
    await click(/Retirer Sujet 1/);
    await waitFor(() => expect(screen.getByText(/1\/10 sujets dans votre une/)).toBeInTheDocument());
  });

  it("Remplacer ramène au carrousel avec la place visée, puis remplace (une pleine)", async () => {
    const full = une([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
    const fn = mount({
      pool: undefined,
      une: full,
      routes: {
        "GET /api/topics/pool": () => res(200, pool(Array.from({ length: 12 }, (_, i) => i + 1))),
        "DELETE /api/me/une/topics/2": () => res(200, une([1, 3, 4, 5, 6, 7, 8, 9, 10])),
        "PUT /api/me/une/topics/11": () => res(200, une([1, 3, 4, 5, 6, 7, 8, 9, 10, 11])),
      },
    } as never);
    await heading(1);
    await saved();
    await click("Revoir et valider");
    await click(/Remplacer Sujet 2/);
    expect(await screen.findByText(/Vous remplacez la place 2/)).toBeInTheDocument();
    for (let i = 0; i < 10; i++) await click(/Suivant/);
    expect(screen.getByRole("heading", { level: 3, name: "Sujet 11" })).toBeInTheDocument();
    await click("Mettre à la place 2");
    expect(await screen.findByText(/Sujet remplacé/)).toBeInTheDocument();
    const calls = fn.mock.calls.filter(([, i]) => i?.method === "DELETE" || i?.method === "PUT").map(([u, i]) => `${i!.method} ${u}`);
    expect(calls).toEqual(["DELETE /api/me/une/topics/2", "PUT /api/me/une/topics/11"]);
    expect(screen.queryByText(/Vous remplacez la place 2/)).not.toBeInTheDocument();
  });

  it("après la clôture : lecture seule", async () => {
    mount({ une: une([1], { open: false }), closed: true });
    await heading(1);
    await saved();
    await click("Revoir et valider");
    expect(screen.getByText(/lecture seule. La prochaine une repart vide/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Retirer/ })).not.toBeInTheDocument();
  });
});
