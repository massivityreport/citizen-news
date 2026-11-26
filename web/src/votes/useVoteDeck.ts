import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import { meKey } from "../api/hooks";
import type { TopicCard, VoteChoice } from "../api/types";
import { readLocalVotes, saveLocalVote } from "./storage";

const BATCH = 10;
const PREFETCH_WHEN_LEFT = 3;

interface State {
  cards: TopicCard[];
  index: number;
  choices: Record<number, VoteChoice>;
  exhausted: boolean;
  loadError: boolean;
}

type Action =
  | { type: "loaded"; items: TopicCard[] }
  | { type: "loadFailed" }
  | { type: "retry" }
  | { type: "voted"; topicId: number; choice: VoteChoice }
  | { type: "back" };

function reducer(s: State, a: Action): State {
  switch (a.type) {
    case "loaded": {
      const known = new Set(s.cards.map((c) => c.id));
      const fresh = a.items.filter((c) => !known.has(c.id));
      return { ...s, cards: [...s.cards, ...fresh], exhausted: fresh.length === 0, loadError: false };
    }
    case "loadFailed":
      return { ...s, loadError: true };
    case "retry":
      return { ...s, loadError: false };
    case "voted":
      return {
        ...s,
        choices: { ...s.choices, [a.topicId]: a.choice },
        index: Math.min(s.index + 1, s.cards.length),
      };
    case "back":
      return { ...s, index: Math.max(s.index - 1, 0) };
  }
}

export type VoteNotice = { kind: "rate-limited"; retryAfter?: number } | { kind: "error"; message: string };

/**
 * Flux de vote : cartes sans résultats, préchargement, retour en arrière, vote modifiable.
 * Sans session (401 sur /me ou sur POST /votes), les votes restent dans le navigateur.
 */
export function useVoteDeck() {
  const qc = useQueryClient();
  const [state, dispatch] = useReducer(reducer, undefined, () => ({
    cards: [],
    index: 0,
    choices: {},
    exhausted: false,
    loadError: false,
  }));
  const [localCount, setLocalCount] = useState(() => readLocalVotes().length);
  const [notice, setNotice] = useState<VoteNotice | null>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  // Garde synchrone contre le double clic dans le même tick (le state `busy` n'est lu qu'au rendu suivant).
  const voting = useRef(false);
  // Sujets déjà votés dans ce navigateur : on ne les redemande pas.
  const [initialSeen] = useState(() => readLocalVotes().map((v) => v.topic_id));

  const { cards, index, exhausted, loadError } = state;

  useEffect(() => {
    if (inFlight.current || exhausted || loadError) return;
    if (cards.length - index > PREFETCH_WHEN_LEFT) return;
    inFlight.current = true;
    const seen = [...new Set([...initialSeen, ...cards.map((c) => c.id)])];
    api
      .voteNext(BATCH, seen)
      .then(({ items }) => dispatch({ type: "loaded", items }))
      .catch(() => dispatch({ type: "loadFailed" }))
      .finally(() => {
        inFlight.current = false;
      });
  }, [cards, index, exhausted, loadError, initialSeen]);

  const vote = useCallback(
    async (choice: VoteChoice) => {
      const card = cards[index];
      if (!card || voting.current) return;
      voting.current = true;
      setBusy(true);
      setNotice(null);
      try {
        const payload = { topic_id: card.id, choice };
        let me = null;
        try {
          me = await qc.fetchQuery({ queryKey: meKey, queryFn: api.me, staleTime: 5 * 60_000 });
        } catch {
          // /me indisponible (5xx, réseau) : on ne perd pas le vote, il reste dans le navigateur.
          me = null;
        }
        if (me) {
          try {
            await api.vote(payload);
          } catch (e) {
            if (e instanceof ApiError && e.isUnauthorized) {
              // Session expirée : on bascule en mode anonyme sans perdre le vote.
              qc.setQueryData(meKey, null);
              me = null;
            } else if (e instanceof ApiError && e.isRateLimited) {
              setNotice({ kind: "rate-limited", retryAfter: e.retryAfter });
              return;
            } else {
              setNotice({ kind: "error", message: "Votre choix n’a pas pu être enregistré. Réessayez." });
              return;
            }
          }
        }
        if (!me) {
          if (!saveLocalVote(payload)) {
            setNotice({
              kind: "error",
              message: "Votre navigateur ne permet pas de conserver votre choix. Créez un compte pour l’enregistrer.",
            });
          }
          setLocalCount(readLocalVotes().length);
        }
        dispatch({ type: "voted", topicId: card.id, choice });
      } finally {
        voting.current = false;
        setBusy(false);
      }
    },
    [cards, index, qc],
  );

  const back = useCallback(() => {
    setNotice(null);
    dispatch({ type: "back" });
  }, []);
  const retry = useCallback(() => dispatch({ type: "retry" }), []);

  const card = cards[index] as TopicCard | undefined;
  return {
    card,
    position: index + 1,
    currentChoice: card ? state.choices[card.id] : undefined,
    canGoBack: index > 0,
    loading: cards.length === 0 && !exhausted && !loadError,
    loadingMore: !card && !exhausted && !loadError && cards.length > 0,
    loadError,
    finished: !card && exhausted,
    votedCount: Object.keys(state.choices).length,
    localCount,
    notice,
    busy,
    vote,
    back,
    retry,
  };
}
