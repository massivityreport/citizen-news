import type { Edition, EditionTopic } from "../src/api/types";

const topic = (rank: number, title: string, approvals: number, over: Partial<EditionTopic> = {}): EditionTopic => ({
  rank,
  topic_id: rank,
  title,
  summary: `Résumé factuel du sujet « ${title} ».`,
  sources: [
    { name: "Le Monde", url: "https://example.org/a", title: `${title} (A)`, published_at: "2026-11-26T09:00:00Z" },
    { name: "Ouest-France", url: "https://example.org/b", title: `${title} (B)`, published_at: "2026-11-26T11:30:00Z" },
  ],
  source_count: 2,
  article_count: 3,
  approvals,
  proportion: approvals / 120,
  image_url: null,
  ...over,
});

export const editions: Edition[] = [
  {
    date: "2026-11-26",
    published_at: "2026-11-26T16:00:00Z",
    participants: 120,
    topics: [
      topic(1, "Pénurie de médecins dans les campagnes", 80),
      topic(2, "Budget : le vote à l’Assemblée", 64),
      topic(3, "Canicule hivernale en Australie", 41),
    ],
  },
  { date: "2026-11-25", published_at: "2026-11-25T16:00:00Z", participants: 0, topics: [] },
];
