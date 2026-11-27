import { Link, useSearchParams } from "react-router-dom";
import { useAdminEditions } from "../../api/hooks";
import { intParam, Pager, useParamSetter } from "../../components/admin/TableParts";
import { usePageTitle } from "../../components/usePageTitle";
import { formatEditionDate, formatFull } from "../../lib/format";
import styles from "./Admin.module.css";

/** Onglet Éditions : les unes publiées, la plus récente d’abord. */
export default function AdminEditionsPage() {
  const h1 = usePageTitle("Éditions");
  const [sp] = useSearchParams();
  const page = intParam(sp.get("page"), 1);
  const set = useParamSetter();
  const editions = useAdminEditions({ page: String(page) });
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
          <p role="status">
            {editions.data.total === 0 ? (
              "Aucune édition n’a encore été publiée."
            ) : (
              <>
                Cette page n’existe pas.{" "}
                <button type="button" className={styles.small} onClick={() => set({ page: null })}>
                  Revenir à la première page
                </button>
              </>
            )}
          </p>
        ) : (
          <>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <caption>Éditions publiées : {editions.data.total}, page {editions.data.page}</caption>
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
          <Pager page={editions.data.page} pageSize={editions.data.page_size} total={editions.data.total} unit="éditions" onPage={(p) => set({ page: String(p) }, true)} />
          </>
        ))}
    </section>
  );
}
