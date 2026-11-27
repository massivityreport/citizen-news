import { Link } from "react-router-dom";
import { useCurrentEdition } from "../api/hooks";
import { Countdown } from "../components/Countdown";
import { EditionView } from "../components/EditionView";
import { EditionSkeleton, LoadError } from "../components/EditionStates";
import { usePageTitle } from "../components/usePageTitle";
import { formatEditionDate } from "../lib/format";
import styles from "../components/Edition.module.css";

const TITLE = "La une citoyenne";

export default function HomePage() {
  const { data, isPending, isError, refetch, isFetching, dataUpdatedAt } = useCurrentEdition();
  const edition = data?.edition ?? null;
  const h1 = usePageTitle(edition ? `${TITLE} du ${formatEditionDate(edition.date)}` : TITLE);

  return (
    <section>
      <h1 ref={h1} tabIndex={-1}>{TITLE}</h1>

      {isPending && <EditionSkeleton label="Chargement de la une…" />}

      {isError && !data && (
        <LoadError message="Impossible de charger la une pour le moment." onRetry={() => void refetch()} busy={isFetching} />
      )}

      {data && (
        <>
          <div className={styles.actions}>
            <Link to="/composer" className={styles.btn}>Composer ma une</Link>
          </div>
          <Countdown nextCloseAt={data.next_close_at} serverTime={data.server_time} receivedAt={dataUpdatedAt} />
          {edition ? (
            <EditionView edition={edition} />
          ) : (
            <div className={styles.state}>
              <p>La première une sera publiée à 17 h.</p>
            </div>
          )}
        </>
      )}
    </section>
  );
}
