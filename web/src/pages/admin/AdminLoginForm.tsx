import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError } from "../../api/client";
import { useAdminLogin } from "../../api/hooks";
import { usePageTitle } from "../../components/usePageTitle";
import styles from "./Admin.module.css";

/** « 90 » -> « 2 minutes » ; « 40 » -> « 40 secondes » (arrondi au-dessus). */
export function readableWait(seconds: number): string {
  if (seconds < 60) return `${seconds} ${seconds > 1 ? "secondes" : "seconde"}`;
  const m = Math.ceil(seconds / 60);
  return `${m} ${m > 1 ? "minutes" : "minute"}`;
}

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError && e.status === 401) return "Mot de passe incorrect.";
  if (e instanceof ApiError && e.isRateLimited) {
    return e.retryAfter
      ? `Trop de tentatives. Réessayez dans ${readableWait(e.retryAfter)}.`
      : "Trop de tentatives. Réessayez plus tard.";
  }
  return "La connexion n’a pas pu aboutir pour le moment. Réessayez dans un instant.";
}

export function AdminLoginForm() {
  const h1 = usePageTitle("Administration");
  const login = useAdminLogin();
  const [password, setPassword] = useState("");
  const errRef = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    if (login.isError) errRef.current?.focus();
  }, [login.isError]);

  function submit(ev: FormEvent) {
    ev.preventDefault();
    if (login.isPending || !password) return;
    login.mutate(password, { onError: () => setPassword("") });
  }

  return (
    <main className={styles.loginPage}>
      <h1 ref={h1} tabIndex={-1}>
        Administration
      </h1>
      <form onSubmit={submit} className={styles.form}>
        <label htmlFor="admin-password">Mot de passe</label>
        <input
          id="admin-password"
          type="password"
          name="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          aria-invalid={login.isError ? true : undefined}
          aria-describedby={login.isError ? "admin-error" : undefined}
          required
        />
        {login.isError && (
          <p id="admin-error" role="alert" ref={errRef} tabIndex={-1} className={styles.error}>
            {errorMessage(login.error)}
          </p>
        )}
        <button type="submit" className={styles.btn} disabled={login.isPending}>
          {login.isPending ? "Connexion…" : "Se connecter"}
        </button>
      </form>
    </main>
  );
}
