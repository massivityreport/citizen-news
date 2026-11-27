import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { TopicCard } from "../api/types";
import { MAX_PLACES } from "../lib/draft";
import { formatHour } from "../lib/format";
import styles from "./composer.module.css";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** « Revoir et valider » : la une en détail, retrait, remplacement, et enregistrement (compte). */
export function ReviewPanel({
  ids,
  topics,
  signedIn,
  closed,
  closesAt,
  onRemove,
  onReplace,
  onBack,
}: {
  ids: number[];
  topics: Map<number, TopicCard>;
  signedIn: boolean;
  closed: boolean;
  closesAt: string | null;
  onRemove: (id: number) => void;
  onReplace: (id: number, place: number) => void;
  onBack: () => void;
}) {
  return (
    <section aria-labelledby="revoir-titre" className={styles.page}>
      <h2 id="revoir-titre">Revoir et valider</h2>
      <button type="button" className={`${styles.btn} ${styles.btnLight} ${styles.review}`} onClick={onBack}>
        ‹ Retour aux sujets
      </button>
      <p>
        {ids.length}/{MAX_PLACES} sujets dans votre une, sans ordre : ils ont tous le même poids.
        {ids.length < MAX_PLACES && " Vous pouvez la compléter."}
      </p>
      <ol className={styles.reviewList}>
        {Array.from({ length: MAX_PLACES }, (_, i) => {
          const id = ids[i];
          if (id === undefined)
            return (
              <li key={i} className={styles.item} data-free="true">
                Place {i + 1} : Place libre
              </li>
            );
          const t = topics.get(id);
          return (
            <li key={id} className={styles.item}>
              <h3>
                <span>Place {i + 1} : </span>
                {t ? t.title : "Sujet qui n’est plus disponible"}
              </h3>
              {t?.summary && <p>{t.summary}</p>}
              {!closed && (
                <div className={styles.itemActions}>
                  <button type="button" className={`${styles.btn} ${styles.btnLight}`} onClick={() => onRemove(id)}>
                    Retirer<span className={styles.srOnly}> {t?.title ?? `la place ${i + 1}`}</span>
                  </button>
                  <button type="button" className={`${styles.btn} ${styles.btnLight}`} onClick={() => onReplace(id, i + 1)}>
                    Remplacer<span className={styles.srOnly}> {t?.title ?? `la place ${i + 1}`}</span>
                  </button>
                </div>
              )}
            </li>
          );
        })}
      </ol>
      {closed ? (
        <p role="status" className={styles.notice}>
          La clôture est passée : votre une est en lecture seule. La prochaine une repart vide.
        </p>
      ) : signedIn ? (
        <div className={styles.notice} role="status">
          <p className={styles.noticeText}>
            Votre une est enregistrée, modifiable jusqu’à {closesAt ? formatHour(closesAt) : "la clôture"}.{" "}
            <Link to="/comment-ca-marche">Comment ça marche ?</Link>
          </p>
        </div>
      ) : (
        <SaveByEmail ids={ids} />
      )}
    </section>
  );
}

function SaveByEmail({ ids }: { ids: number[] }) {
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);
  const [sending, setSending] = useState(false);

  async function submit(ev: FormEvent) {
    ev.preventDefault();
    if (sending) return;
    const value = email.trim();
    if (!EMAIL_RE.test(value)) {
      setError("Saisissez une adresse e-mail valide, par exemple prenom.nom@exemple.fr.");
      return;
    }
    setError(null);
    setSending(true);
    try {
      await api.magicLink(value, ids.length > 0 ? { topic_ids: ids } : undefined);
      setSent(true);
    } catch (e) {
      setError(
        e instanceof ApiError && e.isRateLimited
          ? "Trop de demandes : patientez un instant avant de réessayer."
          : "Le lien n’a pas pu être envoyé pour le moment. Réessayez dans un instant.",
      );
    } finally {
      setSending(false);
    }
  }

  if (sent)
    return (
      <p role="status" className={styles.notice}>
        Un lien vous a été envoyé : ouvrez-le (même dans un autre navigateur, votre brouillon est joint).
      </p>
    );

  return (
    <form onSubmit={(e) => void submit(e)} noValidate className={styles.form} aria-labelledby="enregistrer-titre">
      <h3 id="enregistrer-titre">Enregistrer ma une</h3>
      <p>Pour que votre une compte, enregistrez-la avec votre e-mail.</p>
      <label htmlFor="composer-email">Adresse e-mail</label>
      <input
        id="composer-email"
        type="email"
        autoComplete="email"
        inputMode="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? "composer-email-erreur" : undefined}
      />
      {error && (
        <p id="composer-email-erreur" role="alert" className={styles.error}>
          {error}
        </p>
      )}
      <button type="submit" className={styles.btn} disabled={sending}>
        {sending ? "Envoi…" : "Recevoir un lien"}
      </button>
    </form>
  );
}
