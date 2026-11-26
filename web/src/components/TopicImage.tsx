import { useState } from "react";
import topic from "./Topic.module.css";

/**
 * Image d'illustration d'un sujet.
 * HOTLINK (décision produit) : le navigateur du lecteur charge l'image directement
 * depuis le média ; ni proxy, ni copie, ni CSP. Referrer coupé, chargement différé.
 * Autonome : l'état d'erreur est local à l'instance (le parent la clé par sujet) ;
 * en erreur ou sans URL, rien n'est rendu, donc aucun espace réservé.
 */
export function TopicImage({ url, title }: { url: string | null; title: string }) {
  const [failed, setFailed] = useState<string | null>(null);
  if (!url || failed === url) return null;
  return (
    <div className={topic.image}>
      <img
        src={url}
        alt={`Illustration : ${title}`}
        width={16}
        height={9}
        loading="lazy"
        decoding="async"
        referrerPolicy="no-referrer"
        onError={() => setFailed(url)}
      />
    </div>
  );
}
