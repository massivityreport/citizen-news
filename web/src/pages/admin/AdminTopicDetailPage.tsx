import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import { useAdminTopic, useAdminTopicVotes } from "../../api/hooks";
import type { AdminSupportLevel as SupportLevel, AdminVoteChoice as VoteChoice } from "../../api/types";
import { LineChart } from "../../components/admin/LineChart";
import { Pager } from "../../components/admin/TableParts";
import { usePageTitle } from "../../components/usePageTitle";
import { formatFull } from "../../lib/format";
import styles from "./Admin.module.css";
import { STATE_LABELS } from "./AdminTopicsPage";

const CHOICES: Record<VoteChoice, string> = {
  more: "Il faut en parler",
  not_priority: "Pas prioritaire",
  unknown: "Je ne sais pas",
};
const LEVELS: Record<SupportLevel, string> = { low: "faible", medium: "moyen", high: "élevé" };

const when = (iso: string | null) => (iso ? <time dateTime={iso}>{formatFull(iso)}</time> : "—");

/** Détail d’un sujet : statut, raison à la une, votes (totaux, courbe, liste paginée) et articles. */
export default function AdminTopicDetailPage() {
  const params = useParams();
  const id = Number(params.id);
  const valid = Number.isInteger(id) && id > 0;
  const topic = useAdminTopic(valid ? id : 0);
  const title = topic.data?.title ?? "Sujet";
  const h1 = usePageTitle(title);
  const [votesPage, setVotesPage] = useState(1);
  const votes = useAdminTopicVotes(valid ? id : 0, { page: String(votesPage) });

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
  const daily = t.votes.daily;
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
          <dt>État</dt>
          <dd>
            {STATE_LABELS[t.state]}
            <small>vague {t.wave}</small>
          </dd>
        </div>
        <div>
          <dt>Dernier changement d’état</dt>
          <dd>
            {when(t.state_changed_at)}
            <small>Seul le dernier changement est conservé, pas d’historique.</small>
          </dd>
        </div>
        <div>
          <dt>Dernière évaluation</dt>
          <dd>{when(t.evaluated_at)}</dd>
        </div>
        <div>
          <dt>Articles</dt>
          <dd>{t.article_count}</dd>
        </div>
        <div>
          <dt>Sources distinctes</dt>
          <dd>{t.source_count}</dd>
        </div>
        <div>
          <dt>Soutien</dt>
          <dd>
            {LEVELS[t.support.level]}
            <small>
              score {t.support.score.toFixed(2)} · {t.support.votes_count} votes
            </small>
          </dd>
        </div>
        <div>
          <dt>À la une</dt>
          <dd>
            {t.front.on_front ? "Oui" : "Non"}
            <small>{t.front.reason ? `Raison affichée : ${t.front.reason.label}` : "N’est pas à la une"}</small>
          </dd>
        </div>
      </dl>

      <h2>Votes</h2>
      <dl className={styles.stats}>
        {(Object.keys(CHOICES) as VoteChoice[]).map((c) => (
          <div key={c}>
            <dt>{CHOICES[c]}</dt>
            <dd>{t.votes[c]}</dd>
          </div>
        ))}
        <div>
          <dt>Total</dt>
          <dd>{t.votes.total}</dd>
        </div>
        <div>
          <dt>Votants</dt>
          <dd>{t.votes.voters}</dd>
        </div>
      </dl>
      <LineChart
        title={`Votes par jour : ${t.title}`}
        yLabel="Votes par jour (UTC)"
        emptyText="Aucun vote pour le moment."
        series={(Object.keys(CHOICES) as VoteChoice[]).map((c) => ({
          id: c,
          label: CHOICES[c],
          points: daily.map((d) => ({ date: d.date, value: d[c] })),
        }))}
      />
      <p className={styles.muted}>30 derniers jours au plus, ou depuis le premier vote ; jours en UTC.</p>

      {votes.isPending && <p role="status">Chargement des votes…</p>}
      {votes.isError && (
        <p role="alert" className={styles.error}>
          Impossible de charger la liste des votes.
        </p>
      )}
      {votes.data &&
        (votes.data.total === 0 ? (
          <p role="status">Aucun vote.</p>
        ) : (
          <>
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <caption>Votes, du plus récent au plus ancien</caption>
                <thead>
                  <tr>
                    <th scope="col">Date</th>
                    <th scope="col">Choix</th>
                    <th scope="col">Numéro de compte</th>
                  </tr>
                </thead>
                <tbody>
                  {votes.data.items.map((v, i) => (
                    <tr key={`${v.account_id}-${i}`}>
                      <td>{when(v.date)}</td>
                      <td>{CHOICES[v.choice]}</td>
                      <td className={styles.num}>{v.account_id}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pager page={votes.data.page} pageSize={votes.data.page_size} total={votes.data.total} unit="votes" onPage={setVotesPage} />
          </>
        ))}

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
