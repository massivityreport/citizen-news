import { useAdminStats } from "../../api/hooks";
import type { AdminStats } from "../../api/types";
import { LineChart } from "../../components/admin/LineChart";
import { usePageTitle } from "../../components/usePageTitle";
import styles from "./Admin.module.css";

const number = new Intl.NumberFormat("fr-FR");

const TILES: { label: string; value: (s: AdminStats) => number }[] = [
  { label: "Articles (24 h)", value: (s) => s.last_24h.articles },
  { label: "Articles (total)", value: (s) => s.total.articles },
  { label: "Participants (24 h)", value: (s) => s.last_24h.participants },
  { label: "Participants (total)", value: (s) => s.total.participants },
  { label: "Unes enregistrées (24 h)", value: (s) => s.last_24h.selections },
  { label: "Unes enregistrées (total)", value: (s) => s.total.selections },
];

const CURVES: { key: "articles" | "participants" | "selections"; title: string; yLabel: string; description: string }[] = [
  {
    key: "articles",
    title: "Articles ingérés par jour",
    yLabel: "Articles par jour",
    description: "Articles récupérés ce jour-là (date d’ingestion).",
  },
  {
    key: "participants",
    title: "Participants par jour",
    yLabel: "Participants par jour",
    description: "Comptes ayant une une non vide ce jour-là. Un même compte compte une fois par jour : on ne peut pas additionner les jours.",
  },
  {
    key: "selections",
    title: "Unes enregistrées par jour",
    yLabel: "Unes par jour",
    description: "Unes enregistrées ce jour-là (une par compte et par jour au plus).",
  },
];

/** Accueil du backoffice : chiffres clés et courbes sur 30 jours (jours en UTC). */
export function AdminHomePage() {
  const h1 = usePageTitle("Administration");
  const stats = useAdminStats();
  const data = stats.data;
  return (
    <section className={styles.section}>
      <h1 ref={h1} tabIndex={-1}>
        Administration
      </h1>
      <div className={styles.pager}>
        <button type="button" className={styles.small} onClick={() => void stats.refetch()} disabled={stats.isFetching}>
          {stats.isFetching ? "Actualisation…" : "Actualiser"}
        </button>
        <span className={styles.muted}>
          {data && stats.dataUpdatedAt ? (
            <>Mis à jour à {new Date(stats.dataUpdatedAt).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}</>
          ) : null}
        </span>
      </div>

      {stats.isPending && <p role="status">Chargement des statistiques…</p>}
      {stats.isError && !data && (
        <p role="alert" className={styles.error}>
          Impossible de charger les statistiques. Cliquez sur « Actualiser » pour réessayer.
        </p>
      )}
      {stats.isError && data && (
        <p role="alert" className={styles.error}>
          L’actualisation a échoué : les chiffres affichés peuvent être anciens.
        </p>
      )}

      {data && (
        <>
          <h2>Chiffres clés</h2>
          <dl className={styles.stats}>
            {TILES.map((t) => (
              <div key={t.label}>
                <dt>{t.label}</dt>
                <dd>{number.format(t.value(data))}</dd>
              </div>
            ))}
          </dl>
          <p className={styles.muted}>« 24 h » : les dernières 24 heures glissantes. Articles : selon la date d’ingestion.</p>

          <h2>Les 30 derniers jours</h2>
          {CURVES.map((c) => {
            const empty = data.series.every((d) => d[c.key] === 0);
            return (
              <div key={c.key} className={styles.section}>
                <p style={{ margin: 0 }}>
                  <strong>{c.title}</strong>
                  <br />
                  <span className={styles.muted}>{c.description}</span>
                </p>
                <LineChart
                  title={`${c.title}, 30 derniers jours`}
                  yLabel={c.yLabel}
                  emptyText="Aucune donnée sur les 30 derniers jours."
                  series={[
                    {
                      id: c.key,
                      label: c.title,
                      points: empty ? [] : data.series.map((d) => ({ date: d.date, value: d[c.key] })),
                    },
                  ]}
                />
              </div>
            );
          })}
          <p className={styles.muted}>Jours en UTC, aujourd’hui compris.</p>
        </>
      )}
    </section>
  );
}
