import { createContext, useCallback, useContext, useEffect, useId, useRef, useState, type FormEvent, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { useMe } from "../api/hooks";
import type { FeedbackKind } from "../api/types";
import { journal } from "../lib/journal";
import styles from "./Feedback.module.css";

const MAX_LENGTH = 2000;
const HIDDEN_KEY = "cn.feedbackTabHidden";
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const KINDS: { value: FeedbackKind; label: string }[] = [
  { value: "problem", label: "Problème" },
  { value: "idea", label: "Idée" },
  { value: "other", label: "Autre" },
];

const FeedbackContext = createContext<() => void>(() => {});

function readHidden(): boolean {
  try {
    return window.sessionStorage.getItem(HIDDEN_KEY) === "1";
  } catch {
    return false;
  }
}

/** Fournit l'ouverture du formulaire (lien d'en-tête, onglet) et affiche le formulaire par-dessus la page. */
export function FeedbackProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const openForm = useCallback(() => setOpen(true), []);
  return (
    <FeedbackContext.Provider value={openForm}>
      {children}
      {open && <FeedbackDialog onClose={() => setOpen(false)} />}
    </FeedbackContext.Provider>
  );
}

/** Lien « Votre avis » de l'en-tête : toujours disponible. */
export function FeedbackLink() {
  const open = useContext(FeedbackContext);
  return (
    <button type="button" className={styles.link} onClick={open}>
      Votre avis
    </button>
  );
}

/** Onglet fixé au bord droit, à mi-hauteur ; la croix le masque pour la durée de la visite. */
export function FeedbackTab() {
  const open = useContext(FeedbackContext);
  const [hidden, setHidden] = useState(readHidden);
  if (hidden) return null;
  const hide = () => {
    try {
      window.sessionStorage.setItem(HIDDEN_KEY, "1");
    } catch {
      /* stockage indisponible : masqué jusqu'au prochain rendu seulement */
    }
    setHidden(true);
  };
  return (
    <div className={styles.tab} data-testid="feedback-tab">
      <button type="button" className={styles.tabOpen} onClick={open}>
        Votre avis
      </button>
      <button type="button" className={styles.tabClose} onClick={hide} aria-label="Masquer l'onglet Votre avis">
        ×
      </button>
    </div>
  );
}

// Le chemin seul : les paramètres (recherche tapée, etc.) ne partent jamais avec l'avis, comme dans le parcours récent.
function pageContext(pathname: string) {
  const name = document.title.replace(/\s*—\s*Citizen News$/, "").trim();
  const w = Math.min(Math.round(window.innerWidth), 9999);
  const h = Math.min(Math.round(window.innerHeight), 9999);
  return { page_name: (name || "Citizen News").slice(0, 200), page_url: pathname.slice(0, 500), screen: `${w}x${h}` };
}

function FeedbackDialog({ onClose }: { onClose: () => void }) {
  const me = useMe();
  const { pathname } = useLocation();
  const [page] = useState(() => pageContext(pathname));
  const [kind, setKind] = useState<FeedbackKind>("other");
  const [message, setMessage] = useState("");
  const [email, setEmail] = useState("");
  const [errors, setErrors] = useState<{ message?: string; email?: string; form?: string }>({});
  const [attach, setAttach] = useState(true);
  const [sending, setSending] = useState(false);
  const [done, setDone] = useState(false);
  const titleId = useId();
  const ref = useRef<HTMLDivElement>(null);
  const account = me.data?.email ?? null;

  useEffect(() => {
    const previous = document.activeElement;
    ref.current?.querySelector<HTMLElement>("textarea")?.focus();
    return () => {
      if (previous instanceof HTMLElement) previous.focus();
    };
  }, []);

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape") return onClose();
    if (e.key !== "Tab") return;
    const items = ref.current?.querySelectorAll<HTMLElement>("button:not([disabled]), input, textarea");
    if (!items?.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    const next: typeof errors = {};
    const text = message.trim();
    if (!text) next.message = "Écrivez votre message.";
    if (!account && !EMAIL_RE.test(email.trim())) next.email = "Saisissez une adresse e-mail valide.";
    setErrors(next);
    if (next.message || next.email) return;
    setSending(true);
    try {
      await api.feedback({ kind, message: text, ...(account ? {} : { email: email.trim() }), ...page, ...(attach ? { recent_actions: journal.get() } : {}) });
      setDone(true);
    } catch (err) {
      const limited = err instanceof ApiError && err.isRateLimited;
      setErrors({ form: limited ? "Vous avez envoyé trop d'avis, réessayez plus tard." : "L'envoi a échoué, réessayez plus tard." });
    } finally {
      setSending(false);
    }
  }

  return (
    <div className={styles.backdrop} onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={ref} role="dialog" aria-modal="true" aria-labelledby={titleId} className={styles.dialog} onKeyDown={onKeyDown}>
        <h2 id={titleId}>Votre avis</h2>
        {done ? (
          <>
            <p role="status">Merci pour votre avis, nous l'avons bien reçu.</p>
            <button type="button" className={styles.btn} onClick={onClose}>
              Fermer
            </button>
          </>
        ) : (
          <form onSubmit={submit} noValidate className={styles.form}>
            <fieldset>
              <legend>Type d'avis</legend>
              {KINDS.map((k) => (
                <label key={k.value} className={styles.radio}>
                  <input type="radio" name="kind" value={k.value} checked={kind === k.value} onChange={() => setKind(k.value)} />
                  {k.label}
                </label>
              ))}
            </fieldset>
            <label htmlFor={`${titleId}-msg`}>Votre message</label>
            <textarea
              id={`${titleId}-msg`}
              value={message}
              maxLength={MAX_LENGTH}
              rows={6}
              onChange={(e) => setMessage(e.target.value)}
              aria-invalid={errors.message ? true : undefined}
              aria-describedby={`${titleId}-count`}
            />
            <small id={`${titleId}-count`}>
              {message.length} / {MAX_LENGTH}
            </small>
            {errors.message && (
              <p role="alert" className={styles.error}>
                {errors.message}
              </p>
            )}
            {account ? (
              <p>
                Votre adresse jointe à l'avis : <strong>{account}</strong>
              </p>
            ) : (
              <>
                <label htmlFor={`${titleId}-email`}>Adresse e-mail</label>
                <input
                  id={`${titleId}-email`}
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  aria-invalid={errors.email ? true : undefined}
                />
                {errors.email && (
                  <p role="alert" className={styles.error}>
                    {errors.email}
                  </p>
                )}
              </>
            )}
            <label className={styles.check}>
              <input type="checkbox" checked={attach} onChange={(e) => setAttach(e.target.checked)} />
              Joindre mon parcours récent
            </label>
            <small>
              {attach
                ? "Votre parcours récent est joint à votre avis : les 20 dernières actions de cette visite (pages ouvertes, sujets ajoutés ou retirés de votre une, connexion), avec leur heure."
                : "Votre parcours récent n'est pas joint : rien n'en sera envoyé."}
            </small>
            {errors.form && (
              <p role="alert" className={styles.error}>
                {errors.form}
              </p>
            )}
            <div className={styles.actions}>
              <button type="submit" className={styles.btn} disabled={sending || me.isPending}>
                Envoyer
              </button>
              <button type="button" className={styles.secondary} onClick={onClose}>
                Annuler
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
