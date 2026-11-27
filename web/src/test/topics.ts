import type { Pool, TopicCard, Une } from "../api/types";

export const CLOSE = "2026-11-27T16:00:00Z";

export const card = (id: number, over: Partial<TopicCard> = {}): TopicCard => ({
  id,
  title: `Sujet ${id}`,
  summary: `Résumé du sujet ${id}.`,
  sources: [{ name: "Le Monde", url: `https://example.org/${id}`, title: `Article ${id}`, published_at: "2026-11-27T08:00:00Z" }],
  article_count: 9,
  source_count: 5,
  first_seen_at: "2026-11-27T06:00:00Z",
  updated_at: "2026-11-27T09:00:00Z",
  image_url: null,
  ...over,
});

export const pool = (ids: number[], over: Partial<Pool> = {}): Pool => ({
  edition_date: "2026-11-27",
  closes_at: CLOSE,
  open: true,
  total: ids.length,
  items: ids.map((i) => card(i)),
  ...over,
});

export const une = (ids: number[], over: Partial<Une> = {}): Une => ({
  edition_date: "2026-11-27",
  closes_at: CLOSE,
  open: true,
  topic_ids: ids,
  ...over,
});
