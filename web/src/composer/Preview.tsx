import { MAX_PLACES } from "../lib/draft";
import styles from "./composer.module.css";

/** Les dix places de la une, en zone compacte : numéro, titre tronqué (CSS) ou « Place libre ». */
export function Preview({ titles, highlight }: { titles: (string | null)[]; highlight?: number | null }) {
  return (
    <ol className={styles.preview} aria-label="Aperçu de ma une : dix places">
      {Array.from({ length: MAX_PLACES }, (_, i) => {
        const title = titles[i] ?? null;
        return (
          <li key={i} className={styles.place} data-free={title === null ? "true" : undefined} data-target={highlight === i ? "true" : undefined}>
            <span className={styles.placeNum} aria-hidden="true">
              {i + 1}
            </span>
            <span className={styles.placeTitle} title={title ?? undefined}>
              <span className={styles.srOnly}>Place {i + 1} : </span>
              {title ?? "Place libre"}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
