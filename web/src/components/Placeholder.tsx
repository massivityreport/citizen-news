import { useEffect, useRef } from "react";

/** Page provisoire : titre + emplacement. Le contenu viendra de la tâche suivante. */
export function Placeholder({ title, children }: { title: string; children?: React.ReactNode }) {
  const ref = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    document.title = `${title} — Citizen News`;
    ref.current?.focus({ preventScroll: true });
  }, [title]);

  return (
    <section>
      <h1 ref={ref} tabIndex={-1}>
        {title}
      </h1>
      {children ?? <p className="placeholder">Contenu à venir.</p>}
    </section>
  );
}
