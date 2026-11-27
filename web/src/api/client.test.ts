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
    const fetchMock = mockFetch(200, { items: [] });
    await api.editions(20);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/editions?limit=20");
    expect(init.credentials).toBe("include");
  });

  it("currentEdition appelle /edition/current", async () => {
    const fetchMock = mockFetch(200, { edition: null, next_close_at: "2026-11-27T16:00:00Z", server_time: "2026-11-27T10:00:00Z" });
    const res = await api.currentEdition();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/edition/current");
    expect(res.edition).toBeNull();
  });

  it("edition et editions construisent les bonnes URL", async () => {
    let fetchMock = mockFetch(200, {});
    await api.edition("2026-11-26");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/editions/2026-11-26");
    fetchMock = mockFetch(200, { items: [] });
    await api.editions();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/editions?limit=30");
  });

  it("magicLink joint le brouillon quand il y en a un", async () => {
    const fetchMock = mockFetch(202);
    await api.magicLink("a@b.fr", { topic_ids: [1, 2] });
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ email: "a@b.fr", draft: { topic_ids: [1, 2] } });
  });

  it("lève ApiError 401 avec le detail", async () => {
    mockFetch(401, { detail: "Non connecté" });
    const err = await api.edition("2026-11-26").catch((e) => e);
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
    const err = await api.currentEdition().catch((e) => e);
    expect(err.status).toBe(500);
    expect(err.message).toBeTruthy();
  });
});
