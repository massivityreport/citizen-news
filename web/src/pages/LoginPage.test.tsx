import { draftStore } from "../lib/draftStore";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation } from "react-router-dom";
import { AppRoutes } from "../App";
import { bodiesOf, res, stubFetch, type Handler } from "../test/api-stub";
import { uneKey } from "../api/hooks";
import { makeQueryClient } from "../test/utils";

const EMAIL = "marie@example.org";

function Probe() {
  const l = useLocation();
  return <output data-testid="loc">{l.pathname + l.search}</output>;
}

function renderLogin(route = "/connexion", strict = false) {
  const ui = (
    <QueryClientProvider client={makeQueryClient()}>
      <MemoryRouter initialEntries={[route]}>
        <AppRoutes />
        <Probe />
      </MemoryRouter>
    </QueryClientProvider>
  );
  return render(strict ? <StrictMode>{ui}</StrictMode> : ui);
}

/** API avec une session qui s'ouvre sur verify et se ferme sur logout. */
function session(extra: Record<string, Handler> = {}, connected = false) {
  let on = connected;
  return stubFetch({
    "GET /api/me": () => (on ? res(200, { email: EMAIL }) : res(401, {})),
    "POST /api/auth/verify": () => {
      on = true;
      return res(200, { email: EMAIL });
    },
    "POST /api/auth/logout": () => {
      on = false;
      return res(204);
    },
    ...extra,
  });
}

const main = () => within(screen.getByRole("main"));

beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

describe("Formulaire de connexion", () => {
  it("202 : message neutre, e-mail non stocké", async () => {
    const fn = session({ "POST /api/auth/magic-link": () => res(202) });
    renderLogin();
    await userEvent.type(await screen.findByLabelText("Adresse e-mail"), EMAIL);
    await userEvent.click(screen.getByRole("button", { name: "Recevoir un lien de connexion" }));
    const status = await screen.findByText("Si cette adresse est valide, un lien de connexion vient de partir. Il est valable peu de temps.");
    expect(status).toHaveAttribute("role", "status");
    await waitFor(() => expect(status).toHaveFocus());
    expect(bodiesOf(fn, "POST /api/auth/magic-link")).toEqual([{ email: EMAIL }]);
    expect(JSON.stringify({ ...localStorage, ...sessionStorage })).not.toContain("marie");
  });

  it("refuse une adresse mal formée sans appeler l'API et replace le focus", async () => {
    const fn = session();
    renderLogin();
    await userEvent.type(await screen.findByLabelText("Adresse e-mail"), "pas-un-email");
    await userEvent.click(screen.getByRole("button", { name: /Recevoir/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/adresse e-mail valide/);
    expect(screen.getByLabelText("Adresse e-mail")).toHaveFocus();
    expect(screen.getByLabelText("Adresse e-mail")).toBeInvalid();
    expect(bodiesOf(fn, "POST /api/auth/magic-link")).toEqual([]);
  });

  it("422 : message sur le champ", async () => {
    session({ "POST /api/auth/magic-link": () => res(422, { detail: "x" }) });
    renderLogin();
    await userEvent.type(await screen.findByLabelText("Adresse e-mail"), EMAIL);
    await userEvent.click(screen.getByRole("button", { name: /Recevoir/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/n’est pas valide/);
    expect(screen.getByLabelText("Adresse e-mail")).toHaveAccessibleDescription(/n’est pas valide/);
  });

  it("429 : message avec le délai, bouton désactivé puis réactivé", async () => {
    session({ "POST /api/auth/magic-link": () => res(429, {}, { "Retry-After": "1" }) });
    renderLogin();
    await userEvent.type(await screen.findByLabelText("Adresse e-mail"), EMAIL);
    await userEvent.click(screen.getByRole("button", { name: /Recevoir/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("patienter 1 seconde");
    expect(screen.getByRole("button", { name: /Réessayer dans/ })).toBeDisabled();
    await waitFor(() => expect(screen.getByRole("button", { name: "Recevoir un lien de connexion" })).toBeEnabled(), { timeout: 3000 });
  });
});

describe("Vérification du lien", () => {
  it("succès : verify, token retiré de l'URL, e-mail dans l'en-tête, retour vers /composer", async () => {
    const fn = session();
    renderLogin("/connexion?token=secret123");
    expect(await screen.findByText("Vous êtes connecté·e.")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("loc")).toHaveTextContent(/^\/connexion$/));
    expect(bodiesOf(fn, "POST /api/auth/verify")).toEqual([{ token: "secret123" }]);
    expect(within(screen.getByRole("banner")).getByText(EMAIL)).toBeInTheDocument();
    expect(JSON.stringify({ ...localStorage })).not.toContain("secret123");
    await userEvent.click(screen.getByRole("link", { name: "Continuer" }));
    await waitFor(() => expect(screen.getByTestId("loc")).toHaveTextContent("/composer"));
  });

  it("brouillon fusionné par le serveur : le message l'indique", async () => {
    session({ "POST /api/auth/verify": () => res(200, { email: EMAIL, draft: { added: 2, ignored: 1 } }) });
    renderLogin("/connexion?token=t");
    expect(await screen.findByText(/2 sujets ont été ajoutés à votre une\./)).toBeInTheDocument();
    expect(screen.getByText(/1 autre sujet a été ignoré/)).toBeInTheDocument();
  });

  it("brouillon fusionné : le brouillon local n'est pas perdu (la fusion se fait sur /composer)", async () => {
    draftStore.set({ editionDate: "2026-11-27", ids: [4, 5, 8] });
    session({ "POST /api/auth/verify": () => res(200, { email: EMAIL, draft: { added: 2, ignored: 0 } }) });
    renderLogin("/connexion?token=t");
    await screen.findByText(/2 sujets ont été ajoutés/);
    expect(draftStore.get().ids).toEqual([4, 5, 8]);
  });

  it("oublie la une en cache (autre compte) à la connexion", async () => {
    const client = makeQueryClient();
    client.setQueryData(uneKey, { edition_date: "2026-11-27", closes_at: "x", open: true, topic_ids: [1] });
    session({ "POST /api/auth/verify": () => res(200, { email: EMAIL, draft: null }) });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/connexion?token=t"]}>
          <AppRoutes />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await screen.findByText("Vous êtes connecté·e.");
    expect(client.getQueryData(uneKey)).toBeUndefined();
  });

  it("sans brouillon joint : le brouillon local reste (fusion proposée sur /composer)", async () => {
    draftStore.set({ editionDate: "2026-11-27", ids: [4] });
    session({ "POST /api/auth/verify": () => res(200, { email: EMAIL, draft: null }) });
    renderLogin("/connexion?token=t");
    await screen.findByText("Vous êtes connecté·e.");
    expect(draftStore.get().ids).toEqual([4]);
  });

  it("400 : message « lien plus valable » et formulaire", async () => {
    session({ "POST /api/auth/verify": () => res(400, { detail: "x" }) });
    renderLogin("/connexion?token=vieux");
    expect(await screen.findByRole("alert")).toHaveTextContent("Ce lien n’est plus valable : demandez-en un nouveau.");
    expect(screen.getByLabelText("Adresse e-mail")).toBeInTheDocument();
    expect(screen.getByTestId("loc")).toHaveTextContent(/^\/connexion$/);
  });

  it("déjà connecté avec un lien invalide : message affiché dans la vue connectée", async () => {
    session({ "POST /api/auth/verify": () => res(400, { detail: "x" }) }, true);
    renderLogin("/connexion?token=vieux");
    expect(await screen.findByRole("alert")).toHaveTextContent("Ce lien n’est plus valable : demandez-en un nouveau.");
    expect(await main().findByText(EMAIL)).toBeInTheDocument();
    expect(main().getByRole("button", { name: "Se déconnecter" })).toBeInTheDocument();
    expect(screen.getByTestId("loc")).toHaveTextContent(/^\/connexion$/);
  });

  it("n'appelle verify qu'une fois en StrictMode (jeton à usage unique)", async () => {
    const fn = session();
    renderLogin("/connexion?token=unique", true);
    await screen.findByText("Vous êtes connecté·e.");
    expect(bodiesOf(fn, "POST /api/auth/verify")).toHaveLength(1);
  });

  it("redirige vers /composer après le message", async () => {
    session();
    renderLogin("/connexion?token=t");
    await screen.findByText("Vous êtes connecté·e.");
    await waitFor(() => expect(screen.getByTestId("loc")).toHaveTextContent("/composer"), { timeout: 4000 });
  });
});

describe("Session", () => {
  it("déjà connecté : affiche l'e-mail, et « Se déconnecter » appelle logout", async () => {
    const fn = session({}, true);
    renderLogin();
    expect(await main().findByText(EMAIL)).toBeInTheDocument();
    await userEvent.click(main().getByRole("button", { name: "Se déconnecter" }));
    expect(await main().findByLabelText("Adresse e-mail")).toBeInTheDocument();
    expect(bodiesOf(fn, "POST /api/auth/logout")).toHaveLength(1);
    expect(within(screen.getByRole("banner")).getByRole("link", { name: "Se connecter" })).toBeInTheDocument();
  });
});
