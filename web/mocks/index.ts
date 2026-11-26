import type { Vote } from "../src/api/types";
import { frontTopics, voteDeck } from "./fixtures";

const LATENCY_MS = 150;
const json = (status: number, body?: unknown, headers?: Record<string, string>) =>
  new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });

type Body = { topic_id?: number; choice?: string; email?: string; token?: string; votes?: Vote[] } | undefined;
const CHOICES = ["more", "not_priority", "unknown"];

/**
 * Simule l'API en interceptant fetch pour les URL /api/*.
 * État en mémoire (session, votes) : remis à zéro au rechargement.
 */
export function installMocks() {
  const realFetch = window.fetch.bind(window);
  let session: string | null = null;
  const votes = new Map<number, string>();

  async function handle(method: string, url: URL, body: Body): Promise<Response> {
    const path = url.pathname.replace(/^\/api/, "");
    const route = `${method} ${path}`;

    switch (route) {
      case "GET /topics/front": {
        const limit = Number(url.searchParams.get("limit") ?? 20);
        return json(200, { items: frontTopics.slice(0, limit) });
      }
      case "GET /vote/next": {
        const count = Number(url.searchParams.get("count") ?? 10);
        const seen = new Set((url.searchParams.get("seen") ?? "").split(",").filter(Boolean).map(Number));
        const items = voteDeck.filter((t) => !seen.has(t.id)).slice(0, count);
        return json(200, { items });
      }
      case "POST /votes": {
        if (!session) return json(401, { detail: "Connectez-vous pour enregistrer votre vote." });
        if (!CHOICES.includes(body?.choice ?? "")) return json(422, { detail: "Choix invalide." });
        votes.set(body!.topic_id!, body!.choice!);
        return json(200, { topic_id: body!.topic_id, choice: body!.choice });
      }
      case "POST /votes/claim": {
        if (!session) return json(401, { detail: "Connectez-vous pour enregistrer vos votes." });
        const list = body?.votes ?? [];
        if (list.length > 200) return json(422, { detail: "Trop de votes dans un seul lot (200 maximum)." });
        // Un vote déjà enregistré n'est pas écrasé par un vote anonyme réclamé.
        let claimed = 0;
        for (const v of list) {
          if (votes.has(v.topic_id)) continue;
          votes.set(v.topic_id, v.choice);
          claimed++;
        }
        return json(200, { claimed });
      }
      case "GET /votes/mine":
        if (!session) return json(401, { detail: "Non connecté." });
        return json(200, { votes: [...votes].map(([topic_id, choice]) => ({ topic_id, choice })) });
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
      case "GET /halving/config":
        return json(200, {
          params: { min_votes_first_decision: 20, keep_ratio: 0.5, waves: 3, new_topic_traffic_share: 0.3, rescue_share: 0.1 },
          description: {
            min_votes_first_decision: "Nombre minimal de votes réunis par un sujet avant que l’on décide de le conserver ou non.",
            keep_ratio: "Part des sujets les mieux soutenus qui passent à la vague suivante.",
            waves: "Nombre de vagues de sélection successives.",
            new_topic_traffic_share: "Part des sujets proposés aux votants réservée aux nouveaux sujets.",
            rescue_share: "Part des sujets proposés aux votants réservée au repêchage de sujets de la réserve.",
          },
        });
      default:
        return json(404, { detail: "Introuvable." });
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
