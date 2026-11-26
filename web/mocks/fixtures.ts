import type { FrontTopic, TopicCard } from "../src/api/types";

const day = 86_400_000;
const ago = (ms: number) => new Date(Date.now() - ms).toISOString();

export const frontTopics: FrontTopic[] = [
  {
    id: 1,
    title: "Pénurie de médecins généralistes : des départements en alerte",
    summary: "Plusieurs départements signalent des délais de plus de trois mois pour obtenir un rendez-vous chez un généraliste.",
    sources: [
      { name: "Le Monde", url: "https://example.org/lemonde/medecins", title: "Déserts médicaux : la situation se tend", published_at: ago(5 * 3_600_000) },
      { name: "Ouest-France", url: "https://example.org/ouestfrance/medecins", title: "Sans médecin traitant, des milliers d’habitants", published_at: ago(9 * 3_600_000) },
      { name: "France Info", url: "https://example.org/franceinfo/medecins", title: "Santé : l’accès aux soins en question", published_at: ago(20 * 3_600_000) },
    ],
    first_seen_at: ago(3 * day),
    updated_at: ago(2 * 3_600_000),
    support: { level: "high", votes_count: 1284 },
    reason: { code: "common_priority", label: "Priorité commune" },
  },
  {
    id: 2,
    title: "Sécheresse hivernale : les nappes phréatiques sous le niveau habituel",
    summary: "Après un automne peu pluvieux, les relevés montrent des nappes basses dans le sud et le centre du pays.",
    sources: [
      { name: "Libération", url: "https://example.org/liberation/nappes", title: "Nappes phréatiques : un hiver inquiétant", published_at: ago(12 * 3_600_000) },
      { name: "Reporterre", url: "https://example.org/reporterre/nappes", title: "L’eau manque déjà", published_at: ago(30 * 3_600_000) },
    ],
    first_seen_at: ago(5 * day),
    updated_at: ago(8 * 3_600_000),
    support: { level: "high", votes_count: 972 },
    reason: { code: "strong_mobilisation", label: "Forte mobilisation" },
  },
  {
    id: 3,
    title: "Fermeture annoncée d’une maternité en zone rurale",
    summary: "L’agence régionale de santé confirme la fermeture du service d’ici l’été ; les élus locaux demandent un moratoire.",
    sources: [
      { name: "La Dépêche", url: "https://example.org/depeche/maternite", title: "La maternité fermera ses portes", published_at: ago(26 * 3_600_000) },
    ],
    first_seen_at: ago(2 * day),
    updated_at: ago(26 * 3_600_000),
    support: { level: "medium", votes_count: 214 },
    reason: { code: "under_the_radar", label: "Sous les radars" },
  },
  {
    id: 4,
    title: "Un nouveau protocole de recyclage des batteries testé en Europe",
    summary: "Un consortium de laboratoires annonce récupérer plus de 95 % des métaux d’une batterie de véhicule électrique.",
    sources: [
      { name: "Les Échos", url: "https://example.org/echos/batteries", title: "Batteries : le recyclage change d’échelle", published_at: ago(7 * 3_600_000) },
      { name: "Sciences et Avenir", url: "https://example.org/sciav/batteries", title: "Recycler 95 % d’une batterie, c’est possible", published_at: ago(15 * 3_600_000) },
    ],
    first_seen_at: ago(day),
    updated_at: ago(3 * 3_600_000),
    support: { level: "medium", votes_count: 301 },
    reason: { code: "emerging", label: "Sujet émergent" },
  },
  {
    id: 5,
    title: "Hausse des loyers étudiants dans les grandes villes",
    summary: "Une enquête montre une hausse moyenne de 6 % des loyers de petites surfaces à la rentrée.",
    sources: [
      { name: "Le Parisien", url: "https://example.org/parisien/loyers", title: "Se loger étudiant, un casse-tête", published_at: ago(40 * 3_600_000) },
    ],
    first_seen_at: ago(4 * day),
    updated_at: ago(day),
    support: { level: "low", votes_count: 57 },
    reason: { code: "under_the_radar", label: "Sous les radars" },
  },
];

export const voteDeck: TopicCard[] = [
  ...frontTopics.map((t) => ({
    id: t.id,
    title: t.title,
    summary: t.summary,
    sources: t.sources,
    first_seen_at: t.first_seen_at,
    updated_at: t.updated_at,
  })),
  {
    id: 6,
    title: "Ouverture d’une enquête sur l’étiquetage de produits alimentaires",
    summary: "Des associations de consommateurs dénoncent des mentions trompeuses sur des emballages courants.",
    sources: [{ name: "20 Minutes", url: "https://example.org/20min/etiquetage", title: "Étiquettes : l’enquête démarre", published_at: ago(6 * 3_600_000) }],
    first_seen_at: ago(day),
    updated_at: ago(6 * 3_600_000),
  },
  {
    id: 7,
    title: "Le festival du film documentaire menacé par des coupes budgétaires",
    summary: "Les organisateurs alertent sur une baisse de 30 % des subventions pour la prochaine édition.",
    sources: [{ name: "Télérama", url: "https://example.org/telerama/festival", title: "Un festival en sursis", published_at: ago(22 * 3_600_000) }],
    first_seen_at: ago(2 * day),
    updated_at: ago(22 * 3_600_000),
  },
];
