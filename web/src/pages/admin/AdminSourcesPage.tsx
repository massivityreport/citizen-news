import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError } from "../../api/client";
import { useAddSource, useAdminSources, useDeleteSource, useSetSourceActive } from "../../api/hooks";
import type { AdminSource } from "../../api/types";
import { usePageTitle } from "../../components/usePageTitle";
import { formatDate, formatFull } from "../../lib/format";
import styles from "./Admin.module.css";

/** Message du serveur (déjà en français) ; sinon un texte de repli. */
function serverMessage(e: unknown, fallback: string): string {
  if (e instanceof ApiError && e.status !== 401 && e.message && e.message !== "Une erreur est survenue.") return e.message;
  return fallback;
}

const plural = (n: number) => `${n} article${n > 1 ? "s" : ""}`;

function AddSourceForm() {
  const add = useAddSource();
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [added, setAdded] = useState<string | null>(null);

  function submit(ev: FormEvent) {
    ev.preventDefault();
    if (add.isPending) return;
    setAdded(null);
    add.mutate(
      { name, feed_url: url },
      {
        onSuccess: (source) => {
          setName("");
          setUrl("");
          setAdded(`La source « ${source.name} » a été ajoutée.`);
        },
      },
    );
  }

  return (
    <form onSubmit={submit} className={`${styles.form} ${styles.addForm}`} aria-labelledby="add-source-title">
      <h2 id="add-source-title">Ajouter une source</h2>
      <label htmlFor="source-name">Nom de la source</label>
      <input
        id="source-name"
        value={name}
        maxLength={100}
        onChange={(e) => setName(e.target.value)}
        aria-describedby={add.isError ? "add-source-error" : undefined}
        required
      />
      <label htmlFor="source-url">Adresse du flux (RSS ou Atom)</label>
      <input
        id="source-url"
        type="url"
        inputMode="url"
        placeholder="https://exemple.fr/rss.xml"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        aria-invalid={add.isError ? true : undefined}
        aria-describedby={add.isError ? "add-source-error" : undefined}
        required
      />
      {add.isError && (
        <p id="add-source-error" role="alert" className={styles.error}>
          {serverMessage(add.error, "La source n’a pas pu être ajoutée pour le moment. Réessayez dans un instant.")}
        </p>
      )}
      {added && !add.isError && (
        <p role="status" className={styles.status}>
          {added}
        </p>
      )}
      <button type="submit" className={styles.btn} disabled={add.isPending}>
        {add.isPending ? "Vérification du flux…" : "Ajouter la source"}
      </button>
    </form>
  );
}

function DeleteDialog({ source, onClose }: { source: AdminSource; onClose: () => void }) {
  const del = useDeleteSource();
  // La saisie est liée au nombre d’articles affiché : s’il change (le serveur a refusé, la liste est rechargée), elle est à refaire.
  const [entry, setEntry] = useState({ count: source.article_count, text: "" });
  const typed = entry.count === source.article_count ? entry.text : "";
  const input = useRef<HTMLInputElement>(null);
  const opener = useRef<Element | null>(document.activeElement);
  const matches = typed.trim() === source.name;

  useEffect(() => {
    input.current?.focus();
    const previous = opener.current as HTMLElement | null;
    return () => previous?.focus?.();
  }, []);

  function confirm(ev: FormEvent) {
    ev.preventDefault();
    if (!matches || del.isPending) return;
    del.mutate({ id: source.id, confirm: source.article_count }, { onSuccess: onClose });
  }

  return (
    <div className={styles.overlay} onKeyDown={(e) => e.key === "Escape" && onClose()}>
      <form role="dialog" aria-modal="true" aria-labelledby="delete-title" className={styles.dialog} onSubmit={confirm}>
        <h2 id="delete-title">Supprimer définitivement « {source.name} » ?</h2>
        <p>
          <strong>{plural(source.article_count)} seront supprimés définitivement</strong>, ainsi que la source. Cette
          action est irréversible. Les sujets qui perdent des articles restent, mais peuvent disparaître de la une.
        </p>
        <label htmlFor="delete-confirm">Pour confirmer, saisissez le nom de la source : {source.name}</label>
        <input
          id="delete-confirm"
          ref={input}
          value={typed}
          onChange={(e) => setEntry({ count: source.article_count, text: e.target.value })}
          autoComplete="off"
          aria-describedby={del.isError ? "delete-error" : undefined}
        />
        {del.isError && (
          <p id="delete-error" role="alert" className={styles.error}>
            {serverMessage(del.error, "La suppression a échoué. Réessayez dans un instant.")}
          </p>
        )}
        <div className={styles.dialogButtons}>
          <button type="button" className={styles.small} onClick={onClose}>
            Annuler
          </button>
          <button type="submit" className={`${styles.btn} ${styles.btnDanger}`} disabled={!matches || del.isPending}>
            {del.isPending ? "Suppression…" : "Supprimer définitivement"}
          </button>
        </div>
      </form>
    </div>
  );
}

export default function AdminSourcesPage() {
  const h1 = usePageTitle("Sources");
  const sources = useAdminSources();
  const toggle = useSetSourceActive();
  const [deletingId, setDeletingId] = useState<number | null>(null);
  // La source est relue dans la liste à chaque rendu : le nombre d’articles affiché est toujours le dernier connu.
  const deleting = sources.data?.find((s) => s.id === deletingId) ?? null;

  return (
    <section className={styles.section}>
      <h1 ref={h1} tabIndex={-1}>
        Sources
      </h1>
      <p>
        Les médias dont les flux sont lus. Une source désactivée n’est plus lue, mais ses articles et leurs sujets sont
        conservés.
      </p>

      {sources.isPending && <p role="status">Chargement…</p>}
      {sources.isError && (
        <p role="alert" className={styles.error}>
          Impossible de charger les sources pour le moment.
        </p>
      )}
      {toggle.isError && (
        <p role="alert" className={styles.error}>
          {serverMessage(toggle.error, "Le changement d’état a échoué. Réessayez dans un instant.")}
        </p>
      )}
      {sources.data && sources.data.length === 0 && <p>Aucune source pour le moment.</p>}
      {sources.data && sources.data.length > 0 && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <caption>Sources de la plateforme</caption>
            <thead>
              <tr>
                <th scope="col">Nom</th>
                <th scope="col">Flux</th>
                <th scope="col">État</th>
                <th scope="col">Articles</th>
                <th scope="col">Dernier article</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {sources.data.map((s) => (
                <tr key={s.id}>
                  <th scope="row">{s.name}</th>
                  <td className={styles.url}>{s.feed_url}</td>
                  <td>
                    <span className={`${styles.badge} ${s.active ? styles.on : styles.off}`}>
                      {s.active ? "Actif" : "Inactif"}
                    </span>
                  </td>
                  <td className={styles.num}>{s.article_count}</td>
                  <td>
                    {s.last_article_at ? (
                      <time dateTime={s.last_article_at} title={formatFull(s.last_article_at)}>
                        {formatDate(s.last_article_at)}
                      </time>
                    ) : (
                      "Aucun article"
                    )}
                  </td>
                  <td>
                    <div className={styles.actions}>
                      <button
                        type="button"
                        className={styles.small}
                        disabled={toggle.isPending}
                        aria-label={`${s.active ? "Désactiver" : "Réactiver"} ${s.name}`}
                        onClick={() => toggle.mutate({ id: s.id, active: !s.active })}
                      >
                        {s.active ? "Désactiver" : "Réactiver"}
                      </button>
                      <button
                        type="button"
                        className={`${styles.small} ${styles.danger}`}
                        aria-label={`Supprimer définitivement ${s.name}`}
                        onClick={() => setDeletingId(s.id)}
                      >
                        Supprimer définitivement
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <AddSourceForm />
      {deleting && <DeleteDialog key={deleting.id} source={deleting} onClose={() => setDeletingId(null)} />}
    </section>
  );
}
