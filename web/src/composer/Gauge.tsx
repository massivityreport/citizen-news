import { useId } from "react";
import { MAX_PLACES } from "../lib/draft";
import styles from "./composer.module.css";

/** Jauge « n/10 sujets » : texte visible relié à la barre (role="progressbar"). */
export function Gauge({ count }: { count: number }) {
  const id = useId();
  const n = Math.min(MAX_PLACES, Math.max(0, count));
  return (
    <div className={styles.gauge}>
      <span id={id} className={styles.gaugeText}>
        {n}/{MAX_PLACES} sujets
      </span>
      <div
        role="progressbar"
        aria-labelledby={id}
        aria-valuemin={0}
        aria-valuemax={MAX_PLACES}
        aria-valuenow={n}
        aria-valuetext={`${n} sujet${n > 1 ? "s" : ""} sur ${MAX_PLACES}`}
        className={styles.gaugeTrack}
      >
        <div className={styles.gaugeFill} style={{ width: `${(n / MAX_PLACES) * 100}%` }} />
      </div>
    </div>
  );
}
