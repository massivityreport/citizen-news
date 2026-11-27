import { Link, useSearchParams } from "react-router-dom";
import { useAdminTopics } from "../../api/hooks";
import type { TopicState } from "../../api/types";
import { intParam, Pager, useParamSetter, SortableTh, type SortState } from "../../components/admin/TableParts";
import { usePageTitle } from "../../components/usePageTitle";
import { formatFull } from "../../lib/format";
import styles from "./Admin.module.css";

export const STATE_LABELS: Record<TopicState, string> = {
  new: "Nouveau",
  active: "Actif",
  reserve: "En réserve",
  emerged: "Émergé",
};
const SORTS = ["title", "state", "votes", "articles", "state_changed"];
const DEFAULT_ORDER: Record<string, "asc" | "desc"> = { title: "asc", state: "asc", votes: "desc", articles: "desc", state_changed: "desc" };

/** Onglet Sujets : liste paginée et triable ; tri, filtre d’état et page dans l’URL. */
export default function AdminTopicsPage() {
  const h1 = usePageTitle("Sujets");
  const [sp] = useSearchParams();
  const sort = SORTS.includes(sp.get("sort") ?? "") ? sp.get("sort")! : "votes";
  const order = sp.get("order") === "asc" || sp.get("order") === "desc" ? (sp.get("order") as "asc" | "desc") : DEFAULT_ORDER[sort];
  const state = (Object.keys(STATE_LABELS) as TopicState[]).find((s) => s === sp.get("state")) ?? "";
  const page = intParam(sp.get("page"), 1);

  const set = useParamSetter();

  const topics = useAdminTopics({ page: String(page), sort, order, state });
  const current: SortState = { sort, order };
  const onSort = (column: string) =>
    set(column === sort ? { order: order === "asc" ? "desc" : "asc" } : { sort: column, order: DEFAULT_ORDER[column] });

  return (
    <section className={styles.section}>
      <h1 ref={h1} tabIndex={-1}>
        Sujets
      </h1>
      <form className={styles.filters} aria-label="Filtres des sujets" onSubmit={(e) => e.preventDefault()}>
        <label className={styles.field}>
          État
          <select value={state} onChange={(e) => set({ state: e.target.value })}>
            <option value="">Tous les états</option>
            {(Object.keys(STATE_LABELS) as TopicState[]).map((s) => (
              <option key={s} value={s}>
                {STATE_LABELS[s]}
              </option>
            ))}
          </select>
        </label>
      </form>

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
                "Aucun sujet ne correspond."
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
                    <SortableTh column="state" current={current} onSort={onSort}>
                      État
                    </SortableTh>
                    <SortableTh column="articles" current={current} onSort={onSort}>
                      Articles
                    </SortableTh>
                    <th scope="col">Sources</th>
                    <SortableTh column="votes" current={current} onSort={onSort}>
                      Votes
                    </SortableTh>
                    <SortableTh column="state_changed" current={current} onSort={onSort}>
                      Changement d’état
                    </SortableTh>
                  </tr>
                </thead>
                <tbody>
                  {topics.data.items.map((t) => (
                    <tr key={t.id}>
                      <th scope="row">
                        <Link to={`/admin/sujets/${t.id}`}>{t.title}</Link>
                      </th>
                      <td>
                        {STATE_LABELS[t.state]} <span className={styles.muted}>(vague {t.wave})</span>
                      </td>
                      <td className={styles.num}>{t.article_count}</td>
                      <td className={styles.num}>{t.source_count}</td>
                      <td className={styles.num}>{t.vote_count}</td>
                      <td>
                        {t.state_changed_at ? <time dateTime={t.state_changed_at}>{formatFull(t.state_changed_at)}</time> : <span className={styles.muted}>—</span>}
                      </td>
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
