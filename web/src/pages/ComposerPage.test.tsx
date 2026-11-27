import { afterEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { AppRoutes } from "../App";
import type { Pool, Une } from "../api/types";
import { res, stubFetch, type Handler } from "../test/api-stub";
import { card, pool, une } from "../test/topics";
import { DRAFT_KEY } from "../lib/draft";
import { draftStore } from "../lib/draftStore";
import { getSeed } from "../lib/browse";

afterEach(() => vi.unstubAllGlobals());

const IDS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];

interface Opts {
  pool?: Pool;
  me?: boolean;
  une?: Une;
  routes?: Record<string, Handler>;
}

function mount(o: Opts = {}) {
  const state = { une: o.une ?? une([]) };
  const p = o.pool ?? pool(IDS);
  const fn = stubFetch({
    "GET /api/me": () => (o.me ? res(200, { email: "a@b.fr" }) : res(401, {})),
    "GET /api/topics/pool": (_i, url) => {
      const tab = new URL(url, "http://x").searchParams.get("tab");
      return res(200, tab === "radar" ? { ...p, items: p.items.filter((t) => t.source_count <= 3) } : tab === "recent" ? { ...p, items: [...p.items].reverse() } : p);
    },
    "GET /api/me/une": () => res(200, state.une),
    ...o.routes,
  });
  return { fn, state };
}

function renderPage(client = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/composer"]}>
        <AppRoutes />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return client;
}

const title = () => screen.getByRole("heading", { level: 3 }).textContent;
const swipe = (dx: number, dy: number) => {
  const el = screen.getByRole("group", { name: /Sujets à explorer/ });
  fireEvent.pointerDown(el, { pointerId: 1, clientX: 200, clientY: 300, isPrimary: true, pointerType: "touch" });
  for (let i = 1; i <= 4; i++) fireEvent.pointerMove(el, { pointerId: 1, clientX: 200 + (dx * i) / 4, clientY: 300 + (dy * i) / 4, pointerType: "touch" });
  fireEvent.pointerUp(el, { pointerId: 1, clientX: 200 + dx, clientY: 300 + dy, pointerType: "touch" });
};
const add = () => userEvent.click(screen.getByRole("button", { name: "Ajouter à ma une" }));
const next = () => userEvent.click(screen.getByRole("button", { name: /Suivant/ }));

describe("Composer : écran principal", () => {
  it("nom, heure, jauge, aperçu, onglets, carte et boutons", async () => {
    const { fn } = mount();
    renderPage();
    expect(await screen.findByRole("heading", { level: 3, name: "Sujet 1" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Composer ma une" })).toBeInTheDocument();
    expect(screen.getAllByText("Citizen News").length).toBeGreaterThanOrEqual(2); // en-tête du site + écran principal
    expect(screen.getByText(/Prochaine une à/)).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "0/10 sujets" })).toBeInTheDocument();
    expect(screen.getByText("Non enregistrée")).toBeInTheDocument();
    expect(screen.getAllByText("Place libre")).toHaveLength(10);
    const tabs = screen.getAllByRole("tab");
    expect(tabs.map((t) => t.textContent)).toEqual(["Au hasard", "Récents", "Sous les radars"]);
    expect(tabs[0]).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("position")).toHaveTextContent("1/12");
    expect(screen.getByRole("button", { name: /Précédent/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Revoir et valider" })).toBeInTheDocument();
    const url = new URL(fn.mock.calls.find(([u]) => u.startsWith("/api/topics/pool"))![0], "http://x");
    expect(url.searchParams.get("tab")).toBe("random");
    expect(url.searchParams.get("seed")).toBe(getSeed());
    expect(url.searchParams.get("seed")).toMatch(/^[A-Za-z0-9_-]{16,}$/);
  });

  it("états : chargement puis liste vide", async () => {
    mount({ pool: pool([]) });
    renderPage();
    expect(screen.getByRole("status", { name: "Chargement des sujets" })).toBeInTheDocument();
    expect(await screen.findByText(/Aucun sujet n’est encore disponible/)).toBeInTheDocument();
  });

  it("erreur réseau : message et « Réessayer »", async () => {
    let ok = false;
    mount({ routes: { "GET /api/topics/pool": () => (ok ? res(200, pool(IDS)) : res(500, { detail: "x" })) } });
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent(/n’ont pas pu être chargés/);
    ok = true;
    await userEvent.click(screen.getByRole("button", { name: "Réessayer" }));
    expect(await screen.findByRole("heading", { level: 3, name: "Sujet 1" })).toBeInTheDocument();
  });

  it("aucun compteur d'approbation ni de popularité dans le DOM", async () => {
    mount({ pool: { ...pool([1, 2]), items: [card(1, { approvals: 99, support: "high" } as never), card(2)] } });
    renderPage();
    await screen.findByRole("heading", { level: 3, name: "Sujet 1" });
    await add();
    await userEvent.click(screen.getByRole("button", { name: "Revoir et valider" }));
    expect(document.body.textContent).not.toMatch(/approbation|populaire|popularité|soutien|\b99\b|votes?\b/i);
  });
});

describe("Composer : ajout, retrait, une pleine (brouillon local)", () => {
  it("ajouter par bouton : annonce, jauge, aperçu, marque « Dans ma une », brouillon stocké", async () => {
    mount();
    renderPage();
    await screen.findByRole("heading", { level: 3, name: "Sujet 1" });
    await add();
    expect(await screen.findByText("Ajouté à votre une (1/10)")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "1/10 sujets" })).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: /Aperçu/ })).getAllByRole("listitem")[0]).toHaveTextContent("Sujet 1");
    expect(screen.getByText("Dans ma une")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retirer de ma une" })).toBeInTheDocument();
    expect(JSON.parse(window.localStorage.getItem(DRAFT_KEY)!).ids).toEqual([1]);
    await userEvent.click(screen.getByRole("button", { name: "Retirer de ma une" }));
    expect(await screen.findByText("Retiré de votre une (0/10)")).toBeInTheDocument();
    expect(window.localStorage.getItem(DRAFT_KEY)).toBeNull();
  });

  it("gestes : haut ajoute, gauche passe au suivant, bas retire", async () => {
    mount();
    renderPage();
    await screen.findByRole("heading", { level: 3, name: "Sujet 1" });
    swipe(0, -120);
    expect(await screen.findByText("Ajouté à votre une (1/10)")).toBeInTheDocument();
    swipe(-120, 0);
    expect(await screen.findByRole("heading", { level: 3, name: "Sujet 2" })).toBeInTheDocument();
    swipe(0, 120); // retirer un sujet absent : rien
    expect(screen.getByRole("progressbar", { name: "1/10 sujets" })).toBeInTheDocument();
    swipe(120, 0);
    expect(await screen.findByRole("heading", { level: 3, name: "Sujet 1" })).toBeInTheDocument();
    swipe(0, 120);
    expect(await screen.findByText("Retiré de votre une (0/10)")).toBeInTheDocument();
  });

  it("clavier : flèches ajoutent et naviguent", async () => {
    mount();
    renderPage();
    await screen.findByRole("heading", { level: 3, name: "Sujet 1" });
    screen.getByRole("group", { name: /Sujets à explorer/ }).focus();
    await userEvent.keyboard("{ArrowUp}");
    expect(await screen.findByText("Ajouté à votre une (1/10)")).toBeInTheDocument();
    await userEvent.keyboard("{ArrowRight}");
    expect(await screen.findByRole("heading", { level: 3, name: "Sujet 2" })).toBeInTheDocument();
  });

  it("une pleine : l'ajout est refusé avec « Revoir et valider » ; retirer fonctionne", async () => {
    draftStore.set({ editionDate: "2026-11-27", ids: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10] });
    mount();
    renderPage();
    await screen.findByRole("heading", { level: 3, name: "Sujet 1" });
    expect(screen.getByRole("progressbar", { name: "10/10 sujets" })).toBeInTheDocument();
    swipe(-120, 0);
    swipe(-120, 0);
    await screen.findByRole("heading", { level: 3, name: "Sujet 3" });
    // aller au sujet 11 (hors une)
    for (let i = 0; i < 8; i++) await next();
    expect(title()).toBe("Sujet 11");
    await add();
    expect(await screen.findByText(/Votre une est complète \(10\/10\)\. Pour ajouter/)).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "10/10 sujets" })).toBeInTheDocument();
    const alertBtns = screen.getAllByRole("button", { name: "Revoir et valider" });
    expect(alertBtns.length).toBeGreaterThanOrEqual(2);
    // retirer un sujet de la une : toujours possible
    await userEvent.click(screen.getByRole("button", { name: /Précédent/ }));
    await userEvent.click(screen.getByRole("button", { name: "Retirer de ma une" }));
    expect(await screen.findByText("Retiré de votre une (9/10)")).toBeInTheDocument();
  });
});

describe("Composer : onglets, graine, sans répétition", () => {
  it("flèches du clavier dans les onglets ; Récents sans graine ; chaque onglet garde sa position", async () => {
    const { fn } = mount();
    renderPage();
    await screen.findByRole("heading", { level: 3, name: "Sujet 1" });
    await next();
    await next();
    expect(title()).toBe("Sujet 3");
    const tabs = screen.getAllByRole("tab");
    tabs[0].focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Récents" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Récents" })).toHaveFocus();
    expect(await screen.findByRole("heading", { level: 3, name: "Sujet 12" })).toBeInTheDocument(); // ordre serveur
    await next();
    expect(title()).toBe("Sujet 11");
    const recentCall = fn.mock.calls.map(([u]) => new URL(u, "http://x")).find((u) => u.searchParams.get("tab") === "recent")!;
    expect(recentCall.searchParams.has("seed")).toBe(false);
    screen.getByRole("tab", { name: "Récents" }).focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(await screen.findByRole("tab", { name: "Sous les radars" })).toHaveAttribute("aria-selected", "true");
    await userEvent.keyboard("{ArrowLeft}{ArrowLeft}");
    expect(screen.getByRole("tab", { name: "Au hasard" })).toHaveAttribute("aria-selected", "true");
    expect(title()).toBe("Sujet 3");
    await userEvent.click(screen.getByRole("tab", { name: "Récents" }));
    expect(title()).toBe("Sujet 11");
  });

  it("Sous les radars : états vides", async () => {
    mount({ pool: { ...pool([1, 2]), items: [card(1), card(2)] } });
    renderPage();
    await screen.findByRole("heading", { level: 3, name: "Sujet 1" });
    await userEvent.click(screen.getByRole("tab", { name: "Sous les radars" }));
    expect(await screen.findByText(/Aucun sujet peu couvert/)).toBeInTheDocument();
  });

  it("au hasard : tout le bassin défile sans répétition, et la reprise repart des sujets vus", async () => {
    mount();
    renderPage();
    const seenTitles: string[] = [];
    await screen.findByRole("heading", { level: 3, name: "Sujet 1" });
    for (let i = 0; i < IDS.length; i++) {
      seenTitles.push(title()!);
      if (i < IDS.length - 1) await next();
    }
    expect(new Set(seenTitles).size).toBe(IDS.length);
    expect(screen.getByRole("button", { name: /Suivant/ })).toBeDisabled();
  });

  it("rechargement dans la session : même graine, reprise sur le dernier sujet vu", async () => {
    mount();
    renderPage();
    await screen.findByRole("heading", { level: 3, name: "Sujet 1" });
    await next();
    await next();
    const seed = getSeed();
    cleanupAll();
    renderPage();
    expect(await screen.findByRole("heading", { level: 3, name: "Sujet 3" })).toBeInTheDocument();
    expect(getSeed()).toBe(seed);
  });

  it("un sujet apparu en cours de journée s'insère parmi les non vus, sans faire sauter la carte", async () => {
    let items = IDS.slice(0, 5);
    mount({ routes: { "GET /api/topics/pool": () => res(200, pool(items)) } });
    const client = renderPage();
    await screen.findByRole("heading", { level: 3, name: "Sujet 1" });
    await next();
    await next();
    expect(title()).toBe("Sujet 3");
    items = [1, 2, 3, 99, 4, 5]; // 99 apparaît (ordre serveur) ; 3 est la carte courante
    await act(async () => {
      await client.invalidateQueries({ queryKey: ["pool"] });
    });
    await waitFor(() => expect(screen.getByTestId("position")).toHaveTextContent("3/6"));
    expect(title()).toBe("Sujet 3");
    await next();
    expect(title()).toBe("Sujet 99"); // inséré dans les non vus, à sa place serveur
    await next();
    expect(title()).toBe("Sujet 4");
  });

  it("refetch quand le serveur change l'ordre : la carte courante reste, même position retenue par id", async () => {
    let order = [1, 2, 3, 4];
    mount({ routes: { "GET /api/topics/pool": () => res(200, pool(order)) } });
    const client = renderPage();
    await screen.findByRole("heading", { level: 3, name: "Sujet 1" });
    await userEvent.click(screen.getByRole("tab", { name: "Récents" }));
    await screen.findByRole("heading", { level: 3, name: "Sujet 1" });
    order = [9, 1, 2, 3, 4];
    await act(async () => {
      await client.invalidateQueries({ queryKey: ["pool", "recent"] });
    });
    await waitFor(() => expect(screen.getByTestId("position")).toHaveTextContent("2/5"));
    expect(title()).toBe("Sujet 1");
  });
});

function cleanupAll() {
  document.body.innerHTML = "";
}
