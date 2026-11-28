import { useEffect, useId, useRef, useState } from "react";
import styles from "./composer.module.css";

export interface FullDialogPlace {
  id: number;
  title: string;
}

/**
 * « Votre une est pleine » : s'ouvre quand on ajoute un sujet à une une complète. Deux étapes :
 * 1. la liste des sujets de la une, un par ligne, titres tronqués comme dans l'aperçu ; choisir celui à remplacer ;
 * 2. la confirmation, avec les deux titres en entier : « Remplacer » fait le remplacement, « Retour » revient à la liste.
 * « Annuler », Échap ou un clic hors de la fenêtre ne changent rien.
 */
export function FullDialog({
  incoming,
  places,
  busy,
  onReplace,
  onCancel,
}: {
  incoming: string;
  places: FullDialogPlace[];
  busy: boolean;
  onReplace: (id: number, place: number) => void;
  onCancel: () => void;
}) {
  const titleId = useId();
  const ref = useRef<HTMLDivElement>(null);
  const [choice, setChoice] = useState<{ id: number; place: number; title: string } | null>(null);

  // Rend le focus à l'élément d'origine à la fermeture.
  useEffect(() => {
    const previous = document.activeElement;
    return () => {
      if (previous instanceof HTMLElement) previous.focus();
    };
  }, []);

  // À chaque étape, le focus va sur son premier bouton.
  useEffect(() => {
    ref.current?.querySelector<HTMLElement>("button")?.focus();
  }, [choice]);

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape") return onCancel();
    if (e.key !== "Tab") return;
    const items = ref.current?.querySelectorAll<HTMLElement>("button:not([disabled])");
    if (!items?.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  return (
    <div className={styles.backdrop} onMouseDown={(e) => e.target === e.currentTarget && onCancel()}>
      <div ref={ref} role="dialog" aria-modal="true" aria-labelledby={titleId} className={styles.dialog} onKeyDown={onKeyDown}>
        {choice ? (
          <>
            <h2 id={titleId}>Confirmer le remplacement</h2>
            <dl className={styles.confirm}>
              <dt>Sujet retiré (place {choice.place})</dt>
              <dd>{choice.title}</dd>
              <dt>Remplacé par</dt>
              <dd>{incoming}</dd>
            </dl>
            <div className={styles.dialogActions}>
              <button type="button" className={styles.btn} disabled={busy} onClick={() => onReplace(choice.id, choice.place)}>
                Remplacer
              </button>
              <button type="button" className={`${styles.btn} ${styles.btnLight}`} disabled={busy} onClick={() => setChoice(null)}>
                Retour
              </button>
            </div>
          </>
        ) : (
          <>
            <h2 id={titleId}>Votre une est pleine</h2>
            <p className={styles.dialogText}>Choisissez le sujet à remplacer par « {incoming} », ou annulez.</p>
            <ol className={styles.replaceList}>
              {places.map((p, i) => (
                <li key={p.id}>
                  <button
                    type="button"
                    className={styles.replaceBtn}
                    aria-label={`Remplacer « ${p.title} » (place ${i + 1})`}
                    onClick={() => setChoice({ id: p.id, place: i + 1, title: p.title })}
                  >
                    <span className={styles.placeNum} aria-hidden="true">
                      {i + 1}
                    </span>
                    <span className={styles.placeTitle}>{p.title}</span>
                  </button>
                </li>
              ))}
            </ol>
            <div className={styles.dialogActions}>
              <button type="button" className={`${styles.btn} ${styles.btnLight}`} onClick={onCancel}>
                Annuler
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
