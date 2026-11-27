import { Link, useParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import { useAdminEdition } from "../../api/hooks";
import { usePageTitle } from "../../components/usePageTitle";
import { EDITION_DATE_RE, formatEditionDate, formatFull, formatPercent } from "../../lib/format";
import styles from "./Admin.module.css";

/** Détail d’une édition publiée : approbations et proportion de chaque sujet retenu. */
export default function AdminEditionDetailPage() {
  const { date = "" } = useParams();
  const valid = EDITION_DATE_RE.test(date);
  const edition = useAdminEdition(valid ? date : "");
  const h1 = usePageTitle(valid ? `Édition du ${formatEditionDate(date)}` : "Édition introuvable");
  const back = <Link to="/admin/editions">← Toutes les éditions</Link>;

  if (!valid || (edition.isError && edition.error instanceof ApiError && edition.error.status === 404)) {
    return (
      <section className={styles.section}>
        {back}
        <h1 ref={h1} tabIndex={-1}>
          Édition introuvable
        </h1>
        <p role="status">Cette édition n’existe pas.</p>
      </section>
    );
  }
  if (edition.isPending) return <p role="status">Chargement de l’édition…</p>;
  if (edition.isError)
    return (
      <section className={styles.section}>
        {back}
        <p role="alert" className={styles.error}>
          Impossible de charger l’édition. Réessayez dans un instant.
        </p>
      </section>
    );

  const e = edition.data;
  return (
    <section className={styles.section}>
      {back}
      <h1 ref={h1} tabIndex={-1}>
        Édition du {formatEditionDate(e.date)}
      </h1>
      <dl className={styles.stats}>
        <div>
          <dt>Publication</dt>
          <dd>
            <time dateTime={e.published_at}>{formatFull(e.published_at)}</time>
          </dd>
        </div>
        <div>
          <dt>Participants</dt>
          <dd>{e.participants}</dd>
        </div>
        <div>
          <dt>Sujets retenus</dt>
          <dd>{e.topics.length}</dd>
        </div>
      </dl>
      {e.topics.length === 0 ? (
        <p role="status">Aucun sujet retenu : aucune approbation.</p>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <caption>Sujets de la une, par rang</caption>
            <thead>
              <tr>
                <th scope="col">Rang</th>
                <th scope="col">Sujet</th>
                <th scope="col">Approbations</th>
                <th scope="col">Proportion</th>
                <th scope="col">Médias</th>
              </tr>
            </thead>
            <tbody>
              {e.topics.map((t) => (
                <tr key={t.rank}>
                  <td className={styles.num}>{t.rank}</td>
                  <th scope="row">{t.topic_id === null ? t.title : <Link to={`/admin/sujets/${t.topic_id}`}>{t.title}</Link>}</th>
                  <td className={styles.num}>{t.approvals}</td>
                  <td className={styles.num}>{formatPercent(t.proportion)}</td>
                  <td className={styles.num}>{t.source_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
