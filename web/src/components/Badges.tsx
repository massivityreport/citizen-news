import type { Reason, SupportLevel } from "../api/types";
import styles from "./Topic.module.css";

const SUPPORT: Record<SupportLevel, { label: string; filled: number }> = {
  low: { label: "Soutien faible", filled: 1 },
  medium: { label: "Soutien moyen", filled: 2 },
  high: { label: "Soutien élevé", filled: 3 },
};

/** Niveau de soutien : texte + nombre de barres remplies (jamais la couleur seule). */
export function SupportIndicator({ level }: { level: SupportLevel }) {
  const info = SUPPORT[level] ?? { label: "Soutien inconnu", filled: 0 };
  return (
    <p className={styles.support} data-level={level}>
      <span className={styles.bars} aria-hidden="true">
        {[1, 2, 3].map((n) => (
          <span key={n} className={n <= info.filled ? styles.barOn : styles.bar} />
        ))}
      </span>
      <span>{info.label}</span>
    </p>
  );
}

/** Raison de présence dans la une. Un code inconnu s'affiche avec son label. */
export function ReasonBadge({ reason }: { reason: Reason }) {
  return (
    <span className={styles.reason} data-reason={reason.code}>
      {reason.label}
    </span>
  );
}
