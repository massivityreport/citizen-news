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
  "updated_at": "2026-11-26T09:30:00Z",
  "image_url": "https://cdn.example.org/photo.jpg"
}
```

`image_url` : `string | null`, toujours présent. URL **https** d'une image de l'article, validée à l'ingestion : schéma https (mis en minuscules), hôte fait de lettres, chiffres, points et tirets (IDN conservé en punycode) ou IP littérale publique, port valide, sans identifiants, sans espace, caractère de contrôle, antislash ni `" ' < >`, 500 caractères au plus. Les hôtes locaux ou privés sont refusés (`localhost`, `*.localhost`, IP privées, loopback, link-local, réservées ou non spécifiées, IPv4 comme IPv6) : le navigateur du lecteur ferait la requête sur son propre réseau. Valeur : l'image de l'article le plus récent du sujet (`published_at` décroissant, les dates absentes en dernier, puis `id` décroissant ; contrairement à `sources`, `fetched_at` ne sert pas de repli) qui en a une ; `null` si aucun article n'en a.

**Hotlink uniquement** (décision de l'humain) : le serveur ne télécharge, ne copie ni ne met en cache aucune image, il ne garde que l'URL ; pas de proxy d'images. Le navigateur du lecteur charge l'image directement chez le média.

**Limites connues** : les images appartiennent aux médias (droits d'auteur des images tierces) ; charger une image depuis le média **révèle l'adresse IP du lecteur** (et son navigateur) à ce média. Pas de proxy ni de CSP dans cette version.

#### Source des images (ingestion)

Pour chaque entrée de flux, premier candidat valide parmi, dans l'ordre : `media:content` (`medium="image"` ou type `image/*`), `media:thumbnail`, enclosure de type `image/*`, première `<img src>` du contenu puis du résumé HTML. URL relative résolue contre le lien de l'article ; un candidat invalide passe au suivant, aucun ne fait échouer l'ingestion.

**Réingestion** : les articles déjà en base n'ont pas d'image. Quand un article existant a `image_url` à `NULL` et que son flux en fournit maintenant une valide, le cycle d'ingestion normal la renseigne (mise à jour de cette colonne seule : ni `topic_id`, ni `published_at`, ni regroupement). Une image déjà enregistrée n'est jamais remplacée. Les articles qui ont quitté les flux restent sans image ; il n'y a pas de commande de réingestion séparée.

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

Classement : mélange du soutien citoyen et de la fraîcheur. Chaque carte a toujours un `support` et une `reason`. La v1 n'émet que les quatre raisons ci-dessus (pas d'« Alerte minoritaire »). Détail : [halving.md](halving.md).

### `GET /api/vote/next?count=10&seen=1,2` — public

Prochains sujets à évaluer. `count` : entier 1–20, défaut 10. `seen` : identifiants déjà vus, séparés par des virgules (exclus du résultat). Sujets mélangés par le Successive Halving (nouveaux, repêchage, actifs), hors déjà votés si une session est présente (le cookie est facultatif). **Résultats masqués** : les éléments sont des `TopicCard` **sans** `support` ni `reason` ni aucun compteur.

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

`description` contient une clé par paramètre de `params`, avec un texte en français (les textes ci-dessus sont des exemples ; ceux de l'API sont plus détaillés).

## Santé (implémenté)

### `GET /api/health`

- `200` → `{"status": "ok"}` si la base répond.
- `503` → `{"detail": "Base de données indisponible"}`.
