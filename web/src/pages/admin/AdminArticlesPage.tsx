import { Link, useSearchParams } from "react-router-dom";
import { useAdminArticles, useAdminSources, useAdminTopics } from "../../api/hooks";
import { intParam, Pager, useParamSetter, SortableTh, type SortState } from "../../components/admin/TableParts";
import { usePageTitle } from "../../components/usePageTitle";
import { formatFull } from "../../lib/format";
import styles from "./Admin.module.css";

const SORTS = ["date", "source", "topic"];
const DEFAULT_ORDER: Record<string, "asc" | "desc"> = { date: "desc", source: "asc", topic: "asc" };

/** Onglet Articles. Tri, filtres et page vivent dans l’URL (lien partageable) : /admin/articles?sort=source&order=asc&page=2 */
export default function AdminArticlesPage() {
  const h1 = usePageTitle("Articles");
  const [sp] = useSearchParams();
  const sort = SORTS.includes(sp.get("sort") ?? "") ? sp.get("sort")! : "date";
  const order = sp.get("order") === "asc" || sp.get("order") === "desc" ? (sp.get("order") as "asc" | "desc") : DEFAULT_ORDER[sort];
  const page = intParam(sp.get("page"), 1);
  const ungrouped = sp.get("ungrouped") === "true";
  const topicId = sp.get("topic_id") ?? "";
  const sourceId = sp.get("source_id") ?? "";
  const dateFrom = sp.get("date_from") ?? "";
  const dateTo = sp.get("date_to") ?? "";

  const set = useParamSetter();

  const params: Record<string, string> = {
    page: String(page),
    sort,
    order,
    topic_id: ungrouped ? "" : topicId,
    source_id: sourceId,
    date_from: dateFrom,
    date_to: dateTo,
    ungrouped: ungrouped ? "true" : "",
  };
  const articles = useAdminArticles(params);
  const sources = useAdminSources();
  const topics = useAdminTopics({ sort: "title", order: "asc", page_size: "200" });

  const current: SortState = { sort, order };
  const onSort = (column: string) =>
    set(column === sort ? { order: order === "asc" ? "desc" : "asc" } : { sort: column, order: DEFAULT_ORDER[column] });
  const topicOptions = topics.data?.items ?? [];
  const known = topicOptions.some((t) => String(t.id) === topicId);

  return (
    <section className={styles.section}>
      <h1 ref={h1} tabIndex={-1}>
        Articles
      </h1>

      <form className={styles.filters} aria-label="Filtres des articles" onSubmit={(e) => e.preventDefault()}>
        <label className={styles.field}>
          Sujet
          <select value={topicId} disabled={ungrouped} onChange={(e) => set({ topic_id: e.target.value })}>
            <option value="">Tous les sujets</option>
            {topicId && !known && <option value={topicId}>Sujet n° {topicId}</option>}
            {topicOptions.map((t) => (
              <option key={t.id} value={t.id}>
                {t.title}
              </option>
            ))}
          </select>
        </label>
        <label className={styles.field}>
          Source
          <select value={sourceId} onChange={(e) => set({ source_id: e.target.value })}>
            <option value="">Toutes les sources</option>
            {sourceId && !sources.data?.some((s) => String(s.id) === sourceId) && <option value={sourceId}>Source n° {sourceId}</option>}
            {(sources.data ?? []).map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
                {s.active ? "" : " (désactivée)"}
              </option>
            ))}
          </select>
        </label>
        <label className={styles.field}>
          Publié du
          <input type="date" value={dateFrom} max={dateTo || undefined} onChange={(e) => set({ date_from: e.target.value })} />
        </label>
        <label className={styles.field}>
          au (inclus)
          <input type="date" value={dateTo} min={dateFrom || undefined} onChange={(e) => set({ date_to: e.target.value })} />
        </label>
        <label className={styles.check}>
          <input
            type="checkbox"
            checked={ungrouped}
            onChange={(e) => set({ ungrouped: e.target.checked ? "true" : null, topic_id: e.target.checked ? null : topicId })}
          />
          Non regroupés seulement
        </label>
      </form>
      <p className={styles.muted}>Dates en UTC (jour entier, bornes incluses) ; un article sans date de publication n’apparaît pas quand une date est choisie.</p>

      {articles.isPending && <p role="status">Chargement des articles…</p>}
      {articles.isError && (
        <p role="alert" className={styles.error}>
          Impossible de charger les articles. Vérifiez les filtres puis réessayez.
        </p>
      )}
      {articles.data && (
        <>
          {articles.data.items.length === 0 ? (
            <p role="status">
              {articles.data.total === 0 ? (
                "Aucun article ne correspond à ces filtres."
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
                  Articles : {articles.data.total} au total, page {articles.data.page}
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Titre</th>
                    <SortableTh column="source" current={current} onSort={onSort}>
                      Source
                    </SortableTh>
                    <SortableTh column="date" current={current} onSort={onSort}>
                      Publié
                    </SortableTh>
                    <SortableTh column="topic" current={current} onSort={onSort}>
                      Sujet
                    </SortableTh>
                  </tr>
                </thead>
                <tbody>
                  {articles.data.items.map((a) => (
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
                      <td>
                        {a.published_at ? (
                          <time dateTime={a.published_at}>{formatFull(a.published_at)}</time>
                        ) : (
                          <span className={styles.muted}>Date inconnue</span>
                        )}
                      </td>
                      <td>
                        {a.topic ? (
                          <>
                            <span className={`${styles.badge} ${styles.grouped}`}>regroupé</span>{" "}
                            <Link to={`/admin/sujets/${a.topic.id}`}>{a.topic.title}</Link>
                          </>
                        ) : (
                          <span className={`${styles.badge} ${styles.ungrouped}`}>non regroupé</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <Pager page={articles.data.page} pageSize={articles.data.page_size} total={articles.data.total} unit="articles" onPage={(p) => set({ page: String(p) }, true)} />
        </>
      )}
    </section>
  );
}
