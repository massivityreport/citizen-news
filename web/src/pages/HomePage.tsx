import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { FrontTopic } from "../api/types";
import { ReasonBadge, SupportIndicator } from "../components/Badges";
import { TopicImage } from "../components/TopicImage";
import { SourceList } from "../components/SourceList";
import topic from "../components/Topic.module.css";
import { usePageTitle } from "../components/usePageTitle";
import { formatDate, formatFull } from "../lib/format";
import styles from "./HomePage.module.css";

const TITLE = "La une citoyenne";

function FrontCard({ t }: { t: FrontTopic }) {
  const updated = formatDate(t.updated_at);
  const first = formatDate(t.first_seen_at);
  return (
    <article className={topic.card} aria-labelledby={`topic-${t.id}`}>
      <TopicImage url={t.image_url} title={t.title} />
      <ReasonBadge reason={t.reason} />
      <h2 id={`topic-${t.id}`}>{t.title}</h2>
      <p className={topic.summary}>{t.summary}</p>
      <SupportIndicator level={t.support.level} />
      <SourceList sources={t.sources} />
      <p className={topic.meta}>
        {first && (
          <>
            Apparu <time dateTime={t.first_seen_at} title={formatFull(t.first_seen_at)}>{first}</time>
          </>
        )}
        {first && updated && " · "}
        {updated && (
          <>
            mis à jour <time dateTime={t.updated_at} title={formatFull(t.updated_at)}>{updated}</time>
          </>
        )}
      </p>
    </article>
  );
}

function Skeletons() {
  return (
    <div aria-busy="true">
      <p role="status" className={topic.srOnly}>Chargement de la une…</p>
      <ul className={styles.list} aria-hidden="true">
        {[0, 1, 2].map((i) => (
          <li key={i}>
            <div className={styles.skeleton} />
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function HomePage() {
  const h1 = usePageTitle(TITLE);
  const { data, isPending, isError, refetch, isFetching } = useQuery({
    queryKey: ["topics", "front"],
    queryFn: () => api.topicsFront(20),
  });
  const items = data?.items ?? [];

  return (
    <section>
      <h1 ref={h1} tabIndex={-1}>{TITLE}</h1>
      <p className={styles.intro}>Les sujets qui comptent, tels que les citoyens les ont priorisés.</p>

      {isPending && <Skeletons />}

      {isError && (
        <div className={styles.state} role="alert">
          <p>Impossible de charger la une pour le moment.</p>
          <button type="button" className={styles.btn} onClick={() => void refetch()} disabled={isFetching}>
            Réessayer
          </button>
        </div>
      )}

      {data && items.length === 0 && (
        <div className={styles.state}>
          <p>La une est vide pour l’instant : aucun sujet n’a encore été retenu.</p>
        </div>
      )}

      {items.length > 0 && (
        <ul className={styles.list}>
          {items.map((t) => (
            <li key={t.id}>
              <FrontCard t={t} />
            </li>
          ))}
        </ul>
      )}

      <aside className={styles.cta} aria-label="Participer">
        <p>Vous aussi, dites ce qui compte pour vous.</p>
        <Link to="/jouer" className={styles.btn}>À vous de jouer</Link>
      </aside>
    </section>
  );
}
