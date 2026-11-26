const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["day", 86_400_000],
  ["hour", 3_600_000],
  ["minute", 60_000],
];

const relative = new Intl.RelativeTimeFormat("fr", { numeric: "auto" });
const absolute = new Intl.DateTimeFormat("fr-FR", { dateStyle: "long" });
const absoluteWithTime = new Intl.DateTimeFormat("fr-FR", { dateStyle: "long", timeStyle: "short" });

const WEEK = 7 * 86_400_000;

/** « il y a 3 heures » jusqu'à une semaine, puis « 12 novembre 2026 ». Date invalide : chaîne vide. */
export function formatDate(iso: string, now: number = Date.now()): string {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "";
  const diff = now - t;
  if (diff < 0 || diff >= WEEK) return absolute.format(t);
  if (diff < 60_000) return "à l’instant";
  for (const [unit, ms] of UNITS) {
    if (diff >= ms) return relative.format(-Math.floor(diff / ms), unit);
  }
  return "à l’instant";
}

/** Date complète pour l'attribut title des balises <time>. */
export function formatFull(iso: string): string {
  const t = Date.parse(iso);
  return Number.isNaN(t) ? "" : absoluteWithTime.format(t);
}

/** Ne laisse passer que les liens http(s) venant de l'API. */
export function safeHref(url: string): string | undefined {
  try {
    const u = new URL(url);
    return u.protocol === "https:" || u.protocol === "http:" ? u.href : undefined;
  } catch {
    return undefined;
  }
}
