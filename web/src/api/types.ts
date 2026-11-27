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

export type PoolTab = "random" | "recent" | "radar";

/** Bassin du jour (contrat V2). `items` : 300 au plus, sans pagination. */
export interface Pool {
  edition_date: string;
  closes_at: string;
  open: boolean;
  total: number;
  items: TopicCard[];
}

/** Une personnelle de l'édition en cours (sans compteur), contrat V2. */
export interface Une {
  edition_date: string;
  closes_at: string;
  open: boolean;
  topic_ids: number[];
}

export interface MergeResult {
  added: number;
  ignored: number;
  une: Une;
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

/** Ligne de GET /api/admin/topics (contrat V2) : approbations de l'édition en cours. */
export interface AdminTopicRow {
  id: number;
  title: string;
  article_count: number;
  source_count: number;
  updated_at: string;
  approvals: number;
  image_url: string | null;
}

export interface AdminStatsCounts {
  articles: number;
  /** Comptes ayant une une non vide. */
  participants: number;
  /** Unes enregistrées. */
  selections: number;
}

export interface AdminStats {
  last_24h: AdminStatsCounts;
  total: AdminStatsCounts;
  /** 30 jours UTC, un point par jour. */
  series: { date: string; articles: number; participants: number; selections: number }[];
}

/** Approbations d'un sujet dans une édition publiée. */
export interface AdminTopicHistory {
  edition_date: string;
  approvals: number;
  proportion: number;
  rank: number | null;
}

export interface AdminTopicDetail {
  id: number;
  title: string;
  summary: string;
  first_seen_at: string;
  updated_at: string;
  article_count: number;
  source_count: number;
  /** Approbations de l'édition en cours. */
  approvals: number;
  /** 30 dernières éditions publiées, la plus récente d'abord. */
  history: AdminTopicHistory[];
  articles: { id: number; title: string; url: string; source: AdminSourceRef; published_at: string | null }[];
  articles_truncated: boolean;
}

export type TieCriterion = "source_count" | "updated_at" | "id";

export interface AdminPreviewItem {
  rank: number;
  topic_id: number;
  title: string;
  approvals: number;
  proportion: number;
  source_count: number;
  article_count: number;
  updated_at: string;
  tied_with: number[];
  broken_by: TieCriterion | null;
}

export interface AdminPreviewTie {
  approvals: number;
  topic_ids: number[];
  broken_by: TieCriterion;
  /** L'égalité enjambe la coupure entre le 10e et le 11e rang. */
  crosses_cut: boolean;
}

export interface AdminPreview {
  computed_at: string;
  edition_date: string;
  participants: number;
  topics: AdminPreviewItem[];
  next: AdminPreviewItem[];
  ties: AdminPreviewTie[];
}
