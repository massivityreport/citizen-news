import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderApp } from "../test/utils";
import type { TopicCard } from "../api/types";
import { readLocalVotes, STORAGE_KEY } from "../votes";

const card = (id: number, over: Partial<TopicCard> = {}): TopicCard => ({
  id,
  title: `Sujet ${id}`,
  summary: `Résumé ${id}`,
  image_url: null,
  sources: [{ name: "Le Monde", url: "https://example.org/a", title: "Titre", published_at: new Date().toISOString() }],
  first_seen_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  ...over,
});

interface Opts {
  me?: boolean;
  batches?: TopicCard[][];
  postVote?: () => Response;
}

function stubApi({ me = false, batches = [[card(1), card(2), card(3)]], postVote }: Opts = {}) {
  let next = 0;
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/me") return me ? new Response(JSON.stringify({ email: "a@b.fr" })) : new Response("{}", { status: 401 });
    if (url.startsWith("/api/vote/next")) {
      const items = batches[Math.min(next++, batches.length)] ?? [];
      return new Response(JSON.stringify({ items }));
    }
    if (url === "/api/votes" && init?.method === "POST") {
      return postVote ? postVote() : new Response(init.body as string);
    }
    return new Response("{}", { status: 404 });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

const posts = (fn: ReturnType<typeof stubApi>) =>
  fn.mock.calls.filter(([u, i]) => u === "/api/votes" && i?.method === "POST").map(([, i]) => JSON.parse(i!.body as string));

const choose = (name: RegExp | string) => userEvent.click(screen.getByRole("button", { name }));

beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

describe("Flux de vote /jouer", () => {
  it("propose les trois choix sur une carte, sans résultat ni soutien", async () => {
    stubApi();
    renderApp("/jouer");
    expect(await screen.findByRole("heading", { name: "Sujet 1" })).toBeInTheDocument();
    expect(screen.getByText("Résumé 1")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Le Monde/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Il faut davantage en parler" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ce n’est pas prioritaire" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Je ne sais pas / pas assez d’informations" })).toBeInTheDocument();
    expect(screen.queryByText(/Soutien|votes?\b|%/)).toBeNull();
  });

  it("affiche l'image de la carte du vote et la retire si elle est cassée", async () => {
    stubApi({ me: true, batches: [[card(1, { image_url: "https://img.example.org/v.jpg" }), card(2)]] });
    renderApp("/jouer");
    const img = await screen.findByRole("img", { name: "Illustration : Sujet 1" });
    expect(img).toHaveAttribute("src", "https://img.example.org/v.jpg");
    expect(img).toHaveAttribute("loading", "lazy");
    expect(img).toHaveAttribute("referrerpolicy", "no-referrer");
    fireEvent.error(img);
    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.getByRole("heading", { name: "Sujet 1" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Il faut davantage en parler" })).toBeInTheDocument();
  });

  it.each([
    ["Il faut davantage en parler", "more"],
    ["Ce n’est pas prioritaire", "not_priority"],
    ["Je ne sais pas / pas assez d’informations", "unknown"],
  ] as const)("« %s » enregistre %s, passe au suivant et déplace le focus", async (label, value) => {
    const fn = stubApi({ me: true });
    renderApp("/jouer");
    await screen.findByRole("heading", { name: "Sujet 1" });
    await choose(label);
    const next = await screen.findByRole("heading", { name: "Sujet 2" });
    expect(posts(fn)).toEqual([{ topic_id: 1, choice: value }]);
    await waitFor(() => expect(next).toHaveFocus());
    expect(screen.queryByText(/Soutien|%/)).toBeNull();
  });

  it("précharge le lot suivant quand il reste 3 cartes, avec les sujets déjà vus", async () => {
    const fn = stubApi({ me: true, batches: [[card(1), card(2), card(3), card(4), card(5)], [card(6)]] });
    renderApp("/jouer");
    await screen.findByRole("heading", { name: "Sujet 1" });
    await choose("Il faut davantage en parler");
    await screen.findByRole("heading", { name: "Sujet 2" });
    await choose("Il faut davantage en parler");
    await screen.findByRole("heading", { name: "Sujet 3" });
    await waitFor(() => {
      const urls = fn.mock.calls.map(([u]) => String(u)).filter((u) => u.startsWith("/api/vote/next"));
      expect(urls.length).toBe(2);
      expect(decodeURIComponent(urls[1])).toContain("seen=1,2,3,4,5");
      expect(urls[0]).toContain("count=10");
    });
  });

  it("affiche le message de fin puis permet de modifier le dernier vote", async () => {
    const fn = stubApi({ me: true, batches: [[card(1)]] });
    renderApp("/jouer");
    await screen.findByRole("heading", { name: "Sujet 1" });
    await choose("Il faut davantage en parler");
    const end = await screen.findByRole("heading", { name: /tout évalué/ });
    await waitFor(() => expect(end).toHaveFocus());
    await choose(/Revenir au dernier sujet/);
    expect(await screen.findByRole("heading", { name: "Sujet 1" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Il faut davantage en parler/ })).toHaveAttribute("aria-pressed", "true");
    await choose("Ce n’est pas prioritaire");
    await screen.findByRole("heading", { name: /tout évalué/ });
    expect(posts(fn)).toEqual([
      { topic_id: 1, choice: "more" },
      { topic_id: 1, choice: "not_priority" },
    ]);
  });

  it("revient à la carte précédente pour modifier un vote (anonyme : le dernier remplace)", async () => {
    stubApi();
    renderApp("/jouer");
    await screen.findByRole("heading", { name: "Sujet 1" });
    expect(screen.getByRole("button", { name: /Revenir au sujet précédent/ })).toBeDisabled();
    await choose("Il faut davantage en parler");
    await screen.findByRole("heading", { name: "Sujet 2" });
    await choose(/Revenir au sujet précédent/);
    await screen.findByRole("heading", { name: "Sujet 1" });
    await choose("Ce n’est pas prioritaire");
    await screen.findByRole("heading", { name: "Sujet 2" });
    expect(readLocalVotes()).toEqual([{ topic_id: 1, choice: "not_priority" }]);
  });

  describe("sans compte", () => {
    it("garde les votes dans le navigateur et affiche la bannière après le 1er vote", async () => {
      const fn = stubApi();
      renderApp("/jouer");
      await screen.findByRole("heading", { name: "Sujet 1" });
      expect(screen.queryByRole("link", { name: /Créer un compte/ })).toBeNull();
      await choose("Il faut davantage en parler");
      await screen.findByRole("heading", { name: "Sujet 2" });
      expect(screen.getByRole("link", { name: "Créer un compte pour enregistrer vos choix" })).toHaveAttribute("href", "/connexion");
      await choose("Je ne sais pas / pas assez d’informations");
      await screen.findByRole("heading", { name: "Sujet 3" });
      expect(posts(fn)).toEqual([]);
      expect(readLocalVotes()).toEqual([
        { topic_id: 1, choice: "more" },
        { topic_id: 2, choice: "unknown" },
      ]);
      expect(Object.keys(JSON.parse(localStorage.getItem(STORAGE_KEY)!)[0]).sort()).toEqual(["choice", "topic_id"]);
    });

    it("n'affiche pas la bannière pour un utilisateur connecté", async () => {
      stubApi({ me: true });
      renderApp("/jouer");
      await screen.findByRole("heading", { name: "Sujet 1" });
      await choose("Il faut davantage en parler");
      await screen.findByRole("heading", { name: "Sujet 2" });
      expect(screen.queryByRole("link", { name: /Créer un compte/ })).toBeNull();
      expect(readLocalVotes()).toEqual([]);
    });

    it("bascule en anonyme si POST /votes répond 401, sans perdre le vote", async () => {
      stubApi({ me: true, postVote: () => new Response("{}", { status: 401 }) });
      renderApp("/jouer");
      await screen.findByRole("heading", { name: "Sujet 1" });
      await choose("Il faut davantage en parler");
      await screen.findByRole("heading", { name: "Sujet 2" });
      expect(readLocalVotes()).toEqual([{ topic_id: 1, choice: "more" }]);
      expect(await screen.findByRole("link", { name: /Créer un compte/ })).toBeInTheDocument();
    });

    it("continue de voter quand le stockage local est indisponible", async () => {
      stubApi();
      vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
        throw new Error("denied");
      });
      vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
        throw new Error("denied");
      });
      renderApp("/jouer");
      await screen.findByRole("heading", { name: "Sujet 1" });
      await choose("Il faut davantage en parler");
      expect(await screen.findByRole("heading", { name: "Sujet 2" })).toBeInTheDocument();
      expect(screen.getByRole("alert")).toHaveTextContent(/ne permet pas de conserver/);
      vi.restoreAllMocks();
    });

    it("ignore une liste locale corrompue", async () => {
      localStorage.setItem(STORAGE_KEY, "{pas du json");
      stubApi();
      renderApp("/jouer");
      expect(await screen.findByRole("heading", { name: "Sujet 1" })).toBeInTheDocument();
      expect(readLocalVotes()).toEqual([]);
    });
  });

  it("429 : message poli avec le délai, la carte reste et on peut réessayer", async () => {
    let n = 0;
    const fn = stubApi({
      me: true,
      postVote: () => (++n === 1 ? new Response("{}", { status: 429, headers: { "Retry-After": "7" } }) : new Response("{}")),
    });
    renderApp("/jouer");
    await screen.findByRole("heading", { name: "Sujet 1" });
    await choose("Il faut davantage en parler");
    expect(await screen.findByRole("alert")).toHaveTextContent(/patienter 7 secondes/);
    expect(screen.getByRole("heading", { name: "Sujet 1" })).toBeInTheDocument();
    await choose("Il faut davantage en parler");
    await screen.findByRole("heading", { name: "Sujet 2" });
    expect(posts(fn)).toHaveLength(2);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("deux clics synchrones n'envoient qu'un seul vote", async () => {
    const fn = stubApi({ me: true });
    renderApp("/jouer");
    await screen.findByRole("heading", { name: "Sujet 1" });
    const btn = screen.getByRole("button", { name: "Il faut davantage en parler" });
    act(() => {
      btn.click();
      btn.click();
    });
    await screen.findByRole("heading", { name: "Sujet 2" });
    expect(posts(fn)).toEqual([{ topic_id: 1, choice: "more" }]);
  });

  it("GET /api/me en erreur 500 : le vote est conservé localement, le flux continue", async () => {
    vi.stubGlobal("fetch", async (url: string) => {
      if (url === "/api/me") return new Response("{}", { status: 500 });
      if (url.startsWith("/api/vote/next")) return new Response(JSON.stringify({ items: [card(1), card(2)] }));
      return new Response("{}", { status: 404 });
    });
    renderApp("/jouer");
    await screen.findByRole("heading", { name: "Sujet 1" });
    await choose("Il faut davantage en parler");
    expect(await screen.findByRole("heading", { name: "Sujet 2" })).toBeInTheDocument();
    expect(readLocalVotes()).toEqual([{ topic_id: 1, choice: "more" }]);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("propose de réessayer si le chargement échoue", async () => {
    let calls = 0;
    vi.stubGlobal("fetch", async (url: string) => {
      if (url === "/api/me") return new Response("{}", { status: 401 });
      return ++calls === 1 ? new Response("{}", { status: 500 }) : new Response(JSON.stringify({ items: [card(1)] }));
    });
    renderApp("/jouer");
    expect(await screen.findByRole("alert")).toHaveTextContent(/Impossible de charger/);
    await userEvent.click(screen.getByRole("button", { name: "Réessayer" }));
    expect(await screen.findByRole("heading", { name: "Sujet 1" })).toBeInTheDocument();
  });
});
