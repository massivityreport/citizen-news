import { Link, useSearchParams } from "react-router-dom";
import { useAdminFeedback } from "../../api/hooks";
import { intParam, Pager, useParamSetter } from "../../components/admin/TableParts";
import { usePageTitle } from "../../components/usePageTitle";
import { formatFull } from "../../lib/format";
import { KIND_LABELS } from "../../lib/feedbackLabels";
import styles from "./Admin.module.css";

/** Onglet Avis : les avis reçus du site public, le plus récent d’abord (seul endroit du backoffice qui montre des e-mails). */
export default function AdminFeedbackPage() {
  const h1 = usePageTitle("Avis");
  const [sp] = useSearchParams();
  const page = intParam(sp.get("page"), 1);
  const unreadOnly = sp.get("unread_only") === "true";
  const set = useParamSetter();
  const feedback = useAdminFeedback({ page: String(page), unread_only: unreadOnly ? "true" : "" });
  return (
    <section className={styles.section}>
      <h1 ref={h1} tabIndex={-1}>
        Avis
      </h1>
      <label className={styles.filterRow}>
        <input type="checkbox" checked={unreadOnly} onChange={(e) => set({ unread_only: e.target.checked ? "true" : null })} />
        Non lus seulement
      </label>
      {feedback.isPending && <p role="status">Chargement des avis…</p>}
      {feedback.isError && (
        <p role="alert" className={styles.error}>
          Impossible de charger les avis. Réessayez dans un instant.
        </p>
      )}
      {feedback.data &&
        (feedback.data.items.length === 0 ? (
          <p role="status">
            {feedback.data.total > 0 ? (
              <>
                Cette page n’existe pas.{" "}
                <button type="button" className={styles.small} onClick={() => set({ page: null }, true)}>
                  Revenir à la première page
                </button>
              </>
            ) : unreadOnly ? (
              "Aucun avis non lu."
            ) : (
              "Aucun avis pour le moment."
            )}
          </p>
        ) : (
          <>
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <caption>
                  Avis : {feedback.data.total}, page {feedback.data.page}
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Date</th>
                    <th scope="col">Type</th>
                    <th scope="col">E-mail</th>
                    <th scope="col">Page</th>
                    <th scope="col">Message</th>
                    <th scope="col">État</th>
                  </tr>
                </thead>
                <tbody>
                  {feedback.data.items.map((f) => (
                    <tr key={f.id} className={f.is_read ? undefined : styles.unreadRow}>
                      <td>
                        <time dateTime={f.created_at}>{formatFull(f.created_at)}</time>
                      </td>
                      <td>{KIND_LABELS[f.kind]}</td>
                      <td>{f.email}</td>
                      <td>{f.page_name}</td>
                      <th scope="row">
                        <Link to={`/admin/avis/${f.id}`}>{f.excerpt}</Link>
                      </th>
                      <td>
                        {!f.is_read && <span className={styles.unreadMark}>Non lu</span>}
                        {f.answered && <span className={styles.badge}>Répondu</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pager page={feedback.data.page} pageSize={feedback.data.page_size} total={feedback.data.total} unit="avis" onPage={(p) => set({ page: String(p) }, true)} />
          </>
        ))}
    </section>
  );
}
