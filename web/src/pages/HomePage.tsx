import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { FrontTopic } from "../api/types";
import { ReasonBadge, SupportIndicator } from "../components/Badges";
import { SourceList } from "../components/SourceList";
import topic from "../components/Topic.module.css";
import { usePageTitle } from "../components/usePageTitle";
import { formatDate, formatFull } from "../lib/format";
import styles from "./HomePage.module.css";

const TITLE = "La une citoyenne";
const PAGE = 10;
const MAX = 50;

function FrontCard({ t }: { t: FrontTopic }) {
  const updated = formatDate(t.updated_at);
  const first = formatDate(t.first_seen_at);
  return (
    <article className={topic.card} aria-labelledby={`topic-${t.id}`}>
      <ReasonBadge reason={t.reason} />
      <h2 id={`topic-${t.id}`} tabIndex={-1}>{t.title}</h2>
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
  const [limit, setLimit] = useState(PAGE);
  const { data: fresh, isPending, isError, refetch, isFetching, isPlaceholderData } = useQuery({
    queryKey: ["topics", "front", limit],
    queryFn: () => api.topicsFront(limit),
    placeholderData: keepPreviousData,
  });
  // En cas d'erreur, la requête perd ses données : on garde la dernière liste valide à l'écran.
  const [last, setLast] = useState(fresh);
  if (fresh && fresh !== last) setLast(fresh);
  const data = fresh ?? last;
  const items = data?.items ?? [];
  const loadingMore = isFetching && isPlaceholderData;
  const moreBtn = useRef<HTMLButtonElement>(null);
  const clicked = useRef(false);
  // Le bouton garde le focus au clic ; s'il disparaît (fin de liste), le focus passe au premier nouvel élément.
  useEffect(() => {
    if (!clicked.current || isPlaceholderData) return;
    clicked.current = false;
    if (!moreBtn.current) {
      document.querySelector<HTMLElement>(`#topic-${items[Math.min(limit - PAGE, items.length - 1)]?.id}`)?.focus();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isPlaceholderData, data, limit]);

  return (
    <section>
      <h1 ref={h1} tabIndex={-1}>{TITLE}</h1>
      <p className={styles.intro}>Les sujets qui comptent, tels que les citoyens les ont priorisés.</p>

      {isPending && <Skeletons />}

      {isError && !data && (
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

      {isError && data && (
        <div className={styles.state} role="alert">
          <p>Impossible de charger plus de sujets pour le moment.</p>
          <button type="button" className={styles.btn} onClick={() => void refetch()} disabled={isFetching}>
            Réessayer
          </button>
        </div>
      )}

      {data?.has_more && limit < MAX && !isError && (
        <p className={styles.more}>
          <button
            ref={moreBtn}
            type="button"
            className={styles.btn}
            aria-disabled={loadingMore || undefined}
            onClick={() => {
              if (loadingMore) return;
              clicked.current = true;
              setLimit((l) => Math.min(l + PAGE, MAX));
            }}
          >
            {loadingMore ? "Chargement…" : "Voir plus"}
          </button>
        </p>
      )}

      <aside className={styles.cta} aria-label="Participer">
        <p>Vous aussi, dites ce qui compte pour vous.</p>
        <Link to="/jouer" className={styles.btn}>À vous de jouer</Link>
      </aside>
    </section>
  );
}
