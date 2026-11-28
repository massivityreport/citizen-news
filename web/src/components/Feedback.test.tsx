import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { bodiesOf, res, stubFetch } from "../test/api-stub";
import { journal } from "../lib/journal";
import { renderApp } from "../test/utils";

type Stub = ReturnType<typeof stubFetch>;

function setup(email: string | null, feedback: () => Response = () => res(201, {})): Stub {
  return stubFetch({
    "GET /api/me": () => (email ? res(200, { email }) : res(401, { detail: "Non connecté" })),
    "GET /api/admin/me": () => res(401, { detail: "Authentification administrateur requise" }),
    "POST /api/feedback": feedback,
  });
}

afterEach(() => vi.unstubAllGlobals());

async function openForm() {
  const tab = await screen.findByTestId("feedback-tab");
  await userEvent.click(within(tab).getByRole("button", { name: "Votre avis" }));
}
const dialog = () => screen.findByRole("dialog", { name: "Votre avis" });

describe("onglet et lien d'en-tête", () => {
  beforeEach(() => {
    setup(null);
  });

  it("affiche l'onglet sur les pages publiques et le lien dans l'en-tête", async () => {
    renderApp("/archives");
    expect(await screen.findByTestId("feedback-tab")).toBeInTheDocument();
    expect(within(screen.getByRole("banner")).getByRole("button", { name: "Votre avis" })).toBeInTheDocument();
  });

  it("n'apparaît pas dans le backoffice", async () => {
    renderApp("/admin");
    await screen.findByRole("heading", { level: 1 });
    expect(screen.queryByTestId("feedback-tab")).toBeNull();
    expect(screen.queryByRole("button", { name: "Votre avis" })).toBeNull();
  });

  it("la croix masque l'onglet pour la visite, le lien d'en-tête reste", async () => {
    renderApp("/archives");
    await userEvent.click(await screen.findByRole("button", { name: "Masquer l'onglet Votre avis" }));
    expect(screen.queryByTestId("feedback-tab")).toBeNull();
    expect(window.sessionStorage.getItem("cn.feedbackTabHidden")).toBe("1");
    expect(within(screen.getByRole("banner")).getByRole("button", { name: "Votre avis" })).toBeInTheDocument();
  });

  it("reste masqué si la visite l'a déjà masqué, et le lien ouvre quand même le formulaire", async () => {
    window.sessionStorage.setItem("cn.feedbackTabHidden", "1");
    renderApp("/archives");
    await screen.findByRole("banner");
    expect(screen.queryByTestId("feedback-tab")).toBeNull();
    await userEvent.click(within(screen.getByRole("banner")).getByRole("button", { name: "Votre avis" }));
    expect(await dialog()).toBeInTheDocument();
  });

  it("garde le bouton fixe « Composer ma une » à sa place", async () => {
    renderApp("/archives");
    await screen.findByTestId("feedback-tab");
    expect(document.querySelector("[data-testid='fixed-cta']")).not.toBeNull();
  });
});

describe("formulaire", () => {
  it("non connecté : e-mail obligatoire, type « Autre » par défaut, envoi puis remerciement", async () => {
    const fetchMock = setup(null);
    renderApp("/archives");
    await openForm();
    const d = await dialog();
    expect(within(d).getByRole("radio", { name: "Autre" })).toBeChecked();
    expect(within(d).getAllByRole("radio").map((r) => (r as HTMLInputElement).labels?.[0].textContent)).toEqual(["Problème", "Idée", "Autre"]);

    await userEvent.click(within(d).getByRole("radio", { name: "Idée" }));
    await userEvent.type(within(d).getByLabelText("Votre message"), "Une idée");
    await userEvent.type(within(d).getByLabelText("Adresse e-mail"), "visiteur@example.org");
    await userEvent.click(within(d).getByRole("button", { name: "Envoyer" }));

    expect(await screen.findByText(/merci/i)).toBeInTheDocument();
    const [body] = bodiesOf(fetchMock, "POST /api/feedback");
    expect(body).toMatchObject({ kind: "idea", message: "Une idée", email: "visiteur@example.org", page_url: "/archives" });
    expect(body.screen).toMatch(/^\d+x\d+$/);
    expect(typeof body.page_name).toBe("string");

    await userEvent.click(screen.getByRole("button", { name: "Fermer" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("la page de l'avis part sans ses paramètres d'URL", async () => {
    const fetchMock = setup(null);
    renderApp("/archives?q=secret#haut");
    await openForm();
    const d = await dialog();
    await userEvent.type(within(d).getByLabelText("Votre message"), "Un souci");
    await userEvent.type(within(d).getByLabelText("Adresse e-mail"), "visiteur@example.org");
    await userEvent.click(within(d).getByRole("button", { name: "Envoyer" }));
    expect(await screen.findByText(/merci/i)).toBeInTheDocument();
    const [body] = bodiesOf(fetchMock, "POST /api/feedback");
    expect(body.page_url).toBe("/archives");
  });

  it("connecté : adresse affichée, aucun champ e-mail, rien d'envoyé côté client", async () => {
    const fetchMock = setup("moi@example.org");
    renderApp("/archives");
    await openForm();
    const d = await dialog();
    expect(await within(d).findByText("moi@example.org")).toBeInTheDocument();
    expect(within(d).queryByLabelText("Adresse e-mail")).toBeNull();
    await userEvent.type(within(d).getByLabelText("Votre message"), "Bonjour");
    await userEvent.click(within(d).getByRole("button", { name: "Envoyer" }));
    await screen.findByText(/merci/i);
    expect(bodiesOf(fetchMock, "POST /api/feedback")[0]).not.toHaveProperty("email");
  });

  it("refuse un e-mail invalide et un message vide sans appeler le serveur", async () => {
    const fetchMock = setup(null);
    renderApp("/archives");
    await openForm();
    const d = await dialog();
    await userEvent.click(within(d).getByRole("button", { name: "Envoyer" }));
    expect(await within(d).findAllByRole("alert")).not.toHaveLength(0);
    await userEvent.type(within(d).getByLabelText("Votre message"), "x");
    await userEvent.type(within(d).getByLabelText("Adresse e-mail"), "pas-un-email");
    await userEvent.click(within(d).getByRole("button", { name: "Envoyer" }));
    expect(within(d).getByLabelText("Adresse e-mail")).toHaveAttribute("aria-invalid", "true");
    expect(bodiesOf(fetchMock, "POST /api/feedback")).toHaveLength(0);
  });

  it("limite le message à 2000 caractères", async () => {
    setup("moi@example.org");
    renderApp("/archives");
    await openForm();
    expect(within(await dialog()).getByLabelText("Votre message")).toHaveAttribute("maxlength", "2000");
  });

  it("limite d'envois : message « réessayer plus tard », le formulaire reste ouvert", async () => {
    setup("moi@example.org", () => res(429, { detail: "Trop de tentatives, réessayez plus tard" }, { "Retry-After": "60" }));
    renderApp("/archives");
    await openForm();
    const d = await dialog();
    await userEvent.type(within(d).getByLabelText("Votre message"), "Bonjour");
    await userEvent.click(within(d).getByRole("button", { name: "Envoyer" }));
    expect(await within(d).findByRole("alert")).toHaveTextContent(/réessayez plus tard/i);
    expect(within(d).getByLabelText("Votre message")).toHaveValue("Bonjour");
  });

  it("n'interprète pas le HTML saisi et se ferme avec Échap", async () => {
    setup("moi@example.org");
    renderApp("/archives");
    await openForm();
    const d = await dialog();
    await userEvent.type(within(d).getByLabelText("Votre message"), "<b>gras</b>", { skipClick: false });
    expect(d.querySelector("b")).toBeNull();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

describe("parcours récent", () => {
  const CASE = "Joindre mon parcours récent";

  it("le journal suit les pages ouvertes, sans les paramètres d'URL, avec l'heure", async () => {
    setup(null);
    renderApp("/archives?q=secret");
    await screen.findByRole("banner");
    await userEvent.click(within(screen.getByRole("navigation", { name: "Navigation principale" })).getByRole("link", { name: "Comment ça marche" }));
    await screen.findByRole("heading", { level: 1, name: /Comment/ });
    const pages = journal.get().filter((a) => a.type === "page");
    expect(pages.map((a) => a.page)).toEqual(["/archives", "/comment-ca-marche"]);
    expect(Date.parse(pages[0].at)).not.toBeNaN();
  });

  it("le backoffice n'entre pas au journal", async () => {
    setup(null);
    renderApp("/admin");
    await screen.findByRole("heading", { level: 1 });
    expect(journal.get()).toEqual([]);
  });

  it("case cochée par défaut, avec la phrase qui informe", async () => {
    setup(null);
    renderApp("/archives");
    await openForm();
    const d = await dialog();
    expect(within(d).getByRole("checkbox", { name: CASE })).toBeChecked();
    expect(within(d).getByText(/parcours récent.*joint à votre avis/i)).toBeInTheDocument();
  });

  it("cochée : les actions de la visite partent avec l'avis (20 au plus)", async () => {
    const fetchMock = setup("moi@example.org");
    for (let i = 0; i < 25; i++) journal.record({ type: "page", page: `/p${i}` });
    renderApp("/archives");
    await openForm();
    const d = await dialog();
    await userEvent.type(within(d).getByLabelText("Votre message"), "Bonjour");
    await userEvent.click(within(d).getByRole("button", { name: "Envoyer" }));
    await screen.findByText(/merci/i);
    const [body] = bodiesOf(fetchMock, "POST /api/feedback");
    expect(body.recent_actions).toHaveLength(20);
    expect(body.recent_actions.at(-1)).toMatchObject({ type: "page", page: "/archives" });
    expect(body.recent_actions[0]).toMatchObject({ page: "/p6" });
  });

  it("décochée : rien du parcours n'est envoyé", async () => {
    const fetchMock = setup("moi@example.org");
    journal.record({ type: "login" });
    renderApp("/archives");
    await openForm();
    const d = await dialog();
    await userEvent.click(within(d).getByRole("checkbox", { name: CASE }));
    expect(within(d).getByRole("checkbox", { name: CASE })).not.toBeChecked();
    await userEvent.type(within(d).getByLabelText("Votre message"), "Bonjour");
    await userEvent.click(within(d).getByRole("button", { name: "Envoyer" }));
    await screen.findByText(/merci/i);
    const [body] = bodiesOf(fetchMock, "POST /api/feedback");
    expect(body).not.toHaveProperty("recent_actions");
    expect(JSON.stringify(body)).not.toContain("login");
  });

  it("hors avis, le parcours ne part jamais : aucun appel réseau tant que l'avis n'est pas envoyé", async () => {
    const fetchMock = setup("moi@example.org");
    renderApp("/archives");
    await openForm();
    await dialog();
    await userEvent.keyboard("{Escape}");
    await userEvent.click(within(screen.getByRole("banner")).getByRole("button", { name: "Votre avis" }));
    await userEvent.click(within(await dialog()).getByRole("button", { name: "Annuler" }));
    const sent = fetchMock.mock.calls.filter(([, i]) => i?.method && i.method !== "GET");
    expect(sent).toEqual([]);
    expect(JSON.stringify(fetchMock.mock.calls)).not.toContain("recent_actions");
  });
});
