import { Link } from "react-router-dom";
import { useLogout, useMe } from "../api/hooks";
import styles from "./Layout.module.css";

export function AccountMenu() {
  const me = useMe();
  const logout = useLogout();

  if (me.isPending) return <div className={styles.account} aria-busy="true" />;

  if (me.data) {
    return (
      <div className={styles.account}>
        <span className={styles.email} title={me.data.email}>
          {me.data.email}
        </span>
        <button type="button" onClick={() => logout.mutate()} disabled={logout.isPending}>
          Se déconnecter
        </button>
      </div>
    );
  }

  return (
    <div className={styles.account}>
      <Link to="/connexion">Se connecter</Link>
    </div>
  );
}
