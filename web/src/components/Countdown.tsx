import { formatClock, formatCountdown } from "../lib/format";
import { useCountdown } from "./useCountdown";
import styles from "./Edition.module.css";

/**
 * Compte à rebours vers la prochaine une. Le minuteur visuel change chaque seconde mais n'est pas annoncé
 * (role="timer" : aria-live désactivé) ; une phrase statique donne l'heure locale pour les lecteurs d'écran.
 */
export function Countdown({ nextCloseAt, serverTime, receivedAt }: { nextCloseAt: string; serverTime: string; receivedAt: number }) {
  const remaining = useCountdown(nextCloseAt, serverTime, receivedAt);
  const clock = formatClock(nextCloseAt);
  return (
    <div className={styles.countdown}>
      <p className={styles.countdownLabel}>
        Prochaine une à <time dateTime={nextCloseAt}>{clock}</time> (heure de votre appareil)
      </p>
      {remaining !== null && remaining > 0 ? (
        <p className={styles.timer} role="timer" aria-label="Temps restant avant la prochaine une">
          <span aria-hidden="true">dans </span>
          <span data-testid="countdown">{formatCountdown(remaining)}</span>
        </p>
      ) : (
        <p className={styles.timer} role="status">
          Publication en cours…
        </p>
      )}
    </div>
  );
}
