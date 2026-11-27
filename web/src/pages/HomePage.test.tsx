import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderApp } from "../test/utils";
import { res, stubFetch } from "../test/api-stub";
import type { CurrentEdition, Edition, EditionTopic } from "../api/types";

const NOW = "2026-11-27T10:00:00Z";
const CLOSE = "2026-11-27T16:00:00Z";

const topic = (over: Partial<EditionTopic> = {}): EditionTopic => ({
  rank: 1,
  topic_id: 12,
  title: "Pénurie de médecins",
  summary: "Des délais de trois mois.",
  sources: [
    { name: "Le Monde", url: "https://example.org/a", title: "Titre A", published_at: "2026-11-26T09:00:00Z" },
    { name: "Piégé", url: "javascript:alert(1)", title: "x", published_at: "2026-11-26T09:00:00Z" },
  ],
  source_count: 5,
  article_count: 9,
  approvals: 80,
  proportion: 0.667,
  image_url: null,
  ...over,
});

const edition = (over: Partial<Edition> = {}): Edition => ({
  date: "2026-11-26",
  published_at: "2026-11-26T16:00:00Z",
  participants: 120,
  topics: [topic(), topic({ rank: 2, topic_id: 7, title: "Budget", approvals: 1, proportion: 1 / 120, source_count: 1 })],
  ...over,
});

const current = (e: Edition | null, next = CLOSE, server = NOW): CurrentEdition => ({
  edition: e,
  next_close_at: next,
  server_time: server,
});

const stub = (body: CurrentEdition) =>
  stubFetch({ "GET /api/me": () => res(401, {}), "GET /api/edition/current": () => res(200, body) });

afterEach(() => vi.unstubAllGlobals());

describe("Accueil : la une publiée", () => {
  it("affiche publication, participants, lien permanent et les sujets", async () => {
    stub(current(edition()));
    renderApp("/");
    expect(await screen.findByRole("heading", { level: 1, name: "La une citoyenne" })).toBeInTheDocument();
    const articles = await screen.findAllByRole("article");
    expect(articles).toHaveLength(2);
    expect(screen.getByText(/Publiée le/)).toHaveTextContent(/26 novembre 2026 à \d{2}:\d{2}/);
    expect(screen.getByText(/120 participants/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /\/une\/2026-11-26$/ })).toHaveAttribute("href", "/une/2026-11-26");
    expect(document.title).toBe("La une citoyenne du 26 novembre 2026 — Citizen News");
    // titres : h1 puis h2 par sujet
    expect(screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent)).toEqual(["Pénurie de médecins", "Budget"]);
  });

  it("une carte : rang, résumé, proportion, médias, articles, approbations, sources", async () => {
    stub(current(edition()));
    renderApp("/");
    const card = await screen.findByRole("article", { name: "Pénurie de médecins" });
    expect(within(card).getByText("Sujet n° 1")).toBeInTheDocument();
    expect(within(card).getByText("Des délais de trois mois.")).toBeInTheDocument();
    expect(within(card).getByText("67 % des unes")).toBeInTheDocument();
    expect(within(card).getByText(/80 approbations/)).toBeInTheDocument();
    expect(within(card).getByText(/5 médias · 9 articles/)).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: /Le Monde/ })).toHaveAttribute("href", "https://example.org/a");
    expect(within(card).queryByRole("link", { name: /Piégé/ })).toBeNull();
    const second = screen.getByRole("article", { name: "Budget" });
    expect(within(second).getByText(/1 média · /)).toBeInTheDocument();
    expect(within(second).getByText(/1 approbation$/)).toBeInTheDocument();
  });

  it("image en hotlink sans referrer, retirée proprement si elle ne charge pas", async () => {
    stub(current(edition({ topics: [topic({ image_url: "https://img.example.org/a.jpg" }), topic({ rank: 2 })] })));
    renderApp("/");
    const card = (await screen.findAllByRole("article"))[0];
    const img = within(card).getByRole("img", { name: "Illustration : Pénurie de médecins" });
    expect(img).toHaveAttribute("referrerpolicy", "no-referrer");
    expect(within(screen.getAllByRole("article")[1]).queryByRole("img")).toBeNull();
    fireEvent.error(img);
    expect(within(card).queryByRole("img")).toBeNull();
    expect(within(card).getByRole("heading", { name: "Pénurie de médecins" })).toBeInTheDocument();
  });

  it("bouton principal « Composer ma une » vers /composer", async () => {
    stub(current(edition()));
    renderApp("/");
    const links = await screen.findAllByRole("link", { name: "Composer ma une" });
    expect(links.every((l) => l.getAttribute("href") === "/composer")).toBe(true);
  });

  it("édition null : message de première une et compte à rebours", async () => {
    stub(current(null));
    renderApp("/");
    expect(await screen.findByText(/^La première une sera publiée à \d{2}:\d{2}\.$/)).toBeInTheDocument();
    expect(screen.getByTestId("countdown")).toBeInTheDocument();
    expect(screen.queryByRole("article")).toBeNull();
  });

  it("édition sans sujet : message honnête", async () => {
    stub(current(edition({ participants: 0, topics: [] })));
    renderApp("/");
    expect(await screen.findByText(/Personne n’a encore composé de une/)).toBeInTheDocument();
    expect(screen.getByText(/0 participant\b/)).toBeInTheDocument();
    expect(screen.queryByRole("article")).toBeNull();
  });

  it("propose de réessayer après une erreur", async () => {
    let calls = 0;
    stubFetch({
      "GET /api/me": () => res(401, {}),
      "GET /api/edition/current": () => (++calls === 1 ? res(500, {}) : res(200, current(edition()))),
    });
    renderApp("/");
    expect(await screen.findByRole("alert")).toHaveTextContent(/Impossible de charger/);
    await userEvent.click(screen.getByRole("button", { name: "Réessayer" }));
    expect(await screen.findByRole("article", { name: "Pénurie de médecins" })).toBeInTheDocument();
  });
});

describe("Compte à rebours", () => {
  beforeEach(() => vi.useFakeTimers({ toFake: ["Date", "setInterval", "clearInterval"], now: new Date(NOW) }));
  afterEach(() => vi.useRealTimers());

  async function load(body: CurrentEdition) {
    stub(body);
    renderApp("/");
    // fetch/Promise réels : on laisse la file de micro-tâches se vider sans horloge fausse sur setTimeout
    await vi.waitFor(() => expect(screen.getByTestId("countdown")).toBeInTheDocument());
  }

  it("décompte à la seconde", async () => {
    await load(current(edition()));
    expect(screen.getByTestId("countdown")).toHaveTextContent("6 h 00 min 00 s");
    act(() => vi.advanceTimersByTime(1000));
    expect(screen.getByTestId("countdown")).toHaveTextContent("5 h 59 min 59 s");
    act(() => vi.advanceTimersByTime(59 * 60_000));
    expect(screen.getByTestId("countdown")).toHaveTextContent("5 h 00 min 59 s");
  });

  it("corrige le décalage entre l'horloge du lecteur et server_time", async () => {
    // le lecteur retarde de 1 h : le serveur dit 10:00, l'appareil 09:00
    vi.setSystemTime(new Date("2026-11-27T09:00:00Z"));
    await load(current(edition(), CLOSE, NOW));
    expect(screen.getByTestId("countdown")).toHaveTextContent("6 h 00 min");
  });

  it("édition null : le compte à rebours part de server_time", async () => {
    await load(current(null));
    expect(screen.getByTestId("countdown")).toHaveTextContent("6 h 00 min 00 s");
  });

  it("n'est pas une zone live (pas d'annonce chaque seconde) et expose un nom", async () => {
    await load(current(edition()));
    const timer = screen.getByRole("timer");
    expect(timer).not.toHaveAttribute("aria-live", "assertive");
    expect(timer).toHaveAccessibleName("Temps restant avant la prochaine une");
    expect(document.querySelector("[aria-live]")).toBeNull();
  });

  it("à l'heure dite : « Publication en cours… »", async () => {
    await load(current(edition(), "2026-11-27T10:00:02Z"));
    act(() => vi.advanceTimersByTime(3000));
    expect(screen.getByText("Publication en cours…")).toBeInTheDocument();
  });
});
