import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { AccountMenu } from "./AccountMenu";
import styles from "./Layout.module.css";

const NAV = [
  { to: "/", label: "Accueil", end: true },
  { to: "/composer", label: "Composer", end: false },
  { to: "/archives", label: "Archives", end: false },
  { to: "/comment-ca-marche", label: "Comment ça marche", end: false },
];

export function Layout() {
  const { pathname } = useLocation();
  const showFixedCta = pathname !== "/composer";

  return (
    <div className={styles.shell}>
      <a className={styles.skip} href="#contenu">
        Aller au contenu
      </a>
      <header className={styles.header}>
        <div className={`${styles.bar} container`}>
          <Link to="/" className={styles.brand}>
            Citizen News
          </Link>
          <AccountMenu />
        </div>
        <nav aria-label="Navigation principale" className={`${styles.nav} container`}>
          <ul>
            {NAV.map((item) => (
              <li key={item.to}>
                <NavLink to={item.to} end={item.end}>
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </header>
      <main id="contenu" tabIndex={-1} className={`${styles.main} container`}>
        <Outlet />
      </main>
      <footer className={`${styles.footer} container`}>
        <p>Citizen News — la une choisie par les citoyens.</p>
      </footer>
      {showFixedCta && (
        <Link to="/composer" className={styles.fixedCta} data-testid="fixed-cta">
          Composer ma une
        </Link>
      )}
    </div>
  );
}
