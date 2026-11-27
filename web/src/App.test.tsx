import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderApp } from "./test/utils";

function stubMe(email: string | null) {
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/me") {
      return email
        ? new Response(JSON.stringify({ email }), { status: 200 })
        : new Response(JSON.stringify({ detail: "Non connecté" }), { status: 401 });
    }
    if (url === "/api/auth/logout" && init?.method === "POST") return new Response(null, { status: 204 });
    return new Response("{}", { status: 404 });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

beforeEach(() => stubMe(null));
afterEach(() => vi.unstubAllGlobals());

describe("routage", () => {
  it.each([
    ["/", "La une citoyenne"],
    ["/composer", "Composer ma une"],
    ["/jouer", "Composer ma une"],
    ["/archives", "Archives"],
    ["/comment-ca-marche", "Comment ça marche"],
    ["/connexion", "Se connecter"],
  ])("%s affiche le titre « %s »", async (route, title) => {
    renderApp(route);
    expect(await screen.findByRole("heading", { level: 1, name: title })).toBeInTheDocument();
  });

  it("affiche une 404 pour une route inconnue", async () => {
    renderApp("/nimporte-quoi");
    expect(await screen.findByRole("heading", { level: 1, name: /page introuvable/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /retour à la une/i })).toHaveAttribute("href", "/");
  });
});

describe("layout", () => {
  it("expose les landmarks et la navigation principale ", async () => {
    renderApp("/");
    expect(screen.getByRole("banner")).toBeInTheDocument();
    expect(screen.getByRole("main")).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: /principale/i });
    const labels = within(nav).getAllByRole("link").map((l) => l.textContent);
    expect(labels).toEqual(["Accueil", "Composer", "Archives", "Comment ça marche"]);
    expect(screen.queryByText(/explorer/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/proposer/i)).not.toBeInTheDocument();
  });

  it("propose un lien d'évitement vers le contenu", async () => {
    renderApp("/");
    expect(screen.getByRole("link", { name: /aller au contenu/i })).toHaveAttribute("href", "#contenu");
  });

  it("affiche le bouton fixe « Composer ma une » vers /composer", async () => {
    renderApp("/");
    const fixed = document.querySelector("[data-testid='fixed-cta']") as HTMLElement;
    expect(fixed).toHaveAttribute("href", "/composer");
    expect(fixed.textContent).toBe("Composer ma une");
  });

  it("masque le bouton fixe sur /composer", async () => {
    renderApp("/composer");
    expect(document.querySelector("[data-testid='fixed-cta']")).toBeNull();
  });

  it("marque le lien actif avec aria-current", async () => {
    renderApp("/comment-ca-marche");
    const nav = screen.getByRole("navigation", { name: /principale/i });
    expect(within(nav).getByRole("link", { name: "Comment ça marche" })).toHaveAttribute("aria-current", "page");
  });
});

describe("zone compte", () => {
  it("propose « Se connecter » sans session", async () => {
    renderApp("/");
    const link = await screen.findByRole("link", { name: "Se connecter", description: "" });
    expect(link).toHaveAttribute("href", "/connexion");
  });

  it("affiche l'email et « Se déconnecter » avec session", async () => {
    stubMe("camille@example.org");
    renderApp("/");
    expect(await screen.findByText("camille@example.org")).toBeInTheDocument();
    const btn = screen.getByRole("button", { name: "Se déconnecter" });
    await userEvent.click(btn);
    expect(await screen.findByRole("link", { name: "Se connecter" })).toBeInTheDocument();
  });
});
