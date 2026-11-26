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
const ok = (items: FrontTopic[]) => new Response(JSON.stringify({ items }), { status: 200 });

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
});
