import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import { useAdminFeedbackItem, useDeleteFeedback, useSetFeedbackRead } from "../../api/hooks";
import type { RecentAction } from "../../api/types";
import { usePageTitle } from "../../components/usePageTitle";
import { formatClock, formatFull } from "../../lib/format";
import { KIND_LABELS } from "../../lib/feedbackLabels";
import styles from "./Admin.module.css";

function describe(a: RecentAction): string {
  switch (a.type) {
    case "page":
      return `Page ${a.page ?? ""}`.trim();
    case "topic_added":
      return `Sujet ${a.topic_id ?? "?"} ajouté à la une`;
    case "topic_removed":
      return `Sujet ${a.topic_id ?? "?"} retiré de la une`;
    case "login":
      return "Connexion";
  }
}

function DeleteDialog({ id, onClose }: { id: number; onClose: () => void }) {
  const navigate = useNavigate();
  const del = useDeleteFeedback();
  const cancel = useRef<HTMLButtonElement>(null);
  const opener = useRef<Element | null>(document.activeElement);
  useEffect(() => {
    cancel.current?.focus();
    const previous = opener.current as HTMLElement | null;
    return () => previous?.focus?.();
  }, []);
  return (
    <div className={styles.overlay} onKeyDown={(e) => e.key === "Escape" && onClose()}>
      <div role="dialog" aria-modal="true" aria-labelledby="delete-feedback-title" className={styles.dialog}>
        <h2 id="delete-feedback-title">Supprimer cet avis ?</h2>
        <p>
          L’avis, son parcours et ses éventuelles réponses seront <strong>supprimés définitivement</strong>. Cette action est irréversible.
        </p>
        {del.isError && (
          <p role="alert" className={styles.error}>
            La suppression a échoué. Réessayez dans un instant.
          </p>
        )}
        <div className={styles.dialogButtons}>
          <button type="button" ref={cancel} className={styles.small} onClick={onClose}>
            Annuler
          </button>
          <button
            type="button"
            className={`${styles.btn} ${styles.btnDanger}`}
            disabled={del.isPending}
            onClick={() => del.mutate(id, { onSuccess: () => navigate("/admin/avis", { replace: true }) })}
          >
            {del.isPending ? "Suppression…" : "Supprimer définitivement"}
          </button>
        </div>
      </div>
    </div>
  );
}

/** Détail d’un avis. L’ouvrir le passe en « lu » (une seule fois) ; le bouton le remet en « non lu ». */
export default function AdminFeedbackDetailPage() {
  const params = useParams();
  const id = Number(params.id);
  const valid = Number.isInteger(id) && id >= 1;
  const item = useAdminFeedbackItem(valid ? id : 0);
  const setRead = useSetFeedbackRead();
  const h1 = usePageTitle(valid ? `Avis n° ${id}` : "Avis introuvable");
  const [confirming, setConfirming] = useState(false);
  const markedRead = useRef<number | null>(null);
  const loaded = item.data;

  // Ouvrir l’avis le passe en lu : une fois par avis ouvert, jamais après un « non lu » explicite.
  useEffect(() => {
    if (loaded && !loaded.is_read && markedRead.current !== loaded.id) {
      markedRead.current = loaded.id;
      setRead.mutate({ id: loaded.id, read: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loaded?.id]);

  const back = <Link to="/admin/avis">← Tous les avis</Link>;
  const heading = (
    <h1 ref={h1} tabIndex={-1}>
      {valid ? `Avis n° ${id}` : "Avis introuvable"}
    </h1>
  );
  const notFound = !valid || (item.isError && item.error instanceof ApiError && item.error.status === 404);

  if (notFound)
    return (
      <section className={styles.section}>
        {back}
        {heading}
        <p role="status">Cet avis n’existe pas (ou plus).</p>
      </section>
    );
  if (item.isPending)
    return (
      <section className={styles.section}>
        {back}
        {heading}
        <p role="status">Chargement de l’avis…</p>
      </section>
    );
  if (item.isError)
    return (
      <section className={styles.section}>
        {back}
        {heading}
        <p role="alert" className={styles.error}>
          Impossible de charger l’avis. Réessayez dans un instant.
        </p>
      </section>
    );

  const f = item.data;
  return (
    <section className={styles.section}>
      {back}
      {heading}
      <dl className={styles.stats}>
        <div>
          <dt>Reçu le</dt>
          <dd>
            <time dateTime={f.created_at}>{formatFull(f.created_at)}</time>
          </dd>
        </div>
        <div>
          <dt>Type</dt>
          <dd>{KIND_LABELS[f.kind]}</dd>
        </div>
        <div>
          <dt>E-mail</dt>
          <dd>{f.email}</dd>
        </div>
        <div>
          <dt>Page</dt>
          <dd>
            {f.page_name}
            <small className={styles.url}>{f.page_url}</small>
          </dd>
        </div>
        <div>
          <dt>Taille d’écran</dt>
          <dd>{f.screen}</dd>
        </div>
        <div>
          <dt>Navigateur</dt>
          <dd>{f.browser}</dd>
        </div>
      </dl>
      <h2>Message</h2>
      <p className={styles.message}>{f.message}</p>
      <h2>Parcours récent</h2>
      {f.recent_actions === null ? (
        <p>Parcours non joint par le visiteur.</p>
      ) : f.recent_actions.length === 0 ? (
        <p>Le parcours joint est vide.</p>
      ) : (
        <ul className={styles.journey} aria-label="Parcours récent">
          {f.recent_actions.map((a, i) => (
            <li key={i}>
              <time dateTime={a.at}>{formatClock(a.at)}</time>
              {describe(a)}
            </li>
          ))}
        </ul>
      )}
      {setRead.isError && (
        <p role="alert" className={styles.error}>
          Le changement d’état a échoué. Réessayez dans un instant.
        </p>
      )}
      <div className={styles.actions}>
        {f.is_read && (
          <button type="button" className={styles.small} disabled={setRead.isPending} onClick={() => setRead.mutate({ id: f.id, read: false })}>
            Marquer comme non lu
          </button>
        )}
        <button type="button" className={`${styles.small} ${styles.danger}`} onClick={() => setConfirming(true)}>
          Supprimer
        </button>
      </div>
      {confirming && <DeleteDialog id={f.id} onClose={() => setConfirming(false)} />}
    </section>
  );
}
