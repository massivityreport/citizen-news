import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderApp } from "../test/utils";
import type { FrontTopic } from "../api/types";

const hoursAgo = (h: number) => new Date(Date.now() - h * 3_600_000).toISOString();

const topic = (over: Partial<FrontTopic> = {}): FrontTopic => ({
  id: 1,
  title: "Pénurie de médecins",
  summary: "Des délais de trois mois.",
  sources: [
    { name: "Le Monde", url: "https://example.org/a", title: "Titre A", published_at: hoursAgo(5) },
    { name: "Ouest-France", url: "https://example.org/b", title: "Titre B", published_at: hoursAgo(9) },
    { name: "Piégé", url: "javascript:alert(1)", title: "x", published_at: hoursAgo(9) },
  ],
  first_seen_at: hoursAgo(72),
  updated_at: hoursAgo(2),
  support: { level: "high", votes_count: 10 },
  reason: { code: "common_priority", label: "Priorité commune" },
  ...over,
});

function stubApi(front: () => Response | Promise<Response>) {
  const fn = vi.fn(async (url: string) => {
    if (url.startsWith("/api/topics/front")) return front();
    if (url === "/api/me") return new Response("{}", { status: 401 });
    return new Response("{}", { status: 404 });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}
const ok = (items: FrontTopic[], has_more = false) =>
  new Response(JSON.stringify({ items, has_more }), { status: 200 });

afterEach(() => vi.unstubAllGlobals());

describe("La une citoyenne", () => {
  it("affiche une carte complète", async () => {
    stubApi(() => ok([topic()]));
    renderApp("/");
    const card = await screen.findByRole("article", { name: "Pénurie de médecins" });
    expect(within(card).getByText("Priorité commune")).toBeInTheDocument();
    expect(within(card).getByText("Des délais de trois mois.")).toBeInTheDocument();
    expect(within(card).getByText("Soutien élevé")).toBeInTheDocument();
    const lemonde = within(card).getByRole("link", { name: /Le Monde/ });
    expect(lemonde).toHaveAttribute("href", "https://example.org/a");
    expect(within(card).getByRole("link", { name: /Ouest-France/ })).toBeInTheDocument();
    expect(within(card).getByText(/il y a 2 heures/)).toBeInTheDocument();
    expect(within(card).getByText(/Apparu/)).toBeInTheDocument();
  });

  it("ne rend pas cliquable un lien non http(s)", async () => {
    stubApi(() => ok([topic()]));
    renderApp("/");
    const card = await screen.findByRole("article");
    expect(within(card).queryByRole("link", { name: /Piégé/ })).toBeNull();
    expect(within(card).getByText("Piégé")).toBeInTheDocument();
  });

  it.each([
    ["low", "Soutien faible"],
    ["medium", "Soutien moyen"],
    ["high", "Soutien élevé"],
  ] as const)("niveau %s : libellé « %s »", async (level, label) => {
    stubApi(() => ok([topic({ support: { level, votes_count: 1 } })]));
    renderApp("/");
    expect(await screen.findByText(label)).toBeInTheDocument();
  });

  it.each([
    ["strong_mobilisation", "Forte mobilisation"],
    ["under_the_radar", "Sous les radars"],
    ["emerging", "Sujet émergent"],
  ] as const)("badge %s", async (code, label) => {
    stubApi(() => ok([topic({ reason: { code, label } })]));
    renderApp("/");
    expect(await screen.findByText(label)).toBeInTheDocument();
  });

  it("un code de raison inconnu s'affiche avec son label", async () => {
    stubApi(() =>
      ok([topic({ reason: { code: "nouveau_code" as never, label: "Nouveauté du jour" } })]),
    );
    renderApp("/");
    expect(await screen.findByText("Nouveauté du jour")).toBeInTheDocument();
  });

  it("affiche des squelettes pendant le chargement", () => {
    stubApi(() => new Promise<Response>(() => {}));
    renderApp("/");
    expect(screen.getByText("Chargement de la une…")).toBeInTheDocument();
  });

  it("propose de réessayer après une erreur", async () => {
    let calls = 0;
    stubApi(() => (++calls === 1 ? new Response("{}", { status: 500 }) : ok([topic()])));
    renderApp("/");
    expect(await screen.findByRole("alert")).toHaveTextContent(/Impossible de charger/);
    await userEvent.click(screen.getByRole("button", { name: "Réessayer" }));
    expect(await screen.findByRole("article", { name: "Pénurie de médecins" })).toBeInTheDocument();
  });

  it("affiche un message quand la liste est vide", async () => {
    stubApi(() => ok([]));
    renderApp("/");
    expect(await screen.findByText(/La une est vide/)).toBeInTheDocument();
  });

  it("propose l'appel à l'action vers « À vous de jouer »", async () => {
    stubApi(() => ok([topic()]));
    renderApp("/");
    const cta = await screen.findByRole("complementary", { name: "Participer" });
    expect(within(cta).getByRole("link", { name: "À vous de jouer" })).toHaveAttribute("href", "/jouer");
  });

  describe("Voir plus", () => {
    const many = (n: number) => Array.from({ length: n }, (_, i) => topic({ id: i + 1, title: `Sujet ${i + 1}` }));
    const limitOf = (url: string) => Number(new URL(url, "http://x").searchParams.get("limit"));

    it("affiche 10 sujets, puis 20 au clic, sans doublon", async () => {
      const fn = stubApi(() => ok([]));
      fn.mockImplementation(async (url: string) => {
        if (url.startsWith("/api/topics/front")) {
          const n = limitOf(url);
          return ok(many(n), n < 30);
        }
        return new Response("{}", { status: 401 });
      });
      renderApp("/");
      await screen.findByRole("article", { name: "Sujet 1" });
      expect(screen.getAllByRole("article")).toHaveLength(10);
      expect(fn.mock.calls.some(([u]) => limitOf(u as string) === 10)).toBe(true);
      const btn = screen.getByRole("button", { name: "Voir plus" });
      await userEvent.click(btn);
      await screen.findByRole("article", { name: "Sujet 20" });
      const titles = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
      expect(titles).toHaveLength(20);
      expect(new Set(titles).size).toBe(20);
      expect(screen.getByRole("button", { name: "Voir plus" })).toHaveFocus();
    });

    it("garde la liste pendant le chargement et indique « Chargement… »", async () => {
      let release: (r: Response) => void = () => {};
      const fn = stubApi(() => ok([]));
      fn.mockImplementation(async (url: string) => {
        if (!url.startsWith("/api/topics/front")) return new Response("{}", { status: 401 });
        if (limitOf(url) === 10) return ok(many(10), true);
        return new Promise<Response>((r) => (release = r));
      });
      renderApp("/");
      await screen.findByRole("article", { name: "Sujet 1" });
      await userEvent.click(screen.getByRole("button", { name: "Voir plus" }));
      expect(await screen.findByRole("button", { name: "Chargement…" })).toBeInTheDocument();
      expect(screen.getAllByRole("article")).toHaveLength(10);
      release(ok(many(20), false));
      await screen.findByRole("article", { name: "Sujet 20" });
    });

    it("n'affiche pas le bouton quand has_more est faux", async () => {
      stubApi(() => ok(many(3), false));
      renderApp("/");
      await screen.findByRole("article", { name: "Sujet 1" });
      expect(screen.queryByRole("button", { name: "Voir plus" })).toBeNull();
    });

    it("n'affiche plus le bouton à la limite de 50", async () => {
      const fn = stubApi(() => ok([]));
      fn.mockImplementation(async (url: string) =>
        url.startsWith("/api/topics/front") ? ok(many(limitOf(url)), true) : new Response("{}", { status: 401 }),
      );
      renderApp("/");
      await screen.findByRole("article", { name: "Sujet 10" });
      for (let n = 20; n <= 50; n += 10) {
        await userEvent.click(await screen.findByRole("button", { name: "Voir plus" }));
        await screen.findByRole("article", { name: `Sujet ${n}` });
      }
      expect(screen.queryByRole("button", { name: /Voir plus|Chargement/ })).toBeNull();
      expect(screen.getAllByRole("article")).toHaveLength(50);
      expect(document.activeElement).toBe(screen.getByRole("heading", { name: "Sujet 41" }));
    }, 15000);

    it("passe le focus au premier nouvel élément quand le bouton disparaît (has_more=false)", async () => {
      const fn = stubApi(() => ok([]));
      fn.mockImplementation(async (url: string) =>
        url.startsWith("/api/topics/front")
          ? ok(many(Math.min(limitOf(url), 15)), limitOf(url) < 15)
          : new Response("{}", { status: 401 }),
      );
      renderApp("/");
      await screen.findByRole("article", { name: "Sujet 10" });
      await userEvent.click(screen.getByRole("button", { name: "Voir plus" }));
      await screen.findByRole("article", { name: "Sujet 15" });
      expect(screen.queryByRole("button", { name: "Voir plus" })).toBeNull();
      expect(document.activeElement).toBe(screen.getByRole("heading", { name: "Sujet 11" }));
    });

    it("garde la liste et propose de réessayer si « Voir plus » échoue", async () => {
      const fn = stubApi(() => ok([]));
      fn.mockImplementation(async (url: string) => {
        if (!url.startsWith("/api/topics/front")) return new Response("{}", { status: 401 });
        return limitOf(url) === 10 ? ok(many(10), true) : new Response("{}", { status: 500 });
      });
      renderApp("/");
      await screen.findByRole("article", { name: "Sujet 1" });
      await userEvent.click(screen.getByRole("button", { name: "Voir plus" }));
      expect(await screen.findByRole("alert")).toHaveTextContent(/plus de sujets/);
      expect(screen.getAllByRole("article")).toHaveLength(10);
    });
  });
});
