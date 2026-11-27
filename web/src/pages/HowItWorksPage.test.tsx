import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import { renderApp } from "../test/utils";
import { res, stubFetch } from "../test/api-stub";
import type { CurrentEdition } from "../api/types";

afterEach(() => vi.unstubAllGlobals());

const current = (participants = 120): CurrentEdition => ({
  edition: { date: "2026-11-26", published_at: "2026-11-26T16:00:00Z", participants, topics: [] },
  next_close_at: "2026-11-27T16:00:00Z",
  server_time: "2026-11-27T10:00:00Z",
});
const routes = (body: CurrentEdition | (() => Response)) => ({
  "GET /api/me": () => res(401, {}),
  "GET /api/edition/current": typeof body === "function" ? body : () => res(200, body),
});

const SECTION_TITLES = [
  "Le cycle d’une journée",
  "Comment les articles sont regroupés",
  "Comment fonctionne le tirage au hasard",
  "« Récents » et « Sous les radars »",
  "Comment les unes sont agrégées",
  "Pourquoi les compteurs sont cachés pendant la composition",
  "Pourquoi un compte est nécessaire",
  "Ce qui n’existe pas encore",
  "La participation à la dernière édition",
];

describe("Comment ça marche", () => {
  it("titres hiérarchisés : un h1, neuf h2 ancrés, sommaire cliquable", async () => {
    stubFetch(routes(current()));
    renderApp("/comment-ca-marche");
    expect(await screen.findByRole("heading", { level: 1, name: "Comment ça marche" })).toBeInTheDocument();
    const main = screen.getByRole("main");
    const h2 = within(main).getAllByRole("heading", { level: 2 }).filter((h) => h.id.startsWith("t-"));
    expect(h2.map((h) => h.textContent?.replace(/#$/, ""))).toEqual(SECTION_TITLES);
    const toc = within(main).getByRole("navigation", { name: "Sommaire de la page" });
    const links = within(toc).getAllByRole("link");
    expect(links).toHaveLength(9);
    for (const link of links) {
      const id = link.getAttribute("href")!.slice(1);
      expect(main.querySelector(`section#${id}`)).not.toBeNull();
    }
    expect(within(main).getByRole("heading", { level: 3, name: "Sous les radars" })).toBeInTheDocument();
  });

  it("contenu : 17 h Paris, heure locale, 24 h, 2 médias, 3 médias, graine, départage, compteurs, limites", async () => {
    stubFetch(routes(current()));
    renderApp("/comment-ca-marche");
    await screen.findByRole("heading", { level: 1 });
    const text = await screen.findByText(/17 h, heure de Paris/).then(() => screen.getByRole("main").textContent ?? "");
    expect(text).toMatch(/jusqu’à 17 h/i);
    expect(text).toMatch(/dix sujets/);
    expect(text).toMatch(/au moins 2 médias/);
    expect(text).toMatch(/dernières 24 heures/);
    expect(text).toMatch(/graine/);
    expect(text).toMatch(/aucune pondération/i);
    expect(text).toMatch(/trois au plus/);
    expect(text).toMatch(/score/);
    expect(text).toMatch(/plus grand nombre de médias/);
    expect(text).toMatch(/mise à jour est la plus récente/);
    expect(text).toMatch(/ordre fixe/);
    expect(text).toMatch(/aucun compteur n’est visible/);
    expect(text).toMatch(/lien magique/);
    expect(text).toMatch(/Pas de détection avancée de manipulation/);
    expect(text).toMatch(/Pas de thèmes/);
    expect(text).toMatch(/Pas de recherche/);
    // heure locale du lecteur, dérivée de next_close_at
    const local = screen.getByText((_, el) => el?.tagName === "TIME" && el.getAttribute("datetime") === "2026-11-27T16:00:00Z");
    expect(local.textContent).toMatch(/^\d{1,2} h( \d{2})?$/);
  });

  it("participants de la dernière édition et lien vers l’archive", async () => {
    stubFetch(routes(current(1)));
    renderApp("/comment-ca-marche");
    const section = (await screen.findByRole("heading", { level: 2, name: /La participation/ })).closest("section")!;
    expect(await within(section).findByText("1 participant")).toBeInTheDocument();
    expect(within(section).getByRole("link", { name: "26 novembre 2026" })).toHaveAttribute("href", "/une/2026-11-26");
    expect(within(section).getByRole("link", { name: "Voir l’archive des éditions" })).toHaveAttribute("href", "/archives");
  });

  it("pluriel", async () => {
    stubFetch(routes(current(120)));
    renderApp("/comment-ca-marche");
    expect(await screen.findByText("120 participants")).toBeInTheDocument();
  });

  it("aucune édition : le nombre de participants est absent proprement", async () => {
    stubFetch(routes({ edition: null, next_close_at: "2026-11-27T16:00:00Z", server_time: "2026-11-27T10:00:00Z" }));
    renderApp("/comment-ca-marche");
    expect(await screen.findByText(/Aucune une n’a encore été publiée/)).toBeInTheDocument();
    expect(screen.queryByText(/participants?$/)).not.toBeInTheDocument();
    expect(screen.queryByText("undefined")).not.toBeInTheDocument();
  });

  it("API en erreur : la page reste lisible, sans participants ni heure locale", async () => {
    stubFetch(routes(() => res(500, {})));
    renderApp("/comment-ca-marche");
    expect(await screen.findByText(/17 h, heure de Paris/)).toBeInTheDocument();
    await screen.findByText(/Aucune une n’a encore été publiée/);
    expect(screen.getByRole("main").querySelector("time")).toBeNull();
    expect(within(screen.getByRole("main")).getByRole("link", { name: "Composer ma une" })).toHaveAttribute("href", "/composer");
  });
});
