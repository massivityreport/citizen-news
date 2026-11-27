export interface Source {
  name: string;
  url: string;
  title: string;
  published_at: string;
}

/** Sujet du bassin (contrat V2) : aucun compteur d'approbation avant la publication. */
export interface TopicCard {
  id: number;
  title: string;
  summary: string;
  sources: Source[];
  article_count: number;
  source_count: number;
  first_seen_at: string;
  updated_at: string;
  /** https validée côté serveur, ou null. Chargée en hotlink par le navigateur. */
  image_url: string | null;
}

/** Sujet figé d'une édition publiée. `topic_id` peut être null (sujet supprimé depuis). */
export interface EditionTopic {
  rank: number;
  topic_id: number | null;
  title: string;
  summary: string;
  sources: Source[];
  source_count: number;
  article_count: number;
  approvals: number;
  /** approvals / participants, entre 0 et 1. */
  proportion: number;
  image_url: string | null;
}

export interface Edition {
  /** Date locale AAAA-MM-JJ de la clôture : clé et permalien. */
  date: string;
  published_at: string;
  participants: number;
  topics: EditionTopic[];
}

export interface CurrentEdition {
  edition: Edition | null;
  next_close_at: string;
  server_time: string;
}

export interface EditionSummary {
  date: string;
  published_at: string;
  participants: number;
  topic_count: number;
}

// Types propres au backoffice V1 : conservés tels quels jusqu'à la refonte de l'admin (tâches suivantes).
export type AdminSupportLevel = "low" | "medium" | "high";
export type AdminVoteChoice = "more" | "not_priority" | "unknown";
export interface AdminReason {
  code: string;
  label: string;
}

export interface Me {
  email: string;
}

export interface VerifyResult extends Me {
  /** Brouillon de une fusionné à la vérification (null : aucun, ou édition fermée). */
  draft?: { added: number; ignored: number } | null;
}

export interface AdminSource {
  id: number;
  name: string;
  feed_url: string;
  active: boolean;
  article_count: number;
  last_article_at: string | null;
}

export type TopicState = "new" | "active" | "reserve" | "emerged";

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface AdminSourceRef {
  id: number;
  name: string;
  active: boolean;
}

export interface AdminArticle {
  id: number;
  title: string;
  url: string;
  source: AdminSourceRef;
  published_at: string | null;
  fetched_at: string;
  topic: { id: number; title: string } | null;
  grouped: boolean;
}

export interface AdminTopicRow {
  id: number;
  title: string;
  state: TopicState;
  wave: number;
  state_changed_at: string | null;
  article_count: number;
  source_count: number;
  vote_count: number;
  image_url: string | null;
}

export interface AdminStatsCounts {
  articles: number;
  votes: number;
  voters: number;
}

export interface AdminStats {
  last_24h: AdminStatsCounts;
  total: AdminStatsCounts;
  /** 30 jours UTC, aujourd’hui compris, un point par jour. `voters` : distincts par jour, non cumulables. */
  series: { date: string; articles: number; votes: number; voters: number }[];
}

export interface AdminVoteDay {
  date: string;
  more: number;
  not_priority: number;
  unknown: number;
  total: number;
}

export interface AdminTopicDetail {
  id: number;
  title: string;
  summary: string;
  state: TopicState;
  wave: number;
  first_seen_at: string;
  updated_at: string;
  state_changed_at: string | null;
  evaluated_at: string | null;
  article_count: number;
  source_count: number;
  support: { score: number; level: AdminSupportLevel; votes_count: number };
  front: { on_front: boolean; reason: AdminReason | null };
  votes: {
    more: number;
    not_priority: number;
    unknown: number;
    total: number;
    voters: number;
    first_vote_at: string | null;
    daily: AdminVoteDay[];
  };
  articles: { id: number; title: string; url: string; source: AdminSourceRef; published_at: string | null }[];
  articles_truncated: boolean;
}

export interface AdminVote {
  date: string;
  choice: AdminVoteChoice;
  account_id: number;
}
