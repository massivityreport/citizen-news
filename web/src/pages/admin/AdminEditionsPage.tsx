import { Link } from "react-router-dom";
import { useAdminEditions } from "../../api/hooks";
import { usePageTitle } from "../../components/usePageTitle";
import { formatEditionDate, formatFull } from "../../lib/format";
import styles from "./Admin.module.css";

/** Onglet Éditions : les unes publiées, la plus récente d’abord. */
export default function AdminEditionsPage() {
  const h1 = usePageTitle("Éditions");
  const editions = useAdminEditions();
  return (
    <section className={styles.section}>
      <h1 ref={h1} tabIndex={-1}>
        Éditions
      </h1>
      {editions.isPending && <p role="status">Chargement des éditions…</p>}
      {editions.isError && (
        <p role="alert" className={styles.error}>
          Impossible de charger les éditions. Réessayez dans un instant.
        </p>
      )}
      {editions.data &&
        (editions.data.items.length === 0 ? (
          <p role="status">Aucune édition n’a encore été publiée.</p>
        ) : (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <caption>Éditions publiées : {editions.data.items.length}</caption>
              <thead>
                <tr>
                  <th scope="col">Date</th>
                  <th scope="col">Publication</th>
                  <th scope="col">Participants</th>
                  <th scope="col">Sujets</th>
                </tr>
              </thead>
              <tbody>
                {editions.data.items.map((e) => (
                  <tr key={e.date}>
                    <th scope="row">
                      <Link to={`/admin/editions/${e.date}`}>{formatEditionDate(e.date)}</Link>
                    </th>
                    <td>
                      <time dateTime={e.published_at}>{formatFull(e.published_at)}</time>
                    </td>
                    <td className={styles.num}>{e.participants}</td>
                    <td className={styles.num}>{e.topic_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
    </section>
  );
}
