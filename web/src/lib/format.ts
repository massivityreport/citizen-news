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

const longDate = new Intl.DateTimeFormat("fr-FR", { dateStyle: "long", timeZone: "UTC" });
const publishedFmt = new Intl.DateTimeFormat("fr-FR", {
  day: "numeric",
  month: "long",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZoneName: "short",
});
const timeFmt = new Intl.DateTimeFormat("fr-FR", { hour: "2-digit", minute: "2-digit" });

export const EDITION_DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

/** « 26 novembre 2026 » depuis une date locale AAAA-MM-JJ (sans décalage de fuseau). Invalide : la chaîne telle quelle. */
export function formatEditionDate(date: string): string {
  if (!EDITION_DATE_RE.test(date)) return date;
  const t = Date.parse(`${date}T00:00:00Z`);
  return Number.isNaN(t) ? date : longDate.format(t);
}

/** « 26 novembre 2026 à 17:00 UTC+1 » : fuseau du lecteur, nommé. */
export function formatPublished(iso: string): string {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "";
  const parts = publishedFmt.formatToParts(t);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return `${get("day")} ${get("month")} ${get("year")} à ${get("hour")}:${get("minute")} ${get("timeZoneName")}`;
}

/** « 17:00 » en heure locale du lecteur. */
export function formatClock(iso: string): string {
  const t = Date.parse(iso);
  return Number.isNaN(t) ? "" : timeFmt.format(t);
}

/** « 67 % » ; borné à 0-100. */
export function formatPercent(proportion: number): string {
  const p = Math.min(1, Math.max(0, Number.isFinite(proportion) ? proportion : 0));
  return `${Math.round(p * 100)} %`;
}

export const plural = (n: number, one: string, many: string) => `${n} ${n > 1 ? many : one}`;

/** « 2 h 05 min 09 s » ; « 4 min 09 s » ; « 9 s ». */
export function formatCountdown(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  if (h > 0) return `${h} h ${pad(m)} min ${pad(s)} s`;
  if (m > 0) return `${m} min ${pad(s)} s`;
  return `${s} s`;
}
