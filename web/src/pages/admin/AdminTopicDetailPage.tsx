import { Link, useParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import { useAdminTopic } from "../../api/hooks";
import { usePageTitle } from "../../components/usePageTitle";
import { formatEditionDate, formatFull, formatPercent } from "../../lib/format";
import styles from "./Admin.module.css";

const when = (iso: string | null) => (iso ? <time dateTime={iso}>{formatFull(iso)}</time> : "—");

/** Détail d’un sujet : approbations de l’édition en cours, historique par édition publiée et articles. */
export default function AdminTopicDetailPage() {
  const params = useParams();
  const id = Number(params.id);
  const valid = Number.isInteger(id) && id > 0;
  const topic = useAdminTopic(valid ? id : 0);
  const title = topic.data?.title ?? "Sujet";
  const h1 = usePageTitle(title);

  const back = <Link to="/admin/sujets">← Tous les sujets</Link>;
  if (!valid || (topic.isError && topic.error instanceof ApiError && topic.error.status === 404)) {
    return (
      <section className={styles.section}>
        {back}
        <h1 ref={h1} tabIndex={-1}>
          Sujet introuvable
        </h1>
        <p role="status">Ce sujet n’existe pas (ou plus).</p>
      </section>
    );
  }
  if (topic.isPending) return <p role="status">Chargement du sujet…</p>;
  if (topic.isError)
    return (
      <section className={styles.section}>
        {back}
        <p role="alert" className={styles.error}>
          Impossible de charger le sujet. Réessayez dans un instant.
        </p>
      </section>
    );

  const t = topic.data;
  return (
    <section className={styles.section}>
      {back}
      <h1 ref={h1} tabIndex={-1}>
        {t.title}
      </h1>
      {t.summary && <p className={styles.muted}>{t.summary}</p>}

      <h2>Statut</h2>
      <dl className={styles.stats}>
        <div>
          <dt>Approbations (édition en cours)</dt>
          <dd>
            {t.approvals}
            <small>Comptes qui ont ce sujet dans leur une.</small>
          </dd>
        </div>
        <div>
          <dt>Première apparition</dt>
          <dd>{when(t.first_seen_at)}</dd>
        </div>
        <div>
          <dt>Dernière mise à jour</dt>
          <dd>{when(t.updated_at)}</dd>
        </div>
        <div>
          <dt>Articles</dt>
          <dd>{t.article_count}</dd>
        </div>
        <div>
          <dt>Médias distincts</dt>
          <dd>{t.source_count}</dd>
        </div>
      </dl>

      <h2>Historique par édition</h2>
      {t.history.length === 0 ? (
        <p role="status">Ce sujet n’a figuré dans aucune édition publiée.</p>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <caption>Approbations par édition publiée, de la plus récente à la plus ancienne</caption>
            <thead>
              <tr>
                <th scope="col">Édition</th>
                <th scope="col">Rang</th>
                <th scope="col">Approbations</th>
                <th scope="col">Proportion</th>
              </tr>
            </thead>
            <tbody>
              {t.history.map((h) => (
                <tr key={h.edition_date}>
                  <th scope="row">
                    <Link to={`/admin/editions/${h.edition_date}`}>{formatEditionDate(h.edition_date)}</Link>
                  </th>
                  <td className={styles.num}>{h.rank ?? "—"}</td>
                  <td className={styles.num}>{h.approvals}</td>
                  <td className={styles.num}>{formatPercent(h.proportion)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h2>Articles</h2>
      {t.articles.length === 0 ? (
        <p role="status">Aucun article.</p>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <caption>
              Articles du sujet ({t.article_count}
              {t.articles_truncated ? `, les ${t.articles.length} plus récents affichés` : ""})
            </caption>
            <thead>
              <tr>
                <th scope="col">Titre</th>
                <th scope="col">Source</th>
                <th scope="col">Publié</th>
              </tr>
            </thead>
            <tbody>
              {t.articles.map((a) => (
                <tr key={a.id}>
                  <th scope="row">
                    <a href={a.url} target="_blank" rel="noopener noreferrer">
                      {a.title}
                    </a>
                  </th>
                  <td>
                    {a.source.name}
                    {!a.source.active && (
                      <>
                        {" "}
                        <span className={`${styles.badge} ${styles.off}`}>source désactivée</span>
                      </>
                    )}
                  </td>
                  <td>{when(a.published_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
