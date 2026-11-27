import { useRef, useState, type PointerEvent as ReactPointerEvent } from "react";

export type SwipeDirection = "left" | "right" | "up" | "down";

/** Mouvement minimal avant de décider de l'axe (px). */
export const SLOP = 10;
/** L'axe retenu doit dominer l'autre d'au moins ce rapport : une diagonale ou un défilement vertical ne déclenche rien. */
export const AXIS_RATIO = 1.5;
/** Distance minimale sur l'axe retenu pour valider le geste (px). */
export const THRESHOLD = 64;

export interface Drag {
  dx: number;
  dy: number;
  axis: "x" | "y";
  /** Direction du geste en cours. */
  direction: SwipeDirection;
  /** Le seuil est atteint : relâcher valide l'action. */
  armed: boolean;
}

interface Start {
  id: number;
  x: number;
  y: number;
  axis: "x" | "y" | null;
}

const directionOf = (axis: "x" | "y", dx: number, dy: number): SwipeDirection =>
  axis === "x" ? (dx < 0 ? "left" : "right") : dy < 0 ? "up" : "down";

/**
 * Gestes de glissement par Pointer Events. Le geste ne démarre qu'une fois l'axe tranché (SLOP, AXIS_RATIO) : tant
 * que le doigt reste ambigu, rien ne bouge. Si le navigateur reprend le geste pour défiler (pointercancel), tout
 * est abandonné. Côté CSS, `touch-action` doit laisser passer les événements sur les zones concernées.
 */
export function useSwipe(onSwipe: (direction: SwipeDirection) => void, disabled = false) {
  const start = useRef<Start | null>(null);
  const swallowClick = useRef(false);
  const [drag, setDrag] = useState<Drag | null>(null);

  function reset() {
    start.current = null;
    setDrag(null);
  }

  const handlers = {
    onPointerDown(e: ReactPointerEvent<HTMLElement>) {
      if (disabled || (e.pointerType === "mouse" && e.button !== 0)) return;
      if (start.current) {
        reset(); // deuxième doigt : on abandonne
        return;
      }
      swallowClick.current = false;
      start.current = { id: e.pointerId, x: e.clientX, y: e.clientY, axis: null };
    },
    onPointerMove(e: ReactPointerEvent<HTMLElement>) {
      const s = start.current;
      if (!s || s.id !== e.pointerId) return;
      const dx = e.clientX - s.x;
      const dy = e.clientY - s.y;
      if (!s.axis) {
        const ax = Math.abs(dx);
        const ay = Math.abs(dy);
        if (Math.max(ax, ay) < SLOP) return;
        if (ax >= AXIS_RATIO * ay) s.axis = "x";
        else if (ay >= AXIS_RATIO * ax) s.axis = "y";
        else return; // diagonale : on attend de voir
        try {
          e.currentTarget.setPointerCapture?.(e.pointerId);
        } catch {
          /* pointeur déjà relâché */
        }
      }
      const main = s.axis === "x" ? dx : dy;
      setDrag({ dx, dy, axis: s.axis, direction: directionOf(s.axis, dx, dy), armed: Math.abs(main) >= THRESHOLD });
    },
    onPointerUp(e: ReactPointerEvent<HTMLElement>) {
      const s = start.current;
      if (!s || s.id !== e.pointerId) return;
      const dx = e.clientX - s.x;
      const dy = e.clientY - s.y;
      const axis = s.axis;
      reset();
      if (!axis) return; // simple clic ou toucher
      swallowClick.current = true;
      const main = Math.abs(axis === "x" ? dx : dy);
      const cross = Math.abs(axis === "x" ? dy : dx);
      if (main >= THRESHOLD && cross < main) onSwipe(directionOf(axis, dx, dy));
    },
    onPointerCancel(e: ReactPointerEvent<HTMLElement>) {
      if (start.current?.id === e.pointerId) reset();
    },
    /** Après un glissement, le « clic » qui suit ne doit pas ouvrir un lien sous le doigt. */
    onClickCapture(e: React.MouseEvent<HTMLElement>) {
      if (swallowClick.current) {
        swallowClick.current = false;
        e.preventDefault();
        e.stopPropagation();
      }
    },
  };

  return { handlers, drag: disabled ? null : drag };
}
