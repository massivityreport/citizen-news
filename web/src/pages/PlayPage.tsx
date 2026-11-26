import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import type { VoteChoice } from "../api/types";
import { useMe } from "../api/hooks";
import { TopicImage } from "../components/TopicImage";
import { SourceList } from "../components/SourceList";
import topic from "../components/Topic.module.css";
import { usePageTitle } from "../components/usePageTitle";
import { useVoteDeck, type VoteNotice } from "../votes";
import styles from "./PlayPage.module.css";

const TITLE = "À vous de jouer";

const CHOICES: { value: VoteChoice; label: string }[] = [
  { value: "more", label: "Il faut davantage en parler" },
  { value: "not_priority", label: "Ce n’est pas prioritaire" },
  { value: "unknown", label: "Je ne sais pas / pas assez d’informations" },
];

function noticeText(n: VoteNotice): string {
  if (n.kind === "error") return n.message;
  return n.retryAfter
    ? `Vous votez très vite ! Merci de patienter ${n.retryAfter} seconde${n.retryAfter > 1 ? "s" : ""} avant de réessayer.`
    : "Vous votez très vite ! Merci de patienter un instant avant de réessayer.";
}

export default function PlayPage() {
  const h1 = usePageTitle(TITLE);
  const deck = useVoteDeck();
  const me = useMe();
  const anonymous = me.data === null;
  const { card, finished } = deck;

  // Focus sur la nouvelle carte (ou le message de fin) après chaque vote / retour, pas à l'arrivée.
  const focusRef = useRef<HTMLHeadingElement>(null);
  const arrived = useRef(false);
  const key = card ? card.id : finished ? "end" : null;
  useEffect(() => {
    if (key === null) return;
    if (arrived.current) focusRef.current?.focus();
    arrived.current = true;
  }, [key]);

  const live = deck.notice ? "" : finished ? "Vous avez tout évalué pour l’instant." : card && deck.votedCount + (deck.canGoBack ? 1 : 0) > 0 ? `Sujet suivant : ${card.title}` : "";

  return (
    <section>
      <h1 ref={h1} tabIndex={-1}>{TITLE}</h1>
      <p className={styles.intro}>Pour chaque sujet, dites s’il mérite plus d’attention. Les résultats restent masqués.</p>

      {anonymous && deck.localCount > 0 && (
        <aside className={styles.banner} aria-label="Enregistrer vos choix">
          <p>Vos choix sont gardés dans ce navigateur seulement.</p>
          <Link to="/connexion">Créer un compte pour enregistrer vos choix</Link>
        </aside>
      )}

      {deck.notice && (
        <p className={styles.notice} role="alert">{noticeText(deck.notice)}</p>
      )}

      <div className={topic.srOnly} role="status" aria-live="polite">{live}</div>

      {(deck.loading || deck.loadingMore) && (
        <div aria-busy="true">
          <p role="status" className={topic.srOnly}>Chargement des sujets…</p>
          <div className={styles.skeleton} aria-hidden="true" />
        </div>
      )}

      {deck.loadError && !card && (
        <div className={styles.state} role="alert">
          <p>Impossible de charger les sujets pour le moment.</p>
          <button type="button" className={styles.btn} onClick={deck.retry}>Réessayer</button>
        </div>
      )}

      {card && (
        <article key={card.id} className={`${topic.card} ${styles.card}`} aria-labelledby="vote-title">
          <TopicImage url={card.image_url} title={card.title} />
          <p className={styles.progress}>Sujet n° {deck.position}</p>
          <h2 id="vote-title" ref={focusRef} tabIndex={-1}>{card.title}</h2>
          <p className={topic.summary}>{card.summary}</p>
          <SourceList sources={card.sources} />
          <div className={styles.choices} role="group" aria-label="Votre choix">
            {CHOICES.map((c) => (
              <button
                key={c.value}
                type="button"
                className={styles.choice}
                aria-pressed={deck.currentChoice === c.value}
                disabled={deck.busy}
                onClick={() => void deck.vote(c.value)}
              >
                {c.label}
              </button>
            ))}
          </div>
          <button type="button" className={styles.back} onClick={deck.back} disabled={!deck.canGoBack || deck.busy}>
            ← Revenir au sujet précédent
          </button>
        </article>
      )}

      {finished && (
        <div className={styles.state}>
          <h2 ref={focusRef} tabIndex={-1}>Vous avez tout évalué pour l’instant</h2>
          <p>Merci ! De nouveaux sujets arrivent régulièrement. Découvrez en attendant la une citoyenne.</p>
          <Link to="/" className={styles.btn}>Voir la une citoyenne</Link>
          {deck.canGoBack && (
            <p>
              <button type="button" className={styles.back} onClick={deck.back}>
                ← Revenir au dernier sujet pour modifier mon choix
              </button>
            </p>
          )}
        </div>
      )}
    </section>
  );
}
