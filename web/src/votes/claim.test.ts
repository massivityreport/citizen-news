import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { bodiesOf, res, stubFetch } from "../test/api-stub";
import { claimLocalVotes, CLAIM_BATCH_SIZE } from "./claim";
import { readLocalVotes, saveLocalVote, STORAGE_KEY } from "./storage";

const seed = (n: number) =>
  localStorage.setItem(STORAGE_KEY, JSON.stringify(Array.from({ length: n }, (_, i) => ({ topic_id: i + 1, choice: "more" }))));

beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

describe("claimLocalVotes", () => {
  it("ne fait aucun appel sans votes locaux", async () => {
    const fn = stubFetch({});
    expect(await claimLocalVotes()).toEqual({ status: "none", sent: 0, claimed: 0 });
    expect(fn).not.toHaveBeenCalled();
  });

  it("vide la liste même si le serveur en a créé moins qu'envoyé", async () => {
    seed(3);
    stubFetch({ "POST /api/votes/claim": () => res(200, { claimed: 1 }) });
    expect(await claimLocalVotes()).toEqual({ status: "ok", sent: 3, claimed: 1 });
    expect(readLocalVotes()).toEqual([]);
  });

  it("conserve un vote local enregistré pendant le claim", async () => {
    seed(2);
    stubFetch({
      "POST /api/votes/claim": () => {
        saveLocalVote({ topic_id: 99, choice: "unknown" });
        saveLocalVote({ topic_id: 1, choice: "not_priority" }); // choix modifié pendant l'envoi
        return res(200, { claimed: 2 });
      },
    });
    await claimLocalVotes();
    expect(readLocalVotes()).toEqual([
      { topic_id: 99, choice: "unknown" },
      { topic_id: 1, choice: "not_priority" },
    ]);
  });

  it("envoie par lots de 200 et additionne les votes créés", async () => {
    seed(450);
    const fn = stubFetch({
      "POST /api/votes/claim": (init) => res(200, { claimed: JSON.parse(init!.body as string).votes.length }),
    });
    expect(await claimLocalVotes()).toEqual({ status: "ok", sent: 450, claimed: 450 });
    expect(bodiesOf(fn, "POST /api/votes/claim").map((b) => b.votes.length)).toEqual([CLAIM_BATCH_SIZE, CLAIM_BATCH_SIZE, 50]);
    expect(readLocalVotes()).toEqual([]);
  });

  it("ne vide pas si un lot échoue (5xx)", async () => {
    seed(250);
    let n = 0;
    stubFetch({ "POST /api/votes/claim": () => (n++ === 0 ? res(200, { claimed: 200 }) : res(500, {})) });
    expect((await claimLocalVotes()).status).toBe("error");
    expect(readLocalVotes()).toHaveLength(250);
  });

  it("ne vide pas sur erreur réseau ni sur 401", async () => {
    seed(2);
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("réseau")));
    expect((await claimLocalVotes()).status).toBe("error");
    stubFetch({ "POST /api/votes/claim": () => res(401, {}) });
    expect((await claimLocalVotes()).status).toBe("unauthorized");
    expect(readLocalVotes()).toHaveLength(2);
  });

  it("partage la requête entre appels simultanés", async () => {
    seed(2);
    const fn = stubFetch({ "POST /api/votes/claim": () => res(200, { claimed: 2 }) });
    const [a, b] = await Promise.all([claimLocalVotes(), claimLocalVotes()]);
    expect(a).toBe(b);
    expect(fn).toHaveBeenCalledTimes(1);
  });
});
