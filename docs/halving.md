# Le Successive Halving de Citizen News

Comment un sujet passe de « nouveau » à « émergent », et comment le flux de vote est composé. Implémentation : `api/app/services/halving.py` (calcul des états), `api/app/services/voteflow.py` (flux de vote), `api/app/services/support.py` et `front.py` (une citoyenne). Paramètres : `api/config/halving.yaml` (sévérité) et `api/config/front.yaml` (une).

## Vue d'ensemble

```
nouveau (vague 0) ──quota 20, top 50 %──▶ actif (vague 1) ──quota 40, top 50 %──▶ actif (vague 2) ──quota 80, top 50 %──▶ émergent
        │                                       │                                        │
        └──────────── les autres ───────────────┴────────────────────────────────────────┘
                                                ▼
                                            réserve ──(10 % du flux de vote, nouveau lot de votes)──▶ réévaluation
```

- **États** (`topics.state`) : `new`, `active`, `reserve`, `emerged`. **Vague** (`topics.wave`) : nombre de vagues franchies (pour un sujet en réserve : la vague où il a été écarté).
- Seuls les votes des **comptes** comptent (table `votes`). Les votes anonymes restent dans le navigateur jusqu'au rattachement.
- Le calcul tourne dans le **worker** (`python -m app.cli halve`, lancé aussi par `refresh`), jamais dans une requête de vote. Il est **déterministe** (aucun hasard) et **idempotent** : relancé juste après, il ne change rien. Il ne modifie pas `topics.updated_at`, qui reste la date du dernier article (colonnes dédiées : `state_changed_at`, `evaluated_at`, `votes_at_eval`).

## Le score

`score` = borne basse de l'intervalle de Wilson (z = 1,96) de la part de « Il faut davantage en parler » **parmi les avis exprimés** (« davantage » + « pas prioritaire »).

- « Je ne sais pas » n'est pas un avis : il ne fait pas bouger la part, mais il compte dans le **total de votes** (donc dans les quotas).
- La borne basse évite de favoriser les petits échantillons : **15 « davantage » sur 20 avis** donne 0,53, **3 sur 3** donne 0,44.
- Un sujet sans aucun vote « davantage » (score 0) n'est jamais promu.

## Les vagues

Le **quota** de la vague *w* est `min_votes_first_decision × 2^w` votes au total (cumulés) : 20, 40, 80 avec les valeurs par défaut. Chaque vague demande plus de votes, donc la concentration du trafic augmente : il faut plus de votes pour décider sur des sujets de plus en plus peu nombreux.

À chaque exécution, pour *w* = 0 … `waves`−1, dans cet ordre :

1. **Candidats** : les sujets de la vague *w* (`new` ou `active`) qui ont atteint le quota ; plus les sujets `reserve` de la vague *w* qui ont reçu un nouveau lot de `min_votes_first_decision` votes depuis leur dernière évaluation (repêchage).
2. **Pairs** : les autres sujets déjà évalués à cette vague (au moins le quota de votes, vague ≥ *w*, pas `new`). Ils ne changent pas d'état, mais comptent dans la comparaison : sans eux, un sujet arrivant seul à son quota serait toujours « la meilleure moitié ».
3. On classe candidats et pairs par score (à égalité, l'identifiant le plus petit d'abord) et on garde les `ceil(keep_ratio × effectif)` premiers (au moins 1). Un candidat dans ce haut du classement est **promu** : vague *w*+1, `active`, ou `emerged` si *w*+1 = `waves`. Les autres passent en **réserve** (vague inchangée).

Après `waves` vagues franchies, le sujet est `emerged`. Il n'est plus proposé au vote, sauf en dernier recours quand il n'y a rien d'autre à proposer.

### Repêchage : on ne condamne jamais définitivement

« Jamais définitif » s'entend **dans la fenêtre de regroupement** : un sujet en réserve dont le dernier article sort de la fenêtre (`window_hours`) n'est plus proposé au repêchage, l'actualité périmée n'étant pas re-testée.

Le flux de vote réserve `rescue_share` de ses places à des sujets en réserve, tirés au hasard parmi la moitié **la moins récemment évaluée**. Quand un sujet repêché a reçu `min_votes_first_decision` nouveaux votes, il redevient candidat à sa vague, noté sur **tous** ses votes, face aux mêmes pairs. S'il retrouve le haut du classement, il est promu ; sinon il reste en réserve, avec une nouvelle date d'évaluation (donc il passe à l'arrière de la file de repêchage).

### Exemple chiffré

Paramètres par défaut. Huit sujets reçoivent leur premier lot de 20 votes (davantage / pas prioritaire / ne sait pas) :

| Sujet | Votes | Score |
|---|---|---|
| D | 18 / 2 / 0 | 0,70 |
| A | 15 / 5 / 0 | 0,53 |
| G | 8 / 2 / 10 | 0,49 |
| B | 3 / 0 / 17 | 0,44 |
| C | 12 / 8 / 0 | 0,39 |
| E | 10 / 10 / 0 | 0,30 |
| F | 5 / 15 / 0 | 0,11 |
| H | 1 / 19 / 0 | 0,01 |

- **Vague 0** (quota 20) : on garde `ceil(0,5 × 8)` = 4 sujets. D, A, G et B passent en vague 1 (`active`) ; C, E, F, H passent en `reserve`. Noter que B (3 sur 3, mais 17 « je ne sais pas ») passe de justesse derrière G : le petit échantillon est pénalisé sans être éliminé. A (15 sur 20) devance B (3 sur 3).
- **Vague 1** (quota 40) : D atteint 40 votes (28 / 4 / 8, score 0,72) et A aussi (25 / 15 / 0, score 0,47). Ils sont seuls à ce quota : le classement ne compte que D et A, on garde 1 sujet. D passe en vague 2, A rejoint la réserve.
- **Repêchage** : C (en réserve, 20 votes) est proposé grâce aux 10 % du flux. Il reçoit 20 nouveaux votes (16 « davantage », 4 « pas prioritaire »), soit 28 / 12 / 0 : son score passe à 0,55. Il est réévalué à la vague 0 face aux autres sujets déjà évalués : il se classe 2ᵉ sur 8, dans les 4 premiers, et passe en vague 1. Comme il totalise 40 votes, soit le quota de la vague 1, il est aussitôt évalué à cette vague face à D et A : 2ᵉ sur 3, il en garde `ceil(0,5 × 3)` = 2 et passe en vague 2.
- **Vague 3** : D et C, en vague 2, ont besoin de 80 votes chacun ; une fois ce quota atteint et le classement passé, ils deviennent `emerged` (3 vagues franchies).

### Paramètres (`api/config/halving.yaml`)

| Paramètre | Défaut | Effet |
|---|---|---|
| `min_votes_first_decision` | 20 | Quota de la vague 0, et taille du lot de repêchage. Le quota double à chaque vague. |
| `keep_ratio` | 0,5 | Proportion (de 0 exclu à 1 exclu) du classement conservée à chaque vague. Plus bas = plus sévère. |
| `waves` | 3 | Nombre de vagues à franchir avant `emerged` (1 à 10). |
| `new_topic_traffic_share` | 0,30 | Part des sujets du flux de vote tirés parmi les `new`. |
| `rescue_share` | 0,10 | Part tirée parmi les `reserve`. La somme des deux parts ne dépasse pas 1. |

Hors bornes, le chargement échoue. Une sévérité extrême reste sûre : on garde toujours au moins un sujet par comparaison, jamais zéro.

Limites connues : `POST /api/votes` accepte tout sujet existant (même sorti de la fenêtre ou en réserve), car modifier un vote antérieur doit rester possible ; seuls le quota de débit et l'unicité compte + sujet bornent les votes ; le score ne se calcule que sur les votes de la table `votes` ; un sujet qui reste seul avec des pairs peu nombreux est comparé à peu de monde (la sélection devient plus indulgente quand l'échantillon est petit) ; changer les paramètres ne recalcule pas les sujets déjà évalués (ils sont reclassés seulement quand ils redeviennent candidats).

## Le flux de vote (`GET /api/vote/next`)

Les sujets proposés sont ceux de la fenêtre de regroupement avec assez de médias (comme avant), moins `seen` et, avec une session, ceux déjà votés. Aucun résultat dans la réponse.

| Catégorie | Part du flux | Sujets |
|---|---|---|
| nouveaux | `new_topic_traffic_share` (30 %) | état `new` (vague 0) |
| repêchage | `rescue_share` (10 %) | état `reserve` |
| proches de l'émergence | la moitié du reste (30 %) | `active`, dernière vague (`waves`−1) |
| actifs | l'autre moitié (30 %) | `active`, autres vagues |

Pour `count` sujets, chaque catégorie reçoit `⌊count × part⌋` places, et les places restantes sont tirées au hasard en pondérant par les restes (la part est donc respectée en moyenne même avec `count=1`). Une catégorie vide ou trop courte cède ses places aux autres, au prorata de leurs parts. Dans une catégorie, les sujets qui n'ont pas encore atteint leur quota passent d'abord (c'est ce qui garantit le minimum de votes aux nouveaux), au hasard ; pour le repêchage, tirage au hasard dans la moitié la moins récemment évaluée. L'ordre final est mélangé.

## La une citoyenne (`GET /api/topics/front`)

- **Niveau de soutien** (`support.level`) : `high` / `medium` selon le nombre de votes **et** le score (seuils dans `front.yaml`), sinon `low`. `votes_count` : total des votes, « je ne sais pas » compris.
- **Raison** (`reason`), première règle qui s'applique : `common_priority` (beaucoup de votes et score élevé), `under_the_radar` (au plus `max_sources` médias et score élevé), `strong_mobilisation` (beaucoup de « davantage » avec au moins un soutien moyen), `emerging` (afflux de votes récents, ou passage récent à l'état `emerged`). La v1 n'a ni « Alerte minoritaire » ni « Priorité transversale » : elles demandent des groupes de sensibilités.
- **Défaut documenté** : un sujet récent (dernier article de moins de `recent_hours`) qui n'a pas encore assez de votes pour être jugé reçoit `emerging` (« Sujet émergent »). Un sujet qui a assez de votes mais ne mérite aucune raison est écarté de la une, tout comme les sujets en `reserve`.
- **Éligibilité** : au moins `min_sources_for_front` médias (`clustering.yaml`), **ou** raison `under_the_radar` ; au moins `ranking.min_votes` votes ou sujet récent.
- **Classement** : `support_weight × score + freshness_weight × fraîcheur`, où la fraîcheur vaut `0,5^(âge du dernier article / demi-vie)`.
