import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { request } from "../../api/client";
import { renderApp } from "../../test/utils";
import { bodiesOf, res, stubFetch } from "../../test/api-stub";

afterEach(() => vi.unstubAllGlobals());

const me401 = () => res(401, { detail: "Authentification administrateur requise" });
const me200 = () => res(200, { authenticated: true });

async function typeAndSubmit(password: string) {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Mot de passe"), password);
  await user.click(screen.getByRole("button", { name: "Se connecter" }));
}

describe("/admin", () => {
  it("affiche la connexion sans session, avec noindex", async () => {
    stubFetch({ "GET /api/admin/me": me401 });
    renderApp("/admin");
    expect(await screen.findByLabelText("Mot de passe")).toHaveAttribute("type", "password");
    expect(document.head.querySelector('meta[name="robots"]')).toHaveAttribute("content", "noindex");
  });

  it("retire le noindex en quittant l’admin", async () => {
    stubFetch({ "GET /api/admin/me": me401 });
    const { unmount } = renderApp("/admin");
    await screen.findByLabelText("Mot de passe");
    unmount();
    expect(document.head.querySelector('meta[name="robots"]')).toBeNull();
  });

  it("connexion réussie : coquille, onglets et déconnexion", async () => {
    let session = false;
    const fn = stubFetch({
      "GET /api/admin/me": () => (session ? me200() : me401()),
      "POST /api/admin/login": () => ((session = true), res(200, { authenticated: true })),
      "POST /api/admin/logout": () => ((session = false), res(204)),
      "GET /api/admin/sources": () => res(200, []),
    });
    renderApp("/admin");
    await typeAndSubmit("le-bon");
    expect(await screen.findByRole("heading", { level: 1, name: "Administration" })).toBeInTheDocument();
    expect(bodiesOf(fn, "POST /api/admin/login")).toEqual([{ password: "le-bon" }]);
    const nav = screen.getByRole("navigation", { name: /administration/i });
    expect(Array.from(nav.querySelectorAll("a")).map((a) => a.textContent)).toEqual([
      "Accueil",
      "Sources",
      "Articles",
      "Sujets",
    ]);

    const user = userEvent.setup();
    await user.click(screen.getByRole("link", { name: "Sources" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Sources" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Déconnexion" }));
    expect(await screen.findByLabelText("Mot de passe")).toBeInTheDocument();
    expect(bodiesOf(fn, "POST /api/admin/logout")).toHaveLength(1);
  });

  it("session déjà valide : pas de formulaire", async () => {
    stubFetch({ "GET /api/admin/me": me200 });
    renderApp("/admin");
    expect(await screen.findByRole("button", { name: "Déconnexion" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Mot de passe")).toBeNull();
  });

  it("mot de passe incorrect : message, champ vidé", async () => {
    stubFetch({
      "GET /api/admin/me": me401,
      "POST /api/admin/login": () => res(401, { detail: "Mot de passe incorrect" }),
    });
    renderApp("/admin");
    await typeAndSubmit("mauvais");
    expect(await screen.findByRole("alert")).toHaveTextContent("Mot de passe incorrect.");
    expect(screen.getByLabelText("Mot de passe")).toHaveValue("");
  });

  it("trop de tentatives : durée lisible", async () => {
    stubFetch({
      "GET /api/admin/me": me401,
      "POST /api/admin/login": () => res(429, { detail: "Trop de tentatives" }, { "Retry-After": "840" }),
    });
    renderApp("/admin");
    await typeAndSubmit("x");
    expect(await screen.findByRole("alert")).toHaveTextContent("Trop de tentatives. Réessayez dans 14 minutes.");
  });

  it("une route admin qui répond 401 ramène à la connexion", async () => {
    stubFetch({
      "GET /api/admin/me": me200,
      "GET /api/admin/sources": me401,
    });
    renderApp("/admin");
    await screen.findByRole("button", { name: "Déconnexion" });
    await expect(request("/admin/sources")).rejects.toMatchObject({ status: 401 });
    expect(await screen.findByLabelText("Mot de passe")).toBeInTheDocument();
  });
});

describe("navigation publique", () => {
  it("ne contient aucun lien vers l’admin", async () => {
    stubFetch({
      "GET /api/me": () => res(401, {}),
      "GET /api/topics/front": () => res(200, { items: [], has_more: false }),
    });
    renderApp("/");
    const nav = await screen.findByRole("navigation", { name: "Navigation principale" });
    expect(nav.querySelector('a[href*="admin"]')).toBeNull();
    expect(document.querySelector('a[href*="admin"]')).toBeNull();
  });
});
