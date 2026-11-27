import { useEffect } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { onAdminUnauthorized } from "../../api/client";
import { endAdminSession, useAdminFeedbackUnread, useAdminLogout, useAdminSession } from "../../api/hooks";
import { useNoindex } from "../../components/useNoindex";
import { AdminLoginForm } from "./AdminLoginForm";
import styles from "./Admin.module.css";

const TABS = [
  { to: "/admin", label: "Accueil", end: true },
  { to: "/admin/sources", label: "Sources", end: false },
  { to: "/admin/articles", label: "Articles", end: false },
  { to: "/admin/sujets", label: "Sujets", end: false },
  { to: "/admin/editions", label: "Éditions", end: false },
  { to: "/admin/apercu", label: "Aperçu de la une", end: false },
  { to: "/admin/avis", label: "Avis", end: false },
];

/** Nombre d’avis non lus à côté du nom de l’onglet ; rien à zéro (ou tant qu’il n’est pas connu). */
function UnreadCount() {
  const unread = useAdminFeedbackUnread().data?.unread_count ?? 0;
  if (unread <= 0) return null;
  return (
    <>
      {" "}
      <span className={styles.count} aria-hidden="true">
        {unread}
      </span>
      <span className={styles.srOnly}> ({unread} non {unread > 1 ? "lus" : "lu"})</span>
    </>
  );
}

/** Coquille de /admin : connexion tant que la session n’est pas valide, puis en-tête, onglets et contenu. */
export default function AdminLayout() {
  useNoindex();
  const qc = useQueryClient();
  const session = useAdminSession();
  const logout = useAdminLogout();

  // Une route admin qui répond 401 (session expirée) ramène à la connexion.
  useEffect(() => onAdminUnauthorized(() => endAdminSession(qc)), [qc]);

  if (session.isPending) return <p role="status">Chargement…</p>;
  if (session.isError) {
    return (
      <main className={styles.loginPage}>
        <p role="alert" className={styles.error}>
          Impossible de vérifier la session pour le moment. Rechargez la page dans un instant.
        </p>
      </main>
    );
  }
  if (!session.data) return <AdminLoginForm />;

  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        <div className={`${styles.bar} container`}>
          <span className={styles.brand}>Citizen News — Administration</span>
          <button type="button" className={styles.logout} onClick={() => logout.mutate()} disabled={logout.isPending}>
            Déconnexion
          </button>
        </div>
        <nav aria-label="Navigation de l’administration" className={`${styles.nav} container`}>
          <ul>
            {TABS.map((t) => (
              <li key={t.to}>
                <NavLink to={t.to} end={t.end}>
                  {t.label}
                  {t.to === "/admin/avis" && <UnreadCount />}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </header>
      <main id="contenu" className={`${styles.main} container`}>
        <Outlet />
      </main>
    </div>
  );
}
