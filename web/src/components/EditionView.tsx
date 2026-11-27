import { Link } from "react-router-dom";
import type { Edition, EditionTopic } from "../api/types";
import { formatEditionDate, formatPercent, formatPublished, plural } from "../lib/format";
import { ShareButton } from "./ShareButton";
import { SourceList } from "./SourceList";
import { TopicImage } from "./TopicImage";
import styles from "./Edition.module.css";
import topic from "./Topic.module.css";

export const editionPath = (date: string) => `/une/${date}`;
export const editionUrl = (date: string) => `${window.location.origin}${editionPath(date)}`;

function EditionTopicCard({ t }: { t: EditionTopic }) {
  const id = `edition-topic-${t.rank}`;
  return (
    <article className={topic.card} aria-labelledby={id}>
      <TopicImage url={t.image_url} title={t.title} />
      <p className={styles.rank}>
        <span aria-hidden="true">#{t.rank}</span>
        <span className={topic.srOnly}>Sujet n° {t.rank}</span>
      </p>
      <h2 id={id}>{t.title}</h2>
      <p className={topic.summary}>{t.summary}</p>
      <p className={styles.proportion}>
        <strong>{formatPercent(t.proportion)} des unes</strong>
        <span className={styles.muted}> · {plural(t.approvals, "approbation", "approbations")}</span>
      </p>
      <p className={topic.meta}>
        {plural(t.source_count, "média", "médias")} · {plural(t.article_count, "article", "articles")}
      </p>
      <SourceList sources={t.sources} />
    </article>
  );
}

/** Une publiée : en-tête (publication, participants, lien permanent, partage) puis les sujets. */
export function EditionView({ edition, showPermalink = true }: { edition: Edition; showPermalink?: boolean }) {
  const url = editionUrl(edition.date);
  const published = formatPublished(edition.published_at);
  return (
    <div>
      <p className={styles.facts}>
        Publiée le <time dateTime={edition.published_at}>{published}</time> ·{" "}
        {plural(edition.participants, "participant", "participants")}
      </p>
      {showPermalink && (
        <p className={styles.permalink}>
          Lien permanent : <Link to={editionPath(edition.date)}>{url}</Link>
        </p>
      )}
      <p>
        <ShareButton url={url} title={`La une citoyenne du ${formatEditionDate(edition.date)}`} />
      </p>

      {edition.topics.length === 0 ? (
        <div className={styles.state}>
          <p>Personne n’a encore composé de une : cette édition ne contient aucun sujet.</p>
        </div>
      ) : (
        <ol className={styles.list}>
          {edition.topics.map((t) => (
            <li key={t.rank}>
              <EditionTopicCard t={t} />
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
