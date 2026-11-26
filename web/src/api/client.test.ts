import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "./client";

function mockFetch(status: number, body?: unknown, headers: Record<string, string> = {}) {
  const fn = vi.fn().mockResolvedValue(
    new Response(body === undefined ? null : JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json", ...headers },
    }),
  );
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

describe("api client", () => {
  it("appelle /api avec les cookies de session", async () => {
    const fetchMock = mockFetch(200, { items: [], has_more: false });
    await api.topicsFront(20);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/topics/front?limit=20");
    expect(init.credentials).toBe("include");
  });

  it("topicsFront demande 10 sujets par défaut et expose has_more", async () => {
    const fetchMock = mockFetch(200, { items: [], has_more: true });
    const res = await api.topicsFront();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/topics/front?limit=10");
    expect(res.has_more).toBe(true);
  });

  it("encode seen et count pour /vote/next", async () => {
    const fetchMock = mockFetch(200, { items: [] });
    await api.voteNext(10, [1, 2]);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/vote/next?count=10&seen=1%2C2");
  });

  it("envoie un vote en JSON", async () => {
    const fetchMock = mockFetch(200, { topic_id: 3, choice: "more" });
    await api.vote({ topic_id: 3, choice: "more" });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/votes");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ topic_id: 3, choice: "more" });
    expect(init.headers["Content-Type"]).toBe("application/json");
  });

  it("lève ApiError 401 avec le detail", async () => {
    mockFetch(401, { detail: "Non connecté" });
    const err = await api.vote({ topic_id: 1, choice: "more" }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(401);
    expect(err.message).toBe("Non connecté");
  });

  it("lève ApiError 429 avec Retry-After", async () => {
    mockFetch(429, { detail: "Trop de requêtes" }, { "Retry-After": "30" });
    const err = await api.magicLink("a@b.fr").catch((e) => e);
    expect(err.status).toBe(429);
    expect(err.isRateLimited).toBe(true);
    expect(err.retryAfter).toBe(30);
  });

  it("gère une réponse 202 sans corps", async () => {
    mockFetch(202);
    await expect(api.magicLink("a@b.fr")).resolves.toBeUndefined();
  });

  it("me() renvoie null sur 401", async () => {
    mockFetch(401, { detail: "x" });
    await expect(api.me()).resolves.toBeNull();
  });

  it("message par défaut si le corps n'est pas du JSON", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("oops", { status: 500 })));
    const err = await api.halvingConfig().catch((e) => e);
    expect(err.status).toBe(500);
    expect(err.message).toBeTruthy();
  });
});
