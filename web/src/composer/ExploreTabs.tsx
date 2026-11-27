import { useRef, type KeyboardEvent } from "react";
import type { PoolTab } from "../api/types";
import styles from "./composer.module.css";

export const TABS: { id: PoolTab; label: string }[] = [
  { id: "random", label: "Au hasard" },
  { id: "recent", label: "Récents" },
  { id: "radar", label: "Sous les radars" },
];

export const tabId = (t: PoolTab) => `tab-${t}`;
export const PANEL_ID = "panneau-sujets";

/** Onglets (role=tablist) : flèches gauche/droite, Début/Fin ; l'onglet actif prend le focus et s'active. */
export function ExploreTabs({ value, onChange }: { value: PoolTab; onChange: (t: PoolTab) => void }) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    const i = TABS.findIndex((t) => t.id === value);
    let next = -1;
    if (e.key === "ArrowRight") next = (i + 1) % TABS.length;
    else if (e.key === "ArrowLeft") next = (i - 1 + TABS.length) % TABS.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = TABS.length - 1;
    if (next < 0) return;
    e.preventDefault();
    onChange(TABS[next].id);
    refs.current[TABS[next].id]?.focus();
  }

  return (
    <div role="tablist" aria-label="Logique d’exploration" className={styles.tabs} onKeyDown={onKeyDown}>
      {TABS.map((t) => (
        <button
          key={t.id}
          ref={(el) => void (refs.current[t.id] = el)}
          type="button"
          role="tab"
          id={tabId(t.id)}
          aria-selected={value === t.id}
          aria-controls={PANEL_ID}
          tabIndex={value === t.id ? 0 : -1}
          className={styles.tab}
          onClick={() => onChange(t.id)}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
