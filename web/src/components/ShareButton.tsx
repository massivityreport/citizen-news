import { useEffect, useState } from "react";
import styles from "./Edition.module.css";

type Feedback = "copied" | "shared" | "failed" | null;

/** Web Share API si disponible, sinon copie du lien dans le presse-papiers ; retour visuel et vocal (role="status"). */
export function ShareButton({ url, title }: { url: string; title: string }) {
  const [feedback, setFeedback] = useState<Feedback>(null);

  useEffect(() => {
    if (!feedback) return;
    const t = setTimeout(() => setFeedback(null), 4000);
    return () => clearTimeout(t);
  }, [feedback]);

  async function share() {
    if (typeof navigator.share === "function") {
      try {
        await navigator.share({ title, url });
        setFeedback("shared");
        return;
      } catch (e) {
        if (e instanceof DOMException && e.name === "AbortError") return; // annulé par le lecteur
        // autre erreur : on retombe sur la copie
      }
    }
    try {
      await navigator.clipboard.writeText(url);
      setFeedback("copied");
    } catch {
      setFeedback("failed");
    }
  }

  return (
    <span className={styles.share}>
      <button type="button" className={styles.btnSecondary} onClick={() => void share()}>
        Partager cette une
      </button>
      <span role="status" className={styles.shareFeedback}>
        {feedback === "copied" && "Lien copié ✓"}
        {feedback === "shared" && "Merci d’avoir partagé ✓"}
        {feedback === "failed" && `Copie impossible : copiez ce lien à la main — ${url}`}
      </span>
    </span>
  );
}
