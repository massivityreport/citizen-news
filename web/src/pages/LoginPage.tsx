import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import { meKey, uneKey, useLogout, useMe } from "../api/hooks";
import { usePageTitle } from "../components/usePageTitle";
import styles from "./LoginPage.module.css";

const TITLE = "Se connecter";
const REDIRECT_DELAY_MS = 2500;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Chemin interne uniquement (pas d'URL externe ni de « // »). */
function internalPath(value: unknown): string | null {
  return typeof value === "string" && /^\/(?![/\\])/.test(value) ? value : null;
}

const pick = (n: number, one: string, many: string) => (n > 1 ? many : one);

/** Le brouillon de une attaché au lien (contrat V2) est fusionné par le serveur : on le dit simplement. */
function doneMessage(draft: { added: number; ignored: number } | null | undefined): string {
  if (!draft) return "Vous êtes connecté·e.";
  const ignored = draft.ignored > 0 ? ` ${draft.ignored} ${pick(draft.ignored, "autre sujet a été ignoré", "autres sujets ont été ignorés")} (une complète ou sujet plus disponible).` : "";
  if (draft.added === 0) return `Vous êtes connecté·e. Votre brouillon n’a rien ajouté : ses sujets étaient déjà dans votre une.${ignored}`;
  return `Vous êtes connecté·e. ${draft.added} ${pick(draft.added, "sujet a été ajouté", "sujets ont été ajoutés")} à votre une.${ignored}`;
}

type Phase =
  | { kind: "verifying" }
  | { kind: "done"; message: string }
  | { kind: "invalid" }
  | { kind: "error" };

export default function LoginPage() {
  const h1 = usePageTitle(TITLE);
  const location = useLocation();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [params] = useSearchParams();
  // Le jeton est lu une fois, gardé en mémoire seulement, et retiré de l'URL aussitôt.
  const [token] = useState(() => params.get("token"));
  const [phase, setPhase] = useState<Phase | null>(() =>
    token === null ? null : token === "" ? { kind: "invalid" } : { kind: "verifying" },
  );
  const [from] = useState(() => internalPath((location.state as { from?: unknown } | null)?.from) ?? "/composer");
  const started = useRef(false);
  const msgRef = useRef<HTMLParagraphElement>(null);
  const me = useMe();

  // Déclaré avant l'effet de vérification. Pas de layout effect : navigate() y est ignoré dans une page enfant.
  useEffect(() => {
    if (token !== null) navigate({ pathname: location.pathname, search: "", hash: "" }, { replace: true, state: location.state });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- une seule fois, à l'arrivée
  }, []);

  useEffect(() => {
    // Le jeton est à usage unique : une seule vérification, même en StrictMode.
    if (!token || started.current) return;
    started.current = true;
    void (async () => {
      let user;
      try {
        user = await api.verify(token);
      } catch (e) {
        setPhase({ kind: e instanceof ApiError && e.status === 400 ? "invalid" : "error" });
        return;
      }
      await qc.cancelQueries({ queryKey: meKey });
      qc.setQueryData(meKey, { email: user.email });
      void qc.invalidateQueries({ queryKey: uneKey });
      // Le brouillon local n'est pas touché ici : la page /composer fusionne ce qui n'est pas déjà dans la une.
      setPhase({ kind: "done", message: doneMessage(user.draft) });
    })();
  }, [token, qc]);

  const done = phase?.kind === "done";
  useEffect(() => {
    if (!done) return;
    const t = setTimeout(() => navigate(from, { replace: true }), REDIRECT_DELAY_MS);
    return () => clearTimeout(t);
  }, [done, navigate, from]);

  useEffect(() => {
    if (phase && phase.kind !== "verifying") msgRef.current?.focus();
  }, [phase]);

  let body;
  if (phase?.kind === "verifying") {
    body = (
      <p role="status" aria-busy="true" className={styles.notice}>
        Vérification de votre lien de connexion…
      </p>
    );
  } else if (phase?.kind === "done") {
    body = (
      <>
        <p role="status" ref={msgRef} tabIndex={-1} className={styles.notice}>
          {phase.message}
        </p>
        <p>
          <Link to={from} replace className={styles.btn}>
            Continuer
          </Link>
        </p>
      </>
    );
  } else if (me.isPending) {
    body = <p role="status">Chargement…</p>;
  } else {
    // Lien invalide/expiré : le message s'affiche aussi si l'on est déjà connecté.
    body = (
      <>
        {phase?.kind === "invalid" && (
          <p role="alert" ref={msgRef} tabIndex={-1} className={styles.error}>
            Ce lien n’est plus valable : demandez-en un nouveau.
          </p>
        )}
        {phase?.kind === "error" && (
          <p role="alert" ref={msgRef} tabIndex={-1} className={styles.error}>
            La vérification n’a pas pu aboutir pour le moment. Demandez un nouveau lien ou réessayez plus tard.
          </p>
        )}
        {me.data ? <Account email={me.data.email} /> : <MagicLinkForm />}
      </>
    );
  }

  return (
    <section className={styles.page}>
      <h1 ref={h1} tabIndex={-1}>
        {TITLE}
      </h1>
      {body}
    </section>
  );
}

function Account({ email }: { email: string }) {
  const logout = useLogout();
  const msgRef = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    if (logout.isError) msgRef.current?.focus();
  }, [logout.isError]);
  return (
    <div>
      <p>
        Vous êtes connecté·e avec l’adresse <strong>{email}</strong>.
      </p>
      {logout.isError && (
        <p role="alert" ref={msgRef} tabIndex={-1} className={styles.error}>
          La déconnexion a échoué. Réessayez.
        </p>
      )}
      <button type="button" className={styles.btn} onClick={() => logout.mutate()} disabled={logout.isPending}>
        Se déconnecter
      </button>
      <p>
        <Link to="/composer">Composer ma une</Link>
      </p>
    </div>
  );
}

function MagicLinkForm() {
  const [email, setEmail] = useState("");
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);
  const [sending, setSending] = useState(false);
  const [wait, setWait] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const sentRef = useRef<HTMLParagraphElement>(null);
  const errRef = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    if (wait <= 0) return;
    const t = setTimeout(() => setWait((w) => w - 1), 1000);
    return () => clearTimeout(t);
  }, [wait]);

  useEffect(() => {
    if (sent) sentRef.current?.focus();
  }, [sent]);

  useEffect(() => {
    if (formError) errRef.current?.focus();
  }, [formError]);

  async function submit(ev: FormEvent) {
    ev.preventDefault();
    if (sending || wait > 0) return;
    setFormError(null);
    const value = email.trim();
    if (!EMAIL_RE.test(value)) {
      setFieldError("Saisissez une adresse e-mail valide, par exemple prenom.nom@exemple.fr.");
      inputRef.current?.focus();
      return;
    }
    setFieldError(null);
    setSending(true);
    try {
      await api.magicLink(value);
      setEmail("");
      setSent(true);
    } catch (e) {
      if (e instanceof ApiError && e.status === 422) {
        setFieldError("Cette adresse e-mail n’est pas valide. Vérifiez-la et réessayez.");
        inputRef.current?.focus();
      } else if (e instanceof ApiError && e.isRateLimited) {
        const s = e.retryAfter;
        setFormError(
          s
            ? `Vous avez demandé trop de liens. Merci de patienter ${s} ${pick(s, "seconde", "secondes")} avant de réessayer.`
            : "Vous avez demandé trop de liens. Merci de patienter un instant avant de réessayer.",
        );
        setWait(s ?? 30);
      } else {
        setFormError("Le lien n’a pas pu être envoyé pour le moment. Réessayez dans un instant.");
      }
    } finally {
      setSending(false);
    }
  }

  if (sent) {
    return (
      <div>
        <p role="status" ref={sentRef} tabIndex={-1} className={styles.notice}>
          Si cette adresse est valide, un lien de connexion vient de partir. Il est valable peu de temps.
        </p>
        <button type="button" className={styles.link} onClick={() => setSent(false)}>
          Utiliser une autre adresse
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={(e) => void submit(e)} noValidate className={styles.form}>
      <p>Pas de mot de passe : saisissez votre adresse e-mail, nous vous envoyons un lien de connexion.</p>
      <label htmlFor="email">Adresse e-mail</label>
      <input
        id="email"
        ref={inputRef}
        type="email"
        name="email"
        autoComplete="email"
        inputMode="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        aria-invalid={fieldError ? true : undefined}
        aria-describedby={fieldError ? "email-error" : undefined}
        required
      />
      {fieldError && (
        <p id="email-error" role="alert" className={styles.error}>
          {fieldError}
        </p>
      )}
      {formError && (
        <p role="alert" ref={errRef} tabIndex={-1} className={styles.error}>
          {formError}
        </p>
      )}
      <button type="submit" className={styles.btn} disabled={sending || wait > 0}>
        {wait > 0 ? `Réessayer dans ${wait} s` : sending ? "Envoi…" : "Recevoir un lien de connexion"}
      </button>
    </form>
  );
}
