import { useEffect, useRef } from "react";

/** Titre du document + ref pour le h1 (focus à l'arrivée sur la page, comme Placeholder). */
export function usePageTitle(title: string) {
  const ref = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    document.title = `${title} — Citizen News`;
    ref.current?.focus({ preventScroll: true });
  }, [title]);
  return ref;
}
