import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { bodiesOf, res, stubFetch } from "../test/api-stub";
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
