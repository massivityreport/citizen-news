import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import { renderApp } from "../test/utils";
import { res, stubFetch } from "../test/api-stub";

const config = {
  params: { min_votes_first_decision: 20, keep_ratio: 0.5, waves: 3, new_topic_traffic_share: 0.3, rescue_share: 0.1 },
  description: {
    min_votes_first_decision: "Votes minimum avant la première décision.",
    keep_ratio: "Part conservée à chaque vague.",
    waves: "Nombre de vagues.",
    new_topic_traffic_share: "Part réservée aux nouveaux sujets.",
    rescue_share: "Part réservée au repêchage.",
  },
};

afterEach(() => vi.unstubAllGlobals());

describe("Comment ça marche", () => {
  it("explique la question, les étapes, les raisons et la confidentialité", async () => {
    stubFetch({ "GET /api/me": () => res(401, {}), "GET /api/halving/config": () => res(200, config) });
    renderApp("/comment-ca-marche");
    expect(await screen.findByRole("heading", { level: 1, name: "Comment ça marche" })).toBeInTheDocument();
    expect(screen.getByText(/De quoi devrions-nous parler/)).toBeInTheDocument();
    expect(screen.getByText(/Première vague aléatoire/)).toBeInTheDocument();
    expect(screen.getByText(/écarté sur un seul vote/)).toBeInTheDocument();
    for (const r of ["Priorité commune", "Forte mobilisation", "Sous les radars", "Sujet émergent"]) {
      expect(screen.getByText(r)).toBeInTheDocument();
    }
    expect(screen.getByText(/votre adresse e-mail/)).toBeInTheDocument();
  });

  it("affiche les paramètres actifs lus sur l'API, parts en pourcentage", async () => {
    stubFetch({ "GET /api/me": () => res(401, {}), "GET /api/halving/config": () => res(200, config) });
    renderApp("/comment-ca-marche");
    const item = (label: string) => screen.findByText(label).then((t) => within(t.parentElement!));
    expect((await item("Votes avant la première décision")).getByText("20")).toBeInTheDocument();
    expect((await item("Part des sujets conservés à chaque vague")).getByText(/^50\s%$/)).toBeInTheDocument();
    expect((await item("Nombre de vagues")).getByText("3")).toBeInTheDocument();
    expect((await item("Part de l’attention donnée aux nouveaux sujets")).getByText(/^30\s%$/)).toBeInTheDocument();
    expect((await item("Part de l’attention donnée au repêchage")).getByText(/^10\s%$/)).toBeInTheDocument();
    expect(screen.getByText("Part réservée au repêchage.")).toBeInTheDocument();
  });

  it("affiche un état de chargement puis une erreur avec réessai", async () => {
    stubFetch({ "GET /api/me": () => res(401, {}), "GET /api/halving/config": () => res(500, {}) });
    renderApp("/comment-ca-marche");
    expect(screen.getByText("Chargement des réglages…")).toBeInTheDocument();
    expect(await screen.findByRole("alert")).toHaveTextContent("Les réglages actuels n’ont pas pu être chargés.");
    expect(screen.getByRole("button", { name: "Réessayer" })).toBeInTheDocument();
    expect(screen.queryByText("Nombre de vagues")).toBeNull();
  });
});
