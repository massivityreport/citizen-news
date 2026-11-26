# Contrat HTTP v1 — Citizen News

Contrat que les tâches backend suivantes implémentent et que le front consomme.

- Préfixe : `/api`. Corps et réponses en JSON (`Content-Type: application/json`).
- Authentification : cookie de session `httpOnly` posé par `POST /api/auth/verify`. Le front envoie les requêtes avec les cookies (`credentials: "include"`).
- Erreurs : `{"detail": "<message en français>"}` avec le code HTTP adapté. `429` pour la limitation de débit (en-tête `Retry-After` en secondes).
- Dates : ISO 8601 UTC (`2026-11-26T10:00:00Z`).
- Seul `GET /api/health` est déjà implémenté (voir en fin de document) ; le reste est le contrat cible.

## Types communs

### Carte de sujet (`TopicCard`)

```json
{
  "id": 12,
  "title": "…",
  "summary": "…",
  "sources": [
    { "name": "Nom du média", "url": "https://…", "title": "Titre de l'article", "published_at": "2026-11-26T09:30:00Z" }
  ],
  "first_seen_at": "2026-11-25T18:00:00Z",
  "updated_at": "2026-11-26T09:30:00Z"
}
```

### Soutien (`support`) et raison (`reason`)

```json
"support": { "level": "low|medium|high", "votes_count": 42 },
"reason":  { "code": "common_priority|strong_mobilisation|under_the_radar|emerging", "label": "Priorité commune" }
```

`label` est un libellé en français prêt à afficher.

| `reason.code` | Libellé indicatif |
|---|---|
| `common_priority` | Priorité commune |
| `strong_mobilisation` | Forte mobilisation |
| `under_the_radar` | Sous les radars |
| `emerging` | Sujet émergent |

### Choix de vote (`choice`)

`"more"` (il faut davantage en parler) · `"not_priority"` (ce n'est pas prioritaire) · `"unknown"` (je ne sais pas).

## Sujets

### `GET /api/topics/front?limit=20` — public

La une citoyenne. `limit` : entier 1–50, défaut 20.

```json
{ "items": [ { /* TopicCard */, "support": {…}, "reason": {…} } ] }
```

### `GET /api/vote/next?count=10&seen=1,2` — public

Prochains sujets à évaluer. `count` : entier 1–20, défaut 10. `seen` : identifiants déjà vus, séparés par des virgules (exclus du résultat). **Résultats masqués** : les éléments sont des `TopicCard` **sans** `support` ni `reason` ni aucun compteur.

```json
{ "items": [ { /* TopicCard */ } ] }
```

## Votes

### `POST /api/votes` — session requise

Requête : `{"topic_id": 12, "choice": "more"}`. Remplace le vote existant du compte sur ce sujet (un seul vote par compte et par sujet).

- `200` → `{"topic_id": 12, "choice": "more"}`
- `401` sans session valide · `404` sujet inconnu · `422` choix invalide · `429`

### `POST /api/votes/claim` — session requise

Rattache au compte les votes anonymes gardés dans le navigateur. Requête :

```json
{ "votes": [ { "topic_id": 12, "choice": "more" } ] }
```

Un vote déjà présent sur le sujet n'est pas écrasé ; les sujets inconnus sont ignorés.

- `200` → `{"claimed": 3}` (nombre de votes effectivement enregistrés)
- `401` · `422` · `429`

### `GET /api/votes/mine` — session requise

- `200` → `{"votes": [ {"topic_id": 12, "choice": "more"} ]}`
- `401` sans session.

## Authentification (lien magique)

### `POST /api/auth/magic-link`

Requête : `{"email": "a@example.org"}`.

- `202` **toujours** (corps `{}`), que le compte existe ou non, sans révéler l'un ou l'autre. Un compte est créé à la vérification du premier lien.
- `422` e-mail mal formé · `429` limitation de débit.

### `POST /api/auth/verify`

Requête : `{"token": "…"}` (jeton à usage unique, durée de vie limitée).

- `200` → `{"email": "a@example.org"}` et en-tête `Set-Cookie` de session `httpOnly` (`SameSite=Lax`, `Secure` hors développement).
- `400` jeton invalide, expiré ou déjà utilisé · `429`.

### `POST /api/auth/logout`

- `204`, supprime le cookie de session (idempotent).

### `GET /api/me`

- `200` → `{"email": "a@example.org"}`
- `401` sans session.

## Halving

### `GET /api/halving/config` — public

Paramètres actifs du Successive Halving et leur description (page de transparence).

```json
{
  "params": {
    "min_votes_first_decision": 20,
    "keep_ratio": 0.5,
    "waves": 3,
    "new_topic_traffic_share": 0.3,
    "rescue_share": 0.1
  },
  "description": {
    "min_votes_first_decision": "Nombre minimal de votes avant la première décision.",
    "keep_ratio": "Proportion de sujets conservés à chaque vague.",
    "waves": "Nombre de vagues de sélection.",
    "new_topic_traffic_share": "Part du trafic de vote réservée aux nouveaux sujets.",
    "rescue_share": "Part du trafic de vote réservée au repêchage de sujets en réserve."
  }
}
```

`description` contient une clé par paramètre de `params`, avec un texte en français.

## Santé (implémenté)

### `GET /api/health`

- `200` → `{"status": "ok"}` si la base répond.
- `503` → `{"detail": "Base de données indisponible"}`.
