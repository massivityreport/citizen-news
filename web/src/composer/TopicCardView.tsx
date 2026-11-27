import type { TopicCard } from "../api/types";
import { SourceList } from "../components/SourceList";
import { TopicImage } from "../components/TopicImage";
import { formatDate, formatFull, plural } from "../lib/format";
import styles from "./composer.module.css";

/**
 * Carte d'un sujet pendant la composition. Jamais de compteur d'approbation ni de popularité (contrat V2 :
 * l'API n'en envoie pas, et l'interface n'en montre pas).
 */
export function TopicCardView({
  topic,
  inUne,
  position,
  total,
  scrollRef,
}: {
  topic: TopicCard;
  inUne: boolean;
  position: number;
  total: number;
  scrollRef?: React.Ref<HTMLDivElement>;
}) {
  return (
    <article className={styles.card} data-in-une={inUne ? "true" : undefined} aria-labelledby={`topic-${topic.id}`}>
      <div className={styles.cardTop}>
        <p className={styles.cardMeta}>
          {inUne ? (
            <span className={styles.badge}>
              <span aria-hidden="true">✓ </span>Dans ma une
            </span>
          ) : (
            <span />
          )}
          <span className={styles.position} data-testid="position">
            <span className={styles.srOnly}>Sujet </span>
            {position}/{total}
          </span>
        </p>
        <TopicImage key={topic.id} url={topic.image_url} title={topic.title} />
        <h3 id={`topic-${topic.id}`} className={styles.cardTitle}>
          {topic.title}
        </h3>
      </div>
      <div className={styles.cardScroll} ref={scrollRef}>
        {topic.summary && <p className={styles.summary}>{topic.summary}</p>}
        <p className={styles.counts}>
          {plural(topic.article_count, "article", "articles")} · {plural(topic.source_count, "média", "médias")}
        </p>
        <p className={styles.counts}>
          Mis à jour <time dateTime={topic.updated_at} title={formatFull(topic.updated_at)}>{formatDate(topic.updated_at)}</time>
        </p>
        <SourceList sources={topic.sources} headingLevel="h4" />
      </div>
    </article>
  );
}
