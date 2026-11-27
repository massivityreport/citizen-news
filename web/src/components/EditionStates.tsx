import styles from "./Edition.module.css";
import topic from "./Topic.module.css";

export function EditionSkeleton({ label }: { label: string }) {
  return (
    <div aria-busy="true">
      <p role="status" className={topic.srOnly}>{label}</p>
      <div className={styles.skeleton} aria-hidden="true" />
    </div>
  );
}

export function LoadError({ message, onRetry, busy }: { message: string; onRetry: () => void; busy: boolean }) {
  return (
    <div className={styles.state} role="alert">
      <p>{message}</p>
      <button type="button" className={styles.btnSecondary} onClick={onRetry} disabled={busy}>
        Réessayer
      </button>
    </div>
  );
}
