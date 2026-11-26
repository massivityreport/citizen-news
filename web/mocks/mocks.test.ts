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
});
