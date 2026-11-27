export type SupportLevel = "low" | "medium" | "high";
export type ReasonCode = "common_priority" | "strong_mobilisation" | "under_the_radar" | "emerging";
export type VoteChoice = "more" | "not_priority" | "unknown";

export interface Source {
  name: string;
  url: string;
  title: string;
  published_at: string;
}

export interface Support {
  level: SupportLevel;
  votes_count: number;
}

export interface Reason {
  code: ReasonCode;
  label: string;
}

/** Carte sans support : renvoyée par /vote/next (résultats masqués avant le vote). */
export interface TopicCard {
  id: number;
  title: string;
  summary: string;
  sources: Source[];
  /** https validée côté serveur, ou null. Chargée en hotlink par le navigateur. */
  image_url: string | null;
  first_seen_at: string;
  updated_at: string;
}

export interface FrontTopic extends TopicCard {
  support: Support;
  reason: Reason;
}

export interface Vote {
  topic_id: number;
  choice: VoteChoice;
}

export interface HalvingParams {
  min_votes_first_decision: number;
  keep_ratio: number;
  waves: number;
  new_topic_traffic_share: number;
  rescue_share: number;
}

export interface HalvingConfig {
  params: HalvingParams;
  description: Record<string, string>;
}

export interface Me {
  email: string;
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
  support: { score: number; level: SupportLevel; votes_count: number };
  front: { on_front: boolean; reason: Reason | null };
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
  choice: VoteChoice;
  account_id: number;
}
