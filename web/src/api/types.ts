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
