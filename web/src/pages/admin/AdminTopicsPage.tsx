import { Link, useSearchParams } from "react-router-dom";
import { useAdminTopics } from "../../api/hooks";
import { intParam, Pager, useParamSetter, SortableTh, type SortState } from "../../components/admin/TableParts";
import { usePageTitle } from "../../components/usePageTitle";
import { formatFull } from "../../lib/format";
import styles from "./Admin.module.css";

const SORTS = ["title", "articles", "updated", "approvals"];
const DEFAULT_ORDER: Record<string, "asc" | "desc"> = { title: "asc", articles: "desc", updated: "desc", approvals: "desc" };

/** Onglet Sujets : liste paginée et triable ; tri et page dans l’URL. */
export default function AdminTopicsPage() {
  const h1 = usePageTitle("Sujets");
  const [sp] = useSearchParams();
  const sort = SORTS.includes(sp.get("sort") ?? "") ? sp.get("sort")! : "approvals";
  const order = sp.get("order") === "asc" || sp.get("order") === "desc" ? (sp.get("order") as "asc" | "desc") : DEFAULT_ORDER[sort];
  const page = intParam(sp.get("page"), 1);

  const set = useParamSetter();

  const topics = useAdminTopics({ page: String(page), sort, order });
  const current: SortState = { sort, order };
  const onSort = (column: string) =>
    set(column === sort ? { order: order === "asc" ? "desc" : "asc" } : { sort: column, order: DEFAULT_ORDER[column] });

  return (
    <section className={styles.section}>
      <h1 ref={h1} tabIndex={-1}>
        Sujets
      </h1>
      <p className={styles.muted}>Approbations : nombre de comptes qui ont le sujet dans leur une de l’édition en cours.</p>

      {topics.isPending && <p role="status">Chargement des sujets…</p>}
      {topics.isError && (
        <p role="alert" className={styles.error}>
          Impossible de charger les sujets. Réessayez dans un instant.
        </p>
      )}
      {topics.data && (
        <>
          {topics.data.items.length === 0 ? (
            <p role="status">
              {topics.data.total === 0 ? (
                "Aucun sujet pour le moment."
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
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <caption>
                  Sujets : {topics.data.total} au total, page {topics.data.page}
                </caption>
                <thead>
                  <tr>
                    <SortableTh column="title" current={current} onSort={onSort}>
                      Titre
                    </SortableTh>
                    <SortableTh column="articles" current={current} onSort={onSort}>
                      Articles
                    </SortableTh>
                    <th scope="col">Médias</th>
                    <SortableTh column="updated" current={current} onSort={onSort}>
                      Mise à jour
                    </SortableTh>
                    <SortableTh column="approvals" current={current} onSort={onSort}>
                      Approbations
                    </SortableTh>
                  </tr>
                </thead>
                <tbody>
                  {topics.data.items.map((t) => (
                    <tr key={t.id}>
                      <th scope="row">
                        <Link to={`/admin/sujets/${t.id}`}>{t.title}</Link>
                      </th>
                      <td className={styles.num}>{t.article_count}</td>
                      <td className={styles.num}>{t.source_count}</td>
                      <td>
                        <time dateTime={t.updated_at}>{formatFull(t.updated_at)}</time>
                      </td>
                      <td className={styles.num}>{t.approvals}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <Pager page={topics.data.page} pageSize={topics.data.page_size} total={topics.data.total} unit="sujets" onPage={(p) => set({ page: String(p) }, true)} />
        </>
      )}
    </section>
  );
}
