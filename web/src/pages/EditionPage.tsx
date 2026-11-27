import { Link, useParams } from "react-router-dom";
import { useEdition } from "../api/hooks";
import { ApiError } from "../api/client";
import { EditionView } from "../components/EditionView";
import { EditionSkeleton, LoadError } from "../components/EditionStates";
import { usePageTitle } from "../components/usePageTitle";
import { EDITION_DATE_RE, formatEditionDate } from "../lib/format";
import styles from "../components/Edition.module.css";

const NOT_FOUND = "Édition introuvable";

export default function EditionPage() {
  const { date = "" } = useParams();
  const validDate = EDITION_DATE_RE.test(date);
  const { data, error, isPending, isError, refetch, isFetching } = useEdition(date, validDate);
  const notFound = !validDate || (error instanceof ApiError && error.status === 404);
  const title = notFound ? NOT_FOUND : `La une du ${formatEditionDate(date)}`;
  const h1 = usePageTitle(title);

  return (
    <section>
      <h1 ref={h1} tabIndex={-1}>{title}</h1>
      {notFound ? (
        <div className={styles.state}>
          <p>Aucune une n’a été publiée à cette date.</p>
          <p>
            <Link to="/archives">Voir toutes les unes publiées</Link> · <Link to="/">Retour à la une du jour</Link>
          </p>
        </div>
      ) : isError ? (
        <LoadError message="Impossible de charger cette une pour le moment." onRetry={() => void refetch()} busy={isFetching} />
      ) : isPending ? (
        <EditionSkeleton label="Chargement de la une…" />
      ) : (
        <EditionView edition={data} showPermalink={false} />
      )}
    </section>
  );
}
