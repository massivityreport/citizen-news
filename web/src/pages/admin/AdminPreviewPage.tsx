import { useAdminPreview } from "../../api/hooks";
import type { AdminPreview, AdminPreviewItem, AdminPreviewTie, TieCriterion } from "../../api/types";
import { usePageTitle } from "../../components/usePageTitle";
import { formatEditionDate, formatFull, formatPercent, plural } from "../../lib/format";
import styles from "./Admin.module.css";

const CRITERIA: Record<TieCriterion, string> = {
  source_count: "le nombre de médias",
  updated_at: "la mise à jour la plus récente",
  id: "l’identifiant du sujet (ordre fixe)",
};

function ItemRows({ items, titles }: { items: AdminPreviewItem[]; titles: Map<number, string> }) {
  return (
    <>
      {items.map((t) => (
        <tr key={t.topic_id}>
          <td className={styles.num}>{t.rank}</td>
          <th scope="row">{t.title}</th>
          <td className={styles.num}>{t.approvals}</td>
          <td className={styles.num}>{formatPercent(t.proportion)}</td>
          <td className={styles.num}>{t.source_count}</td>
          <td>
            {t.tied_with.length > 0 ? (
              <>
                Égalité avec {t.tied_with.map((id) => titles.get(id) ?? `sujet ${id}`).join(", ")}
                {t.broken_by && <span className={styles.muted}> — départagé par {CRITERIA[t.broken_by]}</span>}
              </>
            ) : (
              <span className={styles.muted}>—</span>
            )}
          </td>
        </tr>
      ))}
    </>
  );
}

function Header() {
  return (
    <thead>
      <tr>
        <th scope="col">Rang</th>
        <th scope="col">Sujet</th>
        <th scope="col">Approbations</th>
        <th scope="col">Proportion</th>
        <th scope="col">Médias</th>
        <th scope="col">Égalité</th>
      </tr>
    </thead>
  );
}

function Ties({ ties, titles }: { ties: AdminPreviewTie[]; titles: Map<number, string> }) {
  if (ties.length === 0) return null;
  return (
    <>
      <h2 id="egalites">Sujets à égalité</h2>
      <ul className={styles.ties}>
        {ties.map((t) => (
          <li key={t.topic_ids.join("-")}>
            {t.crosses_cut && (
              <p role="alert" className={styles.cutAlert}>
                Attention : cette égalité franchit la coupure entre le 10<sup>e</sup> et le 11<sup>e</sup> rang. Le critère de départage décide
                quels sujets entrent dans la une.
              </p>
            )}
            <p style={{ margin: 0 }}>
              <strong>{plural(t.approvals, "approbation", "approbations")}</strong> chacun :{" "}
              {t.topic_ids.map((id) => titles.get(id) ?? `sujet ${id}`).join(" · ")}
              <br />
              <span className={styles.muted}>Départagés par {CRITERIA[t.broken_by]}.</span>
            </p>
          </li>
        ))}
      </ul>
    </>
  );
}

function Result({ data }: { data: AdminPreview }) {
  const titles = new Map([...data.topics, ...data.next].map((t) => [t.topic_id, t.title]));
  if (data.topics.length === 0 && data.next.length === 0) {
    return <p role="status">Aucune une enregistrée pour le moment : il n’y a rien à agréger.</p>;
  }
  return (
    <>
      <h2 id="dix">Les dix sujets de la une</h2>
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <caption>Rangs 1 à {data.topics.length || 10}</caption>
          <Header />
          <tbody>
            <ItemRows items={data.topics} titles={titles} />
          </tbody>
        </table>
      </div>

      <Ties ties={data.ties} titles={titles} />

      <div className={styles.cut} role="separator" aria-label="Coupure : en dessous, les sujets ne seraient pas publiés">
        <span>Coupure — en dessous, hors de la une</span>
      </div>

      <h2 id="suivants">Rangs 11 à 20</h2>
      {data.next.length === 0 ? (
        <p role="status">Aucun autre sujet n’a d’approbation.</p>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <caption>Sujets juste derrière la une</caption>
            <Header />
            <tbody>
              <ItemRows items={data.next} titles={titles} />
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

/** Prévisualisation de la une : même calcul que la clôture, mais rien n’est publié ni figé. */
export default function AdminPreviewPage() {
  const h1 = usePageTitle("Prévisualisation de la une");
  const preview = useAdminPreview();
  const data = preview.data;
  return (
    <section className={styles.section}>
      <h1 ref={h1} tabIndex={-1}>
        Prévisualisation de la une
      </h1>
      <p className={styles.previewBanner} role="note">
        <strong>Prévisualisation — rien n’est publié ni figé, réservé à l’administration</strong>
      </p>
      <div className={styles.pager}>
        <button type="button" className={styles.small} onClick={() => void preview.refetch()} disabled={preview.isFetching}>
          {preview.isFetching ? "Calcul…" : "Recalculer"}
        </button>
        {data && (
          <span className={styles.muted}>
            Calculé à <time dateTime={data.computed_at}>{formatFull(data.computed_at)}</time>
          </span>
        )}
      </div>

      {preview.isPending && <p role="status">Calcul de l’aperçu…</p>}
      {preview.isError && (
        <p role="alert" className={styles.error}>
          {data ? "Le recalcul a échoué : l’aperçu affiché peut être ancien." : "Impossible de calculer l’aperçu. Cliquez sur « Recalculer » pour réessayer."}
        </p>
      )}
      {data && (
        <>
          <dl className={styles.stats}>
            <div>
              <dt>Édition</dt>
              <dd>{formatEditionDate(data.edition_date)}</dd>
            </div>
            <div>
              <dt>Participants</dt>
              <dd>{data.participants}</dd>
            </div>
          </dl>
          <Result data={data} />
        </>
      )}
    </section>
  );
}
