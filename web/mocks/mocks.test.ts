import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { api, ApiError } from "../src/api/client";
import { installMocks } from "./index";

const realFetch = window.fetch;
beforeEach(() => installMocks());
afterEach(() => {
  window.fetch = realFetch;
});

describe("API simulée", () => {
  it("sert la une avec support et raison", async () => {
    const { items } = await api.topicsFront(3);
    expect(items).toHaveLength(3);
    expect(items[0].support.level).toBeTruthy();
    expect(items[0].reason.label).toBeTruthy();
  });

  it("n'expose pas le support dans le flux de vote et respecte seen", async () => {
    const { items } = await api.voteNext(50, [1, 2]);
    expect(items.some((t) => t.id === 1 || t.id === 2)).toBe(false);
    expect(items[0]).not.toHaveProperty("support");
  });

  it("refuse le vote sans session (401), puis l'accepte après vérification", async () => {
    const err = await api.vote({ topic_id: 1, choice: "more" }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(401);
    await api.verify("abc");
    expect(await api.me()).toEqual({ email: "demo@example.org" });
    await expect(api.vote({ topic_id: 1, choice: "more" })).resolves.toEqual({ topic_id: 1, choice: "more" });
  });

  it("GET /votes/mine renvoie {votes:[...]}", async () => {
    await api.verify("abc");
    await api.vote({ topic_id: 2, choice: "unknown" });
    expect(await api.myVotes()).toEqual({ votes: [{ topic_id: 2, choice: "unknown" }] });
  });

  it("claim n'écrase pas un vote existant", async () => {
    await api.verify("abc");
    await api.vote({ topic_id: 1, choice: "more" });
    await api.claimVotes([
      { topic_id: 1, choice: "not_priority" },
      { topic_id: 2, choice: "more" },
    ]);
    const { votes } = await api.myVotes();
    expect(votes).toContainEqual({ topic_id: 1, choice: "more" });
    expect(votes).toContainEqual({ topic_id: 2, choice: "more" });
  });

  it("magic-link : 202 sans corps, 422 si invalide, 429 avec Retry-After", async () => {
    await expect(api.magicLink("a@b.fr")).resolves.toBeUndefined();
    await expect(api.magicLink("pas-un-email")).rejects.toMatchObject({ status: 422 });
    await expect(api.magicLink("limite@example.org")).rejects.toMatchObject({ status: 429, retryAfter: 5 });
  });

  it("verify refuse un jeton vide ou « expire » (400), logout met fin à la session", async () => {
    await expect(api.verify("")).rejects.toMatchObject({ status: 400 });
    await expect(api.verify("expire")).rejects.toMatchObject({ status: 400 });
    await api.verify("demo");
    await api.logout();
    expect(await api.me()).toBeNull();
  });

  it("claim refuse un lot de plus de 200 votes (422)", async () => {
    await api.verify("demo");
    const votes = Array.from({ length: 201 }, (_, i) => ({ topic_id: i + 1, choice: "more" as const }));
    await expect(api.claimVotes(votes)).rejects.toMatchObject({ status: 422 });
  });

  it("sert les paramètres du halving avec une description par clé", async () => {
    const { params, description } = await api.halvingConfig();
    expect(params).toEqual({ min_votes_first_decision: 20, keep_ratio: 0.5, waves: 3, new_topic_traffic_share: 0.3, rescue_share: 0.1 });
    for (const k of Object.keys(params)) expect(description[k]).toBeTruthy();
  });
});
