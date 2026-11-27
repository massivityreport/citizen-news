import { Link } from "react-router-dom";
import { useEditions } from "../api/hooks";
import { editionPath } from "../components/EditionView";
import { EditionSkeleton, LoadError } from "../components/EditionStates";
import { usePageTitle } from "../components/usePageTitle";
import { formatClock, formatEditionDate, plural } from "../lib/format";
import styles from "../components/Edition.module.css";

const TITLE = "Archives";

export default function ArchivesPage() {
  const h1 = usePageTitle(TITLE);
  const { data, isPending, isError, refetch, isFetching } = useEditions(30);

  return (
    <section>
      <h1 ref={h1} tabIndex={-1}>{TITLE}</h1>
      <p className={styles.facts}>Les unes citoyennes des 30 dernières éditions, de la plus récente à la plus ancienne.</p>
      {isPending && <EditionSkeleton label="Chargement des archives…" />}
      {isError && <LoadError message="Impossible de charger les archives pour le moment." onRetry={() => void refetch()} busy={isFetching} />}
      {data && data.items.length === 0 && (
        <div className={styles.state}>
          <p>Aucune une n’a encore été publiée.</p>
        </div>
      )}
      {data && data.items.length > 0 && (
        <ul className={styles.archives}>
          {data.items.map((e) => (
            <li key={e.date}>
              <Link to={editionPath(e.date)}>{formatEditionDate(e.date)}</Link>
              <p>
                Publiée à {formatClock(e.published_at)} · {plural(e.participants, "participant", "participants")} ·{" "}
                {plural(e.topic_count, "sujet", "sujets")}
              </p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
