import { useEffect, useState } from "react";

/**
 * Millisecondes restantes avant `target` (ISO), l'horloge du lecteur étant corrigée de son décalage avec le serveur.
 * `serverTime` : heure du serveur au moment où `receivedAt` (Date.now() côté lecteur) a été relevé.
 * Mise à jour chaque seconde, alignée sur la seconde entière restante.
 */
export function useCountdown(target: string | undefined, serverTime: string | undefined, receivedAt: number): number | null {
  const offset = serverTime ? Date.parse(serverTime) - receivedAt : 0;
  const end = target ? Date.parse(target) : NaN;
  const compute = () => end - (Date.now() + (Number.isFinite(offset) ? offset : 0));
  const [remaining, setRemaining] = useState(compute);

  useEffect(() => {
    if (Number.isNaN(end)) return;
    const tick = () => setRemaining(end - (Date.now() + (Number.isFinite(offset) ? offset : 0)));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [end, offset]);

  return Number.isNaN(end) ? null : remaining;
}
