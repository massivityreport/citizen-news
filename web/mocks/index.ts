import { editions } from "./fixtures";

const LATENCY_MS = 150;
const json = (status: number, body?: unknown, headers?: Record<string, string>) =>
  new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });

type Body = { email?: string; token?: string } | undefined;

/**
 * Simule l'API en interceptant fetch pour les URL /api/*.
 * État en mémoire (session) : remis à zéro au rechargement.
 */
export function installMocks() {
  const realFetch = window.fetch.bind(window);
  let session: string | null = null;

  async function handle(method: string, url: URL, body: Body): Promise<Response> {
    const path = url.pathname.replace(/^\/api/, "");
    const route = `${method} ${path}`;

    switch (route) {
      case "GET /edition/current": {
        // Fermeture dans 2 h : le compte à rebours bouge sous les yeux. ?mock=vide : aucune édition publiée.
        const none = new URLSearchParams(window.location.search).get("mock") === "vide";
        return json(200, {
          edition: none ? null : editions[0],
          next_close_at: new Date(Date.now() + 2 * 3_600_000).toISOString(),
          server_time: new Date().toISOString(),
        });
      }
      case "GET /editions": {
        const limit = Number(url.searchParams.get("limit") ?? 30);
        return json(200, {
          items: editions.slice(0, limit).map((e) => ({
            date: e.date,
            published_at: e.published_at,
            participants: e.participants,
            topic_count: e.topics.length,
          })),
        });
      }
      case "POST /auth/magic-link":
        if (!body?.email || !String(body.email).includes("@")) return json(422, { detail: "Adresse e-mail invalide." });
        // Pour rejouer le cas « trop de demandes » : limite@example.org
        if (body.email === "limite@example.org") return json(429, { detail: "Trop de demandes." }, { "Retry-After": "5" });
        // Toujours 202, que le compte existe ou non. Lien de test : /connexion?token=demo
        return json(202);
      case "POST /auth/verify":
        // Jeton à usage unique : tout jeton non vide est accepté, sauf « expire » (rejoue le cas 400).
        if (!body?.token || body.token === "expire") return json(400, { detail: "Lien invalide ou expiré." });
        session = "demo@example.org";
        return json(200, { email: session });
      case "POST /auth/logout":
        session = null;
        return json(204);
      case "GET /me":
        return session ? json(200, { email: session }) : json(401, { detail: "Non connecté." });
      default: {
        const m = /^GET \/editions\/(\d{4}-\d{2}-\d{2})$/.exec(route);
        const found = m && editions.find((e) => e.date === m[1]);
        if (found) return json(200, found);
        if (m) return json(404, { detail: "Édition introuvable." });
        return json(404, { detail: "Introuvable." });
      }
    }
  }

  window.fetch = async (input, init) => {
    const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const url = new URL(raw, window.location.origin);
    if (!url.pathname.startsWith("/api/")) return realFetch(input, init);
    await new Promise((r) => setTimeout(r, LATENCY_MS));
    const body = typeof init?.body === "string" ? JSON.parse(init.body) : undefined;
    return handle((init?.method ?? "GET").toUpperCase(), url, body);
  };

  console.info("[mocks] API simulée active (VITE_USE_MOCKS=true)");
}
