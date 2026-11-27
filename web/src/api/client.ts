import type {
  AdminSource,
  FrontTopic,
  HalvingConfig,
  Me,
  TopicCard,
  Vote,
  VoteChoice,
} from "./types";

const BASE = "/api";

export class ApiError extends Error {
  readonly status: number;
  readonly retryAfter?: number;

  constructor(status: number, message: string, retryAfter?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.retryAfter = retryAfter;
  }

  get isUnauthorized() {
    return this.status === 401;
  }

  get isRateLimited() {
    return this.status === 429;
  }
}

const DEFAULT_MESSAGES: Record<number, string> = {
  401: "Vous devez être connecté.",
  429: "Trop de requêtes, réessayez dans un instant.",
};

type UnauthorizedListener = () => void;
const adminUnauthorizedListeners = new Set<UnauthorizedListener>();

/** Appelé quand une route admin (hors connexion et /me) répond 401 : la session a disparu ou expiré. */
export function onAdminUnauthorized(listener: UnauthorizedListener): () => void {
  adminUnauthorizedListeners.add(listener);
  return () => void adminUnauthorizedListeners.delete(listener);
}

const ADMIN_PUBLIC_PATHS = ["/admin/login", "/admin/me"];

export async function request<T>(path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (init.body !== undefined) headers["Content-Type"] = "application/json";

  const res = await fetch(`${BASE}${path}`, {
    method: init.method ?? "GET",
    credentials: "include",
    headers,
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
  });

  const text = await res.text();
  let data: unknown;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = undefined;
    }
  }

  if (!res.ok) {
    if (res.status === 401 && path.startsWith("/admin/") && !ADMIN_PUBLIC_PATHS.includes(path)) {
      adminUnauthorizedListeners.forEach((listener) => listener());
    }
    const detail = (data as { detail?: unknown } | undefined)?.detail;
    const retry = Number(res.headers.get("Retry-After"));
    throw new ApiError(
      res.status,
      typeof detail === "string" ? detail : (DEFAULT_MESSAGES[res.status] ?? "Une erreur est survenue."),
      Number.isFinite(retry) && retry > 0 ? retry : undefined,
    );
  }
  return data as T;
}

export const api = {
  topicsFront: (limit = 10) =>
    request<{ items: FrontTopic[]; has_more: boolean }>(`/topics/front?limit=${limit}`),

  voteNext: (count = 10, seen: number[] = []) => {
    const q = new URLSearchParams({ count: String(count) });
    if (seen.length) q.set("seen", seen.join(","));
    return request<{ items: TopicCard[] }>(`/vote/next?${q}`);
  },

  vote: (vote: { topic_id: number; choice: VoteChoice }) =>
    request<Vote>("/votes", { method: "POST", body: vote }),

  claimVotes: (votes: Vote[]) =>
    request<{ claimed: number }>("/votes/claim", { method: "POST", body: { votes } }),

  myVotes: () => request<{ votes: Vote[] }>("/votes/mine"),

  magicLink: (email: string) =>
    request<void>("/auth/magic-link", { method: "POST", body: { email } }),

  verify: (token: string) => request<Me>("/auth/verify", { method: "POST", body: { token } }),

  logout: () => request<void>("/auth/logout", { method: "POST" }),

  /** Renvoie null si pas de session (401). */
  me: async (): Promise<Me | null> => {
    try {
      return await request<Me>("/me");
    } catch (e) {
      if (e instanceof ApiError && e.isUnauthorized) return null;
      throw e;
    }
  },

  adminLogin: (password: string) =>
    request<{ authenticated: true }>("/admin/login", { method: "POST", body: { password } }),

  adminLogout: () => request<void>("/admin/logout", { method: "POST" }),

  /** true si la session admin est valide, false sinon (401). */
  adminMe: async (): Promise<boolean> => {
    try {
      await request<{ authenticated: true }>("/admin/me");
      return true;
    } catch (e) {
      if (e instanceof ApiError && e.isUnauthorized) return false;
      throw e;
    }
  },

  adminSources: () => request<AdminSource[]>("/admin/sources"),

  adminAddSource: (source: { name: string; feed_url: string }) =>
    request<AdminSource>("/admin/sources", { method: "POST", body: source }),

  adminSetSourceActive: (id: number, active: boolean) =>
    request<AdminSource>(`/admin/sources/${id}/${active ? "reactivate" : "deactivate"}`, { method: "POST" }),

  /** `confirm` : nombre d’articles qui seront supprimés (le serveur refuse s’il a changé). */
  adminDeleteSource: (id: number, confirm: number) =>
    request<{ id: number; deleted_articles: number }>(`/admin/sources/${id}?confirm=${confirm}`, { method: "DELETE" }),

  halvingConfig: () => request<HalvingConfig>("/halving/config"),
};
