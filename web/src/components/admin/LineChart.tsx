import { useId } from "react";
import styles from "./LineChart.module.css";

export interface ChartPoint {
  /** AAAA-MM-JJ ou date ISO complète (lue en UTC). */
  date: string;
  value: number;
}

export interface ChartSeries {
  id: string;
  label: string;
  points: ChartPoint[];
}

interface Props {
  series: ChartSeries[];
  /** Titre lu par les lecteurs d’écran (<title> du SVG). */
  title: string;
  /** Légende de l’axe vertical, par ex. « Votes par jour ». */
  yLabel?: string;
  /** Texte affiché quand aucune série n’a de point. */
  emptyText?: string;
}

const W = 640;
const H = 280;
const M = { top: 14, right: 18, bottom: 34, left: 44 };
const DAY = 86_400_000;
// Couleurs validées (contraste ≥ 3:1 sur le fond blanc, séparation daltoniens) ; la forme du marqueur et le
// style du trait doublent la couleur (jamais la couleur seule).
const COLORS = ["var(--s0)", "var(--s1)", "var(--s2)"];
const DASHES = [undefined, "7 4", "2 4"];
const SHAPES = ["circle", "square", "triangle"] as const;

const dayFmt = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short", timeZone: "UTC" });
const fullFmt = new Intl.DateTimeFormat("fr-FR", { dateStyle: "long", timeZone: "UTC" });

const toTime = (date: string) => {
  const t = Date.parse(date.length === 10 ? `${date}T00:00:00Z` : date);
  return Number.isNaN(t) ? null : t;
};

/** Plus petit pas « rond » (1, 2, 5 × 10ⁿ) donnant au plus ~`count` graduations jusqu’à `max`. */
export function niceStep(max: number, count = 4): number {
  const raw = Math.max(max, 1) / count;
  const pow = 10 ** Math.floor(Math.log10(raw));
  const f = raw / pow;
  return Math.max(1, (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * pow); // des votes : graduations entières
}

function Marker({ shape, x, y, color }: { shape: (typeof SHAPES)[number]; x: number; y: number; color: string }) {
  const common = { fill: color, className: styles.marker };
  if (shape === "square") return <rect {...common} x={x - 4} y={y - 4} width={8} height={8} />;
  if (shape === "triangle") return <polygon {...common} points={`${x},${y - 5} ${x + 5},${y + 4} ${x - 5},${y + 4}`} />;
  return <circle {...common} cx={x} cy={y} r={4} />;
}

/** Courbe SVG sans dépendance : une ou plusieurs séries, axes datés, légende, titre et description pour lecteurs d’écran. */
export function LineChart({ series, title, yLabel, emptyText = "Aucune donnée à afficher." }: Props) {
  const uid = useId().replace(/:/g, "");
  const clean = series.slice(0, COLORS.length).map((s) => ({
    ...s,
    points: s.points
      .map((p) => ({ t: toTime(p.date), v: p.value }))
      .filter((p): p is { t: number; v: number } => p.t !== null && Number.isFinite(p.v))
      .sort((a, b) => a.t - b.t),
  }));
  const all = clean.flatMap((s) => s.points);
  const empty = all.length === 0;

  const tMin = empty ? 0 : Math.min(...all.map((p) => p.t));
  const tMax = empty ? 0 : Math.max(...all.map((p) => p.t));
  const vMax = empty ? 1 : Math.max(...all.map((p) => p.v), 1);
  const step = niceStep(vMax);
  const top = Math.ceil(vMax / step) * step;
  const plotW = W - M.left - M.right;
  const plotH = H - M.top - M.bottom;
  // Un seul instant : le point est centré.
  const x = (t: number) => M.left + (tMax === tMin ? plotW / 2 : ((t - tMin) / (tMax - tMin)) * plotW);
  const y = (v: number) => M.top + plotH - (v / top) * plotH;

  const yTicks: number[] = [];
  for (let v = 0; v <= top + 1e-9; v += step) yTicks.push(v);
  // Au plus 6 dates, réparties régulièrement, la première et la dernière toujours présentes.
  const days = Math.round((tMax - tMin) / DAY) + 1;
  const xTicks: number[] = [];
  if (!empty) {
    const n = Math.min(6, days);
    for (let i = 0; i < n; i++) xTicks.push(n === 1 ? tMin : tMin + Math.round(((days - 1) * i) / (n - 1)) * DAY);
  }

  const description = empty
    ? emptyText
    : clean
        .map((s) => {
          const total = s.points.reduce((a, p) => a + p.v, 0);
          const max = Math.max(...s.points.map((p) => p.v));
          return `${s.label} : ${s.points.length} point${s.points.length > 1 ? "s" : ""}, total ${total}, maximum ${max}`;
        })
        .join(". ") + `. Du ${fullFmt.format(tMin)} au ${fullFmt.format(tMax)}.`;

  return (
    <figure className={styles.figure}>
      <svg
        className={styles.svg}
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-labelledby={`${uid}t ${uid}d`}
      >
        <title id={`${uid}t`}>{title}</title>
        <desc id={`${uid}d`}>{description}</desc>
        {yTicks.map((v) => (
          <g key={v}>
            <line className={v === 0 ? styles.axis : styles.grid} x1={M.left} x2={W - M.right} y1={y(v)} y2={y(v)} />
            <text className={styles.tick} x={M.left - 6} y={y(v) + 4} textAnchor="end">
              {v}
            </text>
          </g>
        ))}
        {yLabel && (
          <text className={styles.tick} x={M.left} y={10} textAnchor="start">
            {yLabel}
          </text>
        )}
        {xTicks.map((t) => (
          <text key={t} className={styles.tick} x={x(t)} y={H - 12} textAnchor={xTicks.length === 1 ? "middle" : "middle"}>
            {dayFmt.format(t)}
          </text>
        ))}
        {empty && (
          <text className={styles.empty} x={W / 2} y={H / 2} textAnchor="middle">
            {emptyText}
          </text>
        )}
        {clean.map((s, i) => (
          <g key={s.id} data-series={s.id}>
            {s.points.length > 1 && (
              <polyline
                className={styles.line}
                stroke={COLORS[i]}
                strokeDasharray={DASHES[i]}
                points={s.points.map((p) => `${x(p.t)},${y(p.v)}`).join(" ")}
              />
            )}
            {(s.points.length <= 31 ? s.points : []).map((p) => (
              <Marker key={p.t} shape={SHAPES[i]} x={x(p.t)} y={y(p.v)} color={COLORS[i]} />
            ))}
          </g>
        ))}
      </svg>
      {clean.length > 0 && (
        <ul className={styles.legend} aria-label="Légende">
          {clean.map((s, i) => (
            <li key={s.id}>
              <svg viewBox="0 0 28 12" aria-hidden="true">
                <line className={styles.legendLine} stroke={COLORS[i]} strokeDasharray={DASHES[i]} x1="0" x2="28" y1="6" y2="6" />
                <Marker shape={SHAPES[i]} x={14} y={6} color={COLORS[i]} />
              </svg>
              {s.label}
            </li>
          ))}
        </ul>
      )}
    </figure>
  );
}
