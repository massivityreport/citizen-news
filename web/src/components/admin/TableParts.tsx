import { useSearchParams } from "react-router-dom";
import type { ReactNode } from "react";
import styles from "../../pages/admin/Admin.module.css";

export interface SortState {
  sort: string;
  order: "asc" | "desc";
}

/** En-tête de colonne triable : le bouton change le tri, `aria-sort` annonce l’état courant. */
export function SortableTh({
  column,
  current,
  onSort,
  children,
}: {
  column: string;
  current: SortState;
  onSort: (column: string) => void;
  children: ReactNode;
}) {
  const active = current.sort === column;
  const ariaSort = active ? (current.order === "asc" ? "ascending" : "descending") : "none";
  return (
    <th scope="col" aria-sort={ariaSort}>
      <button type="button" className={styles.sortBtn} onClick={() => onSort(column)}>
        {children}
        <span aria-hidden="true">{active ? (current.order === "asc" ? " ▲" : " ▼") : " ↕"}</span>
      </button>
    </th>
  );
}

/** Précédent / suivant, « Page X sur N » et total. `onPage` reçoit le numéro de la page demandée. */
export function Pager({
  page,
  pageSize,
  total,
  unit,
  onPage,
}: {
  page: number;
  pageSize: number;
  total: number;
  unit: string;
  onPage: (page: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <nav className={styles.pager} aria-label={`Pagination : ${unit}`}>
      <button type="button" className={styles.small} onClick={() => onPage(page - 1)} disabled={page <= 1}>
        Précédent
      </button>
      <span aria-live="polite">
        Page {page} sur {pages} — {total} {unit}
      </span>
      <button type="button" className={styles.small} onClick={() => onPage(page + 1)} disabled={page >= pages}>
        Suivant
      </button>
    </nav>
  );
}

/** Paramètres d’URL : valeur ou défaut. */
export function intParam(value: string | null, fallback: number): number {
  const n = Number(value);
  return Number.isInteger(n) && n >= 1 ? n : fallback;
}

/** Met à jour des paramètres d’URL (null ou vide : supprimés) ; la page revient à 1 sauf `keepPage`. */
export function useParamSetter(): (changes: Record<string, string | null>, keepPage?: boolean) => void {
  const [, setSp] = useSearchParams();
  return (changes, keepPage = false) =>
    setSp((prev) => {
      const next = new URLSearchParams(prev);
      for (const [k, v] of Object.entries(changes)) {
        if (v === null || v === "") next.delete(k);
        else next.set(k, v);
      }
      if (!keepPage) next.delete("page");
      return next;
    });
}
