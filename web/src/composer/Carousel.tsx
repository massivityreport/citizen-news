import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import type { TopicCard } from "../api/types";
import { TopicCardView } from "./TopicCardView";
import { useSwipe, type SwipeDirection } from "./useSwipe";
import styles from "./composer.module.css";

export interface CarouselActions {
  onPrev: () => void;
  onNext: () => void;
  onAdd: () => void;
  onRemove: () => void;
}

const HINTS: Record<SwipeDirection, string> = {
  left: "Suivant ›",
  right: "‹ Précédent",
  up: "▲ Ajouter à ma une",
  down: "▼ Retirer de ma une",
};

function prefersReducedMotion(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/**
 * Un sujet à la fois. Gestes (glisser gauche/droite/haut/bas) et flèches du clavier appellent les mêmes actions
 * que les boutons de la barre. Vertical : réservé au geste tant que le contenu de la carte tient dans l'espace ;
 * sinon la zone de contenu défile (touch-action: pan-y) et le haut de la carte (image, titre) reste la zone de geste.
 */
export function Carousel({
  topic,
  inUne,
  position,
  total,
  actions,
  disabled,
}: {
  topic: TopicCard;
  inUne: boolean;
  position: number;
  total: number;
  actions: CarouselActions;
  /** Lecture seule (clôture) : plus de geste d'ajout ni de retrait. */
  disabled?: boolean;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [scrollable, setScrollable] = useState(false);

  function run(direction: SwipeDirection) {
    if (direction === "left") actions.onNext();
    else if (direction === "right") actions.onPrev();
    else if (disabled) return;
    else if (direction === "up") actions.onAdd();
    else actions.onRemove();
  }

  const { handlers, drag } = useSwipe(run);
  const reducedMotion = prefersReducedMotion();

  // Le contenu dépasse-t-il ? Alors la zone de contenu garde le défilement vertical natif.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const measure = () => setScrollable(el.scrollHeight > el.clientHeight + 1);
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [topic.id]);

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    // Le focus peut être n'importe où dans le carrousel, sauf là où les flèches ont déjà un sens.
    if ((e.target as HTMLElement).closest('input, select, textarea, [role="tablist"], [contenteditable="true"]')) return;
    const direction: Record<string, SwipeDirection> = { ArrowLeft: "right", ArrowRight: "left", ArrowUp: "up", ArrowDown: "down" };
    const d = direction[e.key];
    if (!d) return;
    e.preventDefault();
    run(d);
  }

  // Mouvement réduit : la carte ne suit plus le doigt ; l'étiquette du geste suffit comme retour.
  const style = drag && !reducedMotion
    ? { transform: drag.axis === "x" ? `translateX(${drag.dx * 0.6}px)` : `translateY(${drag.dy * 0.4}px)`, transition: "none" }
    : undefined;

  return (
    <div
      className={styles.carousel}
      role="group"
      aria-roledescription="carrousel"
      aria-label="Sujets à explorer. Flèches gauche et droite : sujet précédent ou suivant ; flèche haut : ajouter ; flèche bas : retirer."
      tabIndex={0}
      onKeyDown={onKeyDown}
      data-scrollable={scrollable ? "true" : "false"}
      data-gesture={drag?.direction}
      data-armed={drag?.armed ? "true" : undefined}
      {...handlers}
    >
      <div className={styles.swipeSurface} style={style}>
        <TopicCardView topic={topic} inUne={inUne} position={position} total={total} scrollRef={scrollRef} />
      </div>
      {drag && (
        <p className={styles.hint} aria-hidden="true" data-armed={drag.armed ? "true" : undefined}>
          {HINTS[drag.direction]}
        </p>
      )}
    </div>
  );
}

/** Boutons toujours visibles, ancrés en bas (hors défilement, zone sûre incluse). */
export function ActionBar({
  actions,
  canPrev,
  canNext,
  inUne,
  readOnly,
  addLabel,
}: {
  actions: CarouselActions;
  canPrev: boolean;
  canNext: boolean;
  inUne: boolean;
  readOnly: boolean;
  addLabel: string;
}) {
  return (
    <div className={styles.bar} role="group" aria-label="Actions sur le sujet">
      <button type="button" className={styles.navBtn} onClick={actions.onPrev} disabled={!canPrev}>
        <span aria-hidden="true">‹ </span>Précédent
      </button>
      {inUne ? (
        <button type="button" className={`${styles.mainBtn} ${styles.removeBtn}`} onClick={actions.onRemove} disabled={readOnly}>
          Retirer de ma une
        </button>
      ) : (
        <button type="button" className={styles.mainBtn} onClick={actions.onAdd} disabled={readOnly}>
          {addLabel}
        </button>
      )}
      <button type="button" className={styles.navBtn} onClick={actions.onNext} disabled={!canNext}>
        Suivant<span aria-hidden="true"> ›</span>
      </button>
    </div>
  );
}
