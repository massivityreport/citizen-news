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

### `GET /api/topics/front?limit=10` — public

La une citoyenne. `limit` : entier 1–50, défaut 10.

```json
{ "items": [ { /* TopicCard */, "support": {…}, "reason": {…} } ], "has_more": true }
```

`has_more` : vrai s'il existe des sujets classés au-delà de `limit`.

**Pagination (« Voir plus »)** : pas d'`offset` ni de curseur. Le rang dépend du temps (fraîcheur) : un offset donnerait des doublons ou des trous d'une page à l'autre. Le front redemande donc la liste complète avec un `limit` croissant (10, 20, 30… jusqu'à 50) et **remplace** la liste affichée par la réponse, sans jamais concaténer. À un instant donné, la liste `limit=N` est le préfixe de la liste `limit=N+10`.

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

## Admin

Backoffice derrière un mot de passe unique (`ADMIN_PASSWORD`), sans comptes ni rôles. Toutes les routes `/api/admin/*` répondent avec `Cache-Control: no-store` et `X-Robots-Tag: noindex`. Les messages d'erreur sont `{"detail": "<message en français>"}`.

**Cookie `cn_admin`** : posé par `login`, `httpOnly`, `SameSite=Lax`, `Secure` si `COOKIE_SECURE=true`, `Path=/api/admin` (le navigateur ne l'envoie qu'aux routes admin), `Max-Age` = `ADMIN_SESSION_HOURS` (8 h par défaut). Valeur : jeton aléatoire, seul son SHA-256 est stocké (table `admin_sessions`). Indépendant de la session citoyenne : `cn_session` ne donne aucun accès admin, `cn_admin` n'en donne aucun aux routes citoyennes.

**Protection** : toute route admin autre que `login`/`logout` exige un `cn_admin` valide et non expiré (dépendance `require_admin`, appliquée au routeur `admin.protected`) ; sinon `401 {"detail": "Authentification administrateur requise"}`. Une route qui reçoit un 401 du backoffice ramène le front à la connexion.

### `POST /api/admin/login`

Requête : `{"password": "…"}` (1024 caractères au plus).

- `200` → `{"authenticated": true}` et `Set-Cookie: cn_admin=…`.
- `401` → `{"detail": "Mot de passe incorrect"}` (message unique), sans cookie.
- `422` corps invalide · `429` trop de tentatives (par IP : `RATE_LIMIT_ADMIN_LOGIN_PER_IP`, 10 par `RATE_LIMIT_ADMIN_LOGIN_WINDOW_SECONDS`, 900 s), avec `Retry-After` en secondes. Les tentatives réussies comptent aussi.

### `POST /api/admin/logout`

- `204`, supprime la session côté serveur et le cookie (idempotent, même sans session).

### `GET /api/admin/me`

- `200` → `{"authenticated": true}` · `401` sans session valide.

### Sources (`/api/admin/sources`)

Les sources médias sont gérées en base : **la base est la référence**, `api/config/feeds.yaml` ne sert qu'à l'initialiser (voir `api/README.md`). Toutes ces routes exigent une session admin (`401` sinon, y compris avec une session citoyenne). Source :

```json
{ "id": 3, "name": "Le Monde", "feed_url": "https://…/rss.xml", "active": true, "article_count": 42, "last_article_at": "2026-11-26T09:30:00Z" }
```

`last_article_at` : `string | null`, le plus récent des articles de la source, par `published_at`, ou `fetched_at` (date de récupération) pour un article sans date, comme le regroupement ; `null` sans article. `article_count` compte tous les articles, source active ou non.

| Route | Effet |
|---|---|
| `GET /api/admin/sources` | `200` → tableau de sources, trié par nom (sans casse) puis `id`. Une seule requête SQL (jointure + agrégats). |
| `GET /api/admin/sources/{id}` | `200` → une source · `404` `Source introuvable.` |
| `POST /api/admin/sources` | Corps `{"name", "feed_url"}`. `201` → la source créée (active). Voir ci-dessous. |
| `POST /api/admin/sources/{id}/deactivate` | `200` → la source, `active: false`. Idempotent. **Garde** les articles et les sujets ; l'ingestion ne lit plus ce flux. `404` si inconnue. |
| `POST /api/admin/sources/{id}/reactivate` | `200` → la source, `active: true`. Idempotent. `404` si inconnue. |
| `DELETE /api/admin/sources/{id}?confirm=<n>` | Suppression **définitive**. `confirm` (entier ≥ 0, obligatoire) doit être le nombre d'articles qui disparaissent (`article_count`). `200` → `{"id", "deleted_articles"}` · `409` si `confirm` ne correspond pas (rien n'est supprimé ; le message donne le vrai nombre) · `404` · `422` si `confirm` manque ou n'est pas un entier. |

**Ajout** (`POST`). Le nom est nettoyé (espaces et caractères de contrôle) : 1 à 100 caractères. L'URL : `http` ou `https` seulement, 2048 caractères au plus, sans espace ni `\`, sans identifiants (`user:pass@`) ; schéma et hôte sont mis en minuscules, le fragment (`#…`) est retiré (même forme normale pour `feeds.yaml` et les suppressions : une variante de casse n'est ni un doublon ni une recréation). Ordre des contrôles, le premier qui échoue répond :

1. `422` entrée invalide (nom vide ou trop long, schéma, identifiants, URL trop longue…), message précis en français ; aucune requête réseau.
2. `409` `Cette source existe déjà (elle est peut-être désactivée).` (doublon d'URL, source désactivée comprise) ; aucune requête réseau.
3. Le serveur récupère l'URL (garde SSRF ci-dessous). Échec, quelle qu'en soit la cause (adresse refusée, hôte inconnu, injoignable, délai, statut HTTP ≠ 200, trop de redirections, réponse trop volumineuse) : `422` avec **un seul message** : `Cette adresse est refusée ou injoignable. Vérifiez l'adresse du flux.` Ni l'adresse résolue ni la cause ne sont renvoyées : l'API ne permet pas de sonder le réseau interne.
4. Le contenu doit être un flux lisible avec **au moins un article valide** : sinon `422` `Cette adresse ne renvoie pas un flux RSS ou Atom lisible.` ou `Ce flux ne contient aucun article exploitable.` (un document XML bien formé mais vide, comme un sitemap, ne prouve pas que c'est un flux). Rien n'est enregistré.

Ré-ajouter l'URL d'une source supprimée définitivement est permis ; elle quitte alors la liste des suppressions.

**Garde SSRF** (le serveur va chercher l'URL). Appliquée à l'URL et à **chaque** redirection (suivies à la main, 5 au plus, schéma http(s) seulement, `Location` revérifiée) :

- hôte : nom DNS ordinaire ou IP littérale publique ; `localhost` et `*.localhost` refusés ; formes d'IP exotiques (`2130706433`, `0x7f000001`, `127.1`) refusées ;
- le nom est résolu **une fois** et **toutes** les adresses doivent être publiques : refus des adresses privées, loopback, link-local (dont `169.254.169.254`, métadonnées cloud), non spécifiées (`0.0.0.0`, `::`), partagées (`100.64/10`), réservées, multicast, IPv6 locales (`::1`, `fe80::`, `fc00::`) et IPv6 qui encapsulent une IPv4 (mappées `::ffff:10.0.0.1`, NAT64 `64:ff9b::7f00:1`, SIIT `::ffff:0:127.0.0.1`, compatibles `::127.0.0.1`, 6to4 `2002:7f00:1::` : jugées comme l'IPv4 qu'elles contiennent), préfixe NAT64 local `64:ff9b:1::/48`, site-local `fec0::/10`, `192.0.0.0/24` ;
- la connexion se fait vers l'IP validée (en-tête `Host` et SNI/certificat TLS conservés) : une réponse DNS qui change entre la vérification et la connexion (DNS rebinding) ne détourne pas la requête ;
- variables proxy de l'environnement ignorées ; réponse non compressée (`Accept-Encoding: identity`) ; 10 s au total, 5 Mo au plus ;
- la même garde protège l'ingestion périodique de chaque source (celles de `feeds.yaml` comprises), pas seulement l'ajout ;
- limite : la résolution DNS (`getaddrinfo`) n'a pas de délai propre, le délai de 10 s n'est vérifié qu'entre les étapes.

**Suppression** : les articles partent en cascade, l'URL est mémorisée dans `deleted_sources` pour que l'initialisation depuis `feeds.yaml` ne recrée pas la source. Un sujet qui perd des articles n'est pas supprimé (ses votes sont conservés) : s'il lui reste moins de médias distincts que le minimum pour la une, ou plus aucun article, il n'apparaît plus sur la une ni dans le flux de vote ; son titre et son résumé ne changent qu'au prochain regroupement qui lui rattache un article : un sujet mixte garde donc, après la suppression, un titre calculé avec l'ancien article.

### Articles, sujets et votes (lecture seule)

Routes sous `/api/admin`, toutes derrière la session admin (`401` sinon, y compris avec une session citoyenne). **Aucune réponse ne contient d'adresse e-mail, de hash ni de donnée personnelle** : un vote est `{date, choix, numéro de compte}`, le numéro étant l'`id` du compte (un test parcourt les réponses et échoue si une adresse y apparaît).

**Pagination** (`/articles`, `/topics`, `/topics/{id}/votes`) : `page` (≥ 1, 100 000 au plus, défaut 1) et `page_size` (1 à 200, défaut 50) ; hors bornes → `422`. Réponse `{"items": […], "total": <n>, "page": <p>, "page_size": <s>}`. Une page au-delà de la dernière répond `200` avec `items: []` et le vrai `total`. Pagination et tri sont faits par le serveur (`LIMIT/OFFSET` + un `COUNT`), jamais en mémoire. Tout paramètre invalide → `422 {"detail": "Requête invalide (champ : …)"}` (ou un message précis pour les dates).

**Tri** : `sort` et `order` (`asc`/`desc`) sont des listes blanches strictes (`422` sinon) ; l'`ORDER BY` vient d'une table fermée du serveur, jamais de l'entrée. Ordre total : l'`id` départage les égalités (même sens que `order`) ; les valeurs absentes (article sans date, sujet sans changement d'état, article non regroupé) viennent **toujours en dernier**, dans les deux sens.

#### `GET /api/admin/articles`

Paramètres : `page`, `page_size`, `sort` = `date` (défaut, `published_at`) | `source` (nom, sans casse) | `topic` (titre du sujet, sans casse) ; `order` (défaut `desc`) ; filtres :

- `topic_id` (entier ≥ 1) : articles de ce sujet ;
- `source_id` (entier ≥ 1) ;
- `date_from`, `date_to` : `AAAA-MM-JJ` strict (une date-heure est refusée), entre 2000 et 2100, `date_from` ≤ `date_to`, sinon `422`. Filtre sur **`published_at`**, en **UTC** : `date_from` inclus (00:00 UTC), `date_to` inclus **jour entier** (jusqu'au lendemain 00:00 UTC exclu). **Un article sans date de publication est exclu dès qu’une borne est donnée** (`published_at` nul ne satisfait aucune comparaison) (il apparaît sans filtre de date, en dernier du tri par date) ;
- `ungrouped=true` : `topic_id IS NULL` (`false` = pas de filtre). **Incompatible avec `topic_id` → `422`** `« ungrouped » et « topic_id » s'excluent`.

Les filtres se combinent (ET). Item :

```json
{ "id": 12, "title": "…", "url": "https://…", "published_at": "2026-11-03T10:00:00Z", "fetched_at": "2026-11-03T10:05:00Z",
  "source": { "id": 3, "name": "Le Monde", "active": true },
  "topic": { "id": 7, "title": "Retraites" }, "grouped": true }
```

`topic: null` et `grouped: false` pour un article non regroupé. Une source désactivée reste listée (`source.active: false`). Deux requêtes SQL quelle que soit la taille de page (la page avec ses jointures sur la source et le sujet, et un `COUNT`).

#### `GET /api/admin/topics`

Paramètres : `page`, `page_size`, `sort` = `votes` (défaut) | `title` | `state` (ordre du cycle de vie : new, active, emerged, reserve) | `articles` | `state_changed` ; `order` (défaut `desc`) ; filtre `state` = `new` | `active` | `reserve` | `emerged`. Item :

```json
{ "id": 7, "title": "Retraites", "state": "active", "wave": 1, "state_changed_at": "2026-11-20T09:30:00Z",
  "article_count": 5, "source_count": 3, "vote_count": 41, "image_url": "https://…" }
```

`source_count` : médias distincts. `image_url` : image du plus récent article qui en a une (comme les cartes citoyennes), ou `null`. Agrégats calculés par le SQL de la page (deux requêtes avec le `COUNT`).

#### `GET /api/admin/topics/{id}`

`404 {"detail": "Sujet introuvable."}` si inconnu. Sinon :

```json
{
  "id": 7, "title": "…", "summary": "…", "state": "emerged", "wave": 3,
  "first_seen_at": "…", "updated_at": "…", "state_changed_at": "…|null", "evaluated_at": "…|null",
  "article_count": 5, "source_count": 3,
  "support": { "score": 0.61, "level": "high", "votes_count": 40 },
  "front": { "on_front": true, "reason": { "code": "strong_mobilisation", "label": "Forte mobilisation" } },
  "votes": { "more": 30, "not_priority": 6, "unknown": 4, "total": 40, "voters": 40, "first_vote_at": "…|null",
             "daily": [ { "date": "2026-11-24", "more": 10, "not_priority": 2, "unknown": 0, "total": 12 } ] },
  "articles": [ { "id": 1, "title": "…", "url": "…", "source": { "id": 3, "name": "…", "active": true }, "published_at": "…|null" } ],
  "articles_truncated": false
}
```

- **Historique** : le modèle ne garde **que le dernier changement d'état** (`state_changed_at`) et la dernière évaluation de vague (`evaluated_at`) ; il n'y a pas d'historique des états, et l'API n'en invente pas.
- **Soutien** : `score` = borne basse de Wilson de la part de « more » parmi les opinions (`more` + `not_priority`), `level` = `low`/`medium`/`high` : les fonctions de `services/support.py` et `halving.py`, pas une copie. `votes_count` compte aussi « unknown ».
- **À la une** : `front.on_front` vaut `true` quand le sujet **remplit les conditions pour figurer sur la une** (même fonction `front_entry` que la page d'accueil : fenêtre d'activité, hors réserve, nombre de médias, votes ou fraîcheur, raison), **sans tenir compte du nombre d'emplacements affichés** (`limit`). `reason` est alors la raison affichée aux citoyens ; `null` (et `on_front: false`) sinon, même si les votes mériteraient une raison.
- **Votes** : totaux par choix, `voters` = comptes distincts. `daily` : votes **par jour UTC** (`date_trunc('day')` en UTC, agrégé en SQL), une entrée par jour, séries `more`/`not_priority`/`unknown` et `total`, sur les **30 derniers jours** (aujourd'hui compris) ou **depuis le jour du premier vote** si c'est plus court ; les jours sans vote valent 0 ; `[]` sans aucun vote. Les totaux, eux, portent sur tous les votes.
- **Articles** : du plus récent au plus ancien (`published_at`, sans date en dernier, puis `id`), 200 au plus ; `articles_truncated` signale la coupe (`article_count` reste le vrai nombre).

#### `GET /api/admin/topics/{id}/votes`

`page`, `page_size`. `404` si le sujet est inconnu. Trié par date décroissante (puis `id` du vote décroissant : ordre stable). Item : `{"date": "2026-11-26T10:00:00Z", "choice": "more|not_priority|unknown", "account_id": 42}`.

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
