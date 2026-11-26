import { vi } from "vitest";

export const res = (status: number, body?: unknown, headers?: Record<string, string>) =>
  new Response(body === undefined ? null : JSON.stringify(body), { status, headers });

export type Handler = (init: RequestInit | undefined, url: string) => Response | Promise<Response>;

/** Remplace fetch par une table « MÉTHODE /chemin » -> réponse ; les routes absentes répondent 404. */
export function stubFetch(routes: Record<string, Handler>) {
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    const path = url.split("?")[0];
    const handler = routes[`${init?.method ?? "GET"} ${path}`];
    return handler ? handler(init, url) : res(404, { detail: "Introuvable." });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

/** Corps JSON des appels à une route. */
export function bodiesOf(fn: ReturnType<typeof stubFetch>, route: string) {
  return fn.mock.calls
    .filter(([u, i]) => `${i?.method ?? "GET"} ${u.split("?")[0]}` === route)
    .map(([, i]) => (i?.body ? JSON.parse(i.body as string) : undefined));
}
