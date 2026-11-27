# Contrat HTTP v2 — Citizen News

Contrat des routes de Citizen News V2 : chaque citoyen compose sa une de 10 sujets (poids égaux), modifiable jusqu'à 17 h ; à 17 h le serveur agrège et publie une une collective figée. Il fait foi pour le backend et le front, développés en parallèle. Produit : [citizen-news-brief-v2.md](citizen-news-brief-v2.md).

- Préfixe : `/api`. Corps et réponses en JSON (`Content-Type: application/json`).
- Authentification : cookie de session `httpOnly` (`cn_session`) posé par `POST /api/auth/verify`. Le front envoie les requêtes avec les cookies (`credentials: "include"`).
- Erreurs : `{"detail": "<message en français>"}` avec le code HTTP adapté. `429` pour la limitation de débit (en-tête `Retry-After` en secondes).
- Dates : ISO 8601 UTC (`2026-11-27T16:00:00Z`).
- **Heure de clôture** : 17:00 Europe/Paris (`EDITION_HOUR=17`, `EDITION_TIMEZONE=Europe/Paris`). `edition_date` est la date **locale** (`AAAA-MM-JJ`) du jour de la clôture ; c'est la clé de l'édition et son permalien (`/une/2026-11-27` côté front).
- **Compteurs d'approbation** : jamais dans une réponse destinée à un citoyen avant la publication (ni bassin, ni `/me/une`, ni erreur). Ils apparaissent dans l'édition publiée et dans le backoffice.
- **Remplacement net de V1** (décision de l'humain) : plus de vote, de halving, de `support`/`reason`, de `/api/topics/front`, `/api/vote/next`, `/api/votes*`, `/api/halving/config`. La migration 0009 a supprimé ces données.

**État d'implémentation** — implémenté : `GET /api/health`, les éditions publiées (`GET /api/edition/current`, `/api/editions*`), l'agrégation et la clôture (worker), l'authentification avec brouillon, le bassin (`GET /api/topics/pool`), la une personnelle (`/api/me/une*`), le calendrier d'édition, le backoffice sources et articles, `GET /api/admin/topics` (+ détail) et `GET /api/admin/stats` dans leur forme réduite décrite plus bas, la `TopicCard` V2. **Cible, à venir** (tâche suivante) : aperçu et listes d'éditions admin, `approvals`/participants admin. Les sections ci-dessous marquées « (implémenté) » le sont ; les autres décrivent la cible.

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
  "article_count": 9,
  "source_count": 5,
  "first_seen_at": "2026-11-25T18:00:00Z",
  "updated_at": "2026-11-26T09:30:00Z",
  "image_url": "https://cdn.example.org/photo.jpg"
}
```

`sources` : un média par entrée (son article le plus récent). `article_count` : tous les articles du sujet ; `source_count` : médias **distincts**. `updated_at` : dernière mise à jour du sujet (arrivée d'un article : le regroupement la recalcule à chaque rattachement, c'est la date de son article le plus récent ; test dans `test_topic_cards.py`). Plus de `support` ni de `reason`.

`image_url` : `string | null`, toujours présent. URL **https** d'une image de l'article, validée à l'ingestion : schéma https (mis en minuscules), hôte fait de lettres, chiffres, points et tirets (IDN conservé en punycode) ou IP littérale publique, port valide, sans identifiants, sans espace, caractère de contrôle, antislash ni `" ' < >`, 500 caractères au plus. Les hôtes locaux ou privés sont refusés (`localhost`, `*.localhost`, IP privées, loopback, link-local, réservées ou non spécifiées, IPv4 comme IPv6) : le navigateur du lecteur ferait la requête sur son propre réseau. Valeur : l'image de l'article le plus récent du sujet (`published_at` décroissant, les dates absentes en dernier, puis `id` décroissant ; contrairement à `sources`, `fetched_at` ne sert pas de repli) qui en a une ; `null` si aucun article n'en a.

**Hotlink uniquement** (décision de l'humain) : le serveur ne télécharge, ne copie ni ne met en cache aucune image, il ne garde que l'URL ; pas de proxy d'images. Le navigateur du lecteur charge l'image directement chez le média.

**Limites connues** : les images appartiennent aux médias (droits d'auteur des images tierces) ; charger une image depuis le média **révèle l'adresse IP du lecteur** (et son navigateur) à ce média. Pas de proxy ni de CSP dans cette version.

#### Source des images (ingestion)

Pour chaque entrée de flux, premier candidat valide parmi, dans l'ordre : `media:content` (`medium="image"` ou type `image/*`), `media:thumbnail`, enclosure de type `image/*`, première `<img src>` du contenu puis du résumé HTML. URL relative résolue contre le lien de l'article ; un candidat invalide passe au suivant, aucun ne fait échouer l'ingestion.

**Réingestion** : les articles déjà en base n'ont pas d'image. Quand un article existant a `image_url` à `NULL` et que son flux en fournit maintenant une valide, le cycle d'ingestion normal la renseigne (mise à jour de cette colonne seule : ni `topic_id`, ni `published_at`, ni regroupement). Une image déjà enregistrée n'est jamais remplacée. Les articles qui ont quitté les flux restent sans image ; il n'y a pas de commande de réingestion séparée.

## Bassin de sujets (implémenté)

### `GET /api/topics/pool?tab=random|recent|radar&seed=<chaîne>` — public

`seed` : 8 à 64 caractères `[A-Za-z0-9_-]`. Sujets du jour = au moins un article dans les `POOL_WINDOW_HOURS` dernières heures (24) **et** au moins 2 médias distincts (règle de regroupement inchangée, `min_sources_for_front`). Réponse (plafond 300 items, pas de pagination) :

```json
{ "edition_date": "2026-11-27", "closes_at": "2026-11-27T16:00:00Z", "open": true, "total": 42, "items": [ { /* TopicCard */ } ] }
```

- `random` (défaut) : tri par `sha256(seed + ":" + topic_id)` (stable pour une même graine, différent d'une graine à l'autre, sans pondération). `seed` **obligatoire** pour `random` (`422` sinon). Le **client** garde la graine (stockage du navigateur, une par session de navigation) et la liste des sujets déjà vus : il présente d'abord les vus dans l'ordre de passage, puis les non vus dans l'ordre du serveur ; un nouveau sujet s'insère ainsi au hasard parmi les non vus.
- `recent` : `updated_at` décroissant, puis `id` décroissant.
- `radar` : sujets du bassin avec `source_count <= RADAR_MAX_SOURCES` (3), même ordre que `recent`. Seule la faible couverture médiatique compte.

Les sujets déjà dans la une de l'utilisateur restent dans la liste (le client les marque « Dans ma une »). Aucun compteur d'approbation.

Précisions : `total` = nombre de sujets de l'onglet (`items` est plafonné à 300) ; `edition_date`, `closes_at` et `open` sont ceux de la une en cours (voir ci-dessous). `seed` invalide ou `tab` inconnu → `422`. Réponse `Cache-Control: no-store` (elle dépend de la graine et de l'heure). Un article compte pour la fenêtre par sa date `published_at`, à défaut `fetched_at`.

**Calendrier de l'édition.** Avant la clôture d'un jour sans édition publiée : `edition_date` = jour local, `open: true`. Dès l'heure de clôture sans édition publiée : même `edition_date`, `open: false` (période de publication, même si le worker est en retard). Une fois l'édition du jour local publiée : `edition_date` = lendemain, `open: true`, `closes_at` = demain 17:00 locale. 17:00 Paris = 15:00 UTC l'été, 16:00 UTC l'hiver.

## Une personnelle (implémenté)

Session citoyenne requise (`cn_session`), `401` sinon. La une est celle de l'édition en cours (`edition_date` ci-dessus). Un compte = une une par `edition_date` (unicité en base : `selections`). 10 places au plus, sans ordre ni poids, moins de 10 autorisé.

Corps commun (« une ») : `{ "edition_date": "2026-11-27", "closes_at": "2026-11-27T16:00:00Z", "open": true, "topic_ids": [12, 7] }` (ordre d'ajout, sans compteur).

| Route | Effet |
|---|---|
| `GET /api/me/une` | `200` → une |
| `PUT /api/me/une` `{"topic_ids": [...]}` | remplace toute la une (dédoublonnés, ≤ 10 après dédoublonnage, sujets existants — le bassin n'est pas exigé ici) ; plus de 10, identifiant invalide ou sujet inconnu → `422` · `200` → une |
| `PUT /api/me/une/topics/{id}` | ajoute un sujet (idempotent, même hors bassin s'il est déjà dans la une) ; une pleine → `409 "Votre une est complète"` ; sujet inconnu → `404` ; sujet existant mais hors bassin → `422 "Ce sujet n'est plus au bassin du jour"` · `200` → une |
| `DELETE /api/me/une/topics/{id}` | retire (idempotent) · `200` → une |
| `POST /api/me/une/merge` `{"topic_ids": [...]}` | fusionne sans écraser : l'existant reste, les nouveaux s'ajoutent jusqu'à 10 places, sujets inconnus ou hors bassin ignorés (ainsi que ceux qui ne tiennent plus dans les 10 places : ils comptent dans `ignored` ; un sujet déjà présent n'est ni ajouté ni ignoré) ; plus de 10 identifiants distincts → `422` · `200` → `{"added": 2, "ignored": 1, "une": {…}}` |

Toute écriture : `409 {"detail": "La clôture est passée, la une du jour n'est plus modifiable"}` si `open` est faux. `open` est faux dès l'heure de clôture, même si le worker est en retard ; il redevient vrai (pour l'édition suivante, une vide) quand l'édition du jour est publiée.

**Édition ciblée en cas de retard.** `edition_state` cible la plus ancienne clôture **due non publiée** tant qu'elle existe : `open: false`, ses unes enregistrées restent lisibles (`GET /api/me/une`) et aucune écriture n'est possible, même si le retard dépasse minuit ou dure plusieurs jours ; l'édition suivante s'ouvre une fois celle-ci publiée. Une date due n'est « en attente » que s'il existe déjà une édition publiée plus ancienne (tous les jours après la dernière édition publiée, dont la clôture est passée) ou, avant toute édition, si des unes sont enregistrées pour cette date (pas d'édition fantôme au premier lancement : sans cela on cible la prochaine clôture, comme aujourd'hui). `services/edition_calendar.pending_editions(session, now)` expose ces dates dues non publiées (la plus ancienne d'abord) pour `close_due_edition`.

**Clôture et sujets hors bassin.** `PUT /api/me/une` accepte des sujets existants hors bassin, mais la clôture ne compte que les sujets qui passent `eligible_pool` **au moment de la clôture** : les autres restent dans la une du citoyen sans rien totaliser. Les articles datés de plus d'1 h dans le futur sont ignorés pour la fenêtre du bassin. Limitation de débit sur les écritures (par compte, `429` avec `Retry-After` ; `RATE_LIMIT_UNE_WRITES_PER_ACCOUNT` par `RATE_LIMIT_UNE_WINDOW_SECONDS`, 60 par minute par défaut ; la lecture n'est pas limitée). Les écritures d'un même compte sont sérialisées (verrou sur le compte) : la limite de 10 ne peut pas être dépassée par des requêtes simultanées. Réponses `Cache-Control: no-store`. Les identifiants de `topic_ids` sont des entiers positifs (`422` sinon).

## Éditions publiées (implémenté)

Édition :

```json
{ "date": "2026-11-26", "published_at": "2026-11-26T16:00:03Z", "participants": 120,
  "topics": [ { "rank": 1, "topic_id": 12, "title": "…", "summary": "…",
                "sources": [ { "name": "…", "url": "…", "title": "…", "published_at": "…" } ],
                "source_count": 5, "article_count": 9, "approvals": 80, "proportion": 0.667, "image_url": "https://…" } ] }
```

Capture **figée** (titre, résumé, sources, nombre de médias… copiés à la clôture, ne changent plus ; `topic_id` vaut `null` si le sujet a été supprimé depuis). 0 à 10 `topics` : seuls les sujets avec ≥ 1 approbation. `proportion = approbations / participants` ; arrondie à 3 décimales dans les réponses (valeur exacte conservée en base ;) `participants` = nombre de comptes ayant enregistré une une **non vide**. Sans participants, l'édition est publiée quand même (`topics: []`, `participants: 0`).

| Route | Réponse |
|---|---|
| `GET /api/edition/current` — public | `{ "edition": Édition \| null, "next_close_at": "…Z", "server_time": "…Z" }` (`null` avant la première édition ; `next_close_at` = prochaine heure de clôture strictement après `server_time`, même si le worker est en retard ; `Cache-Control: no-store`) |
| `GET /api/editions/{date}` — public | Édition · `404 {"detail": "Édition introuvable."}` (permalien stable) · date mal formée `422` · `Cache-Control: public, max-age=30` |
| `GET /api/editions?limit=30` — public | `limit` 1–100 · `{ "items": [ {"date", "published_at", "participants", "topic_count"} ] }`, plus récentes d'abord · `Cache-Control: public, max-age=30` |

## Agrégation et clôture (implémenté)

**Agrégation** — une seule fonction, `aggregate(session, edition_date, now)` : score d'un sujet = nombre de comptes l'ayant dans leur une ; seuls les sujets éligibles à la clôture comptent (bassin) ; égalités départagées par `source_count` décroissant, puis `updated_at` le plus récent, puis `id` croissant (déterministe) ; les 10 premiers (score ≥ 1) forment la une ; rangs 11–20 pour l'aperçu admin. Elle rend le classement complet, les participants, les groupes d'égalité et le critère qui a départagé. La clôture **et** l'aperçu admin appellent exactement cette fonction.

`aggregate(session, edition_date, now, *, top=10, extra=10)` (`app/services/aggregation.py`) n'écrit rien et rend un `Aggregation` (dataclasses) : `participants`, `ranking` (tous les sujets de score ≥ 1, `RankedTopic` : `rank`, `topic_id`, `score`, `proportion` = score / participants, données de publication captées — titre, résumé, sources, `source_count`, `article_count`, `image_url`, `updated_at` —, `tied_with`, `broken_by`), `topics` (rangs 1–`top`), `next` (rangs suivants, `extra`) et `ties` (`TieGroup` : `approvals`, `topic_ids`, `broken_by`, `crosses_cut`). `broken_by` d'un groupe d'égalité = le critère le plus profond nécessaire pour ordonner tout le groupe (`source_count` < `updated_at` < `id`) ; `crosses_cut` = le groupe a des sujets dans la une et hors de la une (coupure 10/11). Nombre de requêtes constant (participants, bassin, scores, sujets, cartes). Les participants sont les comptes ayant au moins un sujet dans leur une du jour, sujets hors bassin compris.

**Clôture** — `close_due_edition(session, now)`, appelée par le worker (`python -m app.cli run`, vérification **chaque minute**, tick séparé de l'ingestion de 15 min) : au premier passage après l'heure locale de clôture, s'il n'existe pas d'édition pour `edition_date`, agrège et publie. Idempotente et atomique (une transaction ; verrou advisory ou contrainte unique sur `editions.edition_date` : deux workers simultanés → une seule édition). Rattrape un retard (worker arrêté des heures ou des jours : publie l'édition du jour dû, une seule, la plus récente due, pas d'éditions fantômes). Horloge injectable (`now`) ; tests à l'heure d'été (17:00 locale = 15:00 UTC l'été, 16:00 UTC l'hiver).

Détails d'implémentation (`app/services/edition_close.py`) : `pending_editions` donne les dates dues ; seule la plus récente est publiée (les jours manqués avant elle ne produisent rien, et le calendrier passe à la suite car il s'appuie sur la dernière édition publiée). Verrou `pg_advisory_xact_lock` puis nouvelle vérification sous verrou ; la contrainte unique `editions.edition_date` est le filet (conflit = pas de seconde édition). L'édition et ses `edition_topics` s'insèrent dans une seule transaction (échec = rien de publié, le tick suivant réessaie). `published_at` = l'horloge `now` du tick. Après publication, l'ingestion peut modifier les sujets : l'édition ne change plus. Course à 17 h : toute écriture de une (`PUT`, `PUT/DELETE topics`, `merge`, fusion du brouillon à la vérification) prend d'abord `pg_advisory_xact_lock_shared` sur la même clé que la clôture (exclusive), puis lit l'état de l'édition, puis verrouille la ligne du compte (ordre fixe, pas d'interblocage). Une écriture en vol fait attendre la clôture, donc elle est comptée ; une écriture qui démarre pendant la clôture attend, voit l'édition publiée et écrit sur le lendemain. Le verrou ne dure que la courte transaction de l'écriture. Participants et scores sont lus dans une seule requête (un seul instantané) : jamais de `proportion` > 1, même pour l'aperçu.

## Authentification (lien magique) (implémenté, brouillon compris)

### `POST /api/auth/magic-link`

Requête : `{"email": "a@example.org", "draft": {"topic_ids": [12, 7]}}` — `draft` optionnel (≤ 10 sujets, `422` au-delà ; dédoublonné et validé côté serveur).

Le serveur garde le brouillon **avec le jeton** (jamais dans l'URL ; supprimé quand le jeton est consommé ou purgé : colonne `login_tokens.draft`).

- `202` **toujours** (identique avec ou sans brouillon) (corps `{}`), que le compte existe ou non, sans révéler l'un ou l'autre. Un compte est créé à la vérification du premier lien.
- `422` e-mail mal formé · `429` limitation de débit.

### `POST /api/auth/verify`

Requête : `{"token": "…"}` (jeton à usage unique, durée de vie limitée).

- `200` → `{"email": "a@example.org", "draft": {"added": 2, "ignored": 1} | null}` : si l'édition est ouverte et qu'un brouillon est attaché, il est fusionné (règle de `/api/me/une/merge`) dans la une du compte, même si le navigateur est différent ; édition fermée → brouillon ignoré, `draft: null`. Si la fusion échoue (panne), la connexion réussit quand même avec `draft: {"added": 0, "ignored": n}`. En-tête `Set-Cookie` de session `httpOnly` (`SameSite=Lax`, `Secure` hors développement).
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

**Suppression** : les articles partent en cascade, l'URL est mémorisée dans `deleted_sources` pour que l'initialisation depuis `feeds.yaml` ne recrée pas la source. Un sujet qui perd des articles n'est pas supprimé (ses sélections et ses éditions publiées sont conservées) : s'il lui reste moins de médias distincts que le minimum pour le bassin, ou plus aucun article, il n'en fait plus partie ; son titre et son résumé ne changent qu'au prochain regroupement qui lui rattache un article : un sujet mixte garde donc, après la suppression, un titre calculé avec l'ancien article.

### Statistiques (`GET /api/admin/stats`)

Page d'accueil du backoffice. Derrière la session admin (`401` sinon, y compris avec une session citoyenne). **Comptes agrégés uniquement** : ni identifiant de compte, ni adresse. Réponse **actuelle** (articles seulement) :

```json
{
  "last_24h": {"articles": 12},
  "total":    {"articles": 1830},
  "series": [{"date": "2026-10-29", "articles": 7}, …]
}
```

**Cible V2** (tâche admin à venir) : `participants` et `unes` (unes enregistrées) s'ajoutent à `last_24h`, `total` et à chaque point de `series`, à la place des votes et votants V1.

- **Fenêtre « 24 h »** : glissante, `[maintenant − 24 h, maintenant]` (bornes incluses), horloge du serveur (injectable dans les tests).
- **Articles** : comptés selon la date d'**ingestion** (`articles.fetched_at`, posée à l'insertion, jamais modifiée), pas la date de publication.
- **`series`** : exactement 30 entrées, un jour UTC chacune, de J−29 à aujourd'hui **compris** (aujourd'hui est une journée UTC partielle), ordre croissant, jours vides à `0`. Les éléments plus anciens ne figurent pas dans la série mais sont comptés dans `total`.
- Calculé en base par des requêtes agrégées (nombre constant, quel que soit le volume) ; index `ix_articles_fetched_at` (migration 0008).

### Articles et sujets (lecture seule)

Routes sous `/api/admin`, toutes derrière la session admin (`401` sinon, y compris avec une session citoyenne). **Aucune réponse ne contient d'adresse e-mail, de hash ni de donnée personnelle** (un test parcourt les réponses et échoue si une adresse y apparaît).

**Pagination** (`/articles`, `/topics`) : `page` (≥ 1, 100 000 au plus, défaut 1) et `page_size` (1 à 200, défaut 50) ; hors bornes → `422`. Réponse `{"items": […], "total": <n>, "page": <p>, "page_size": <s>}`. Une page au-delà de la dernière répond `200` avec `items: []` et le vrai `total`. Pagination et tri sont faits par le serveur (`LIMIT/OFFSET` + un `COUNT`), jamais en mémoire. Tout paramètre invalide → `422 {"detail": "Requête invalide (champ : …)"}` (ou un message précis pour les dates).

**Tri** : `sort` et `order` (`asc`/`desc`) sont des listes blanches strictes (`422` sinon) ; l'`ORDER BY` vient d'une table fermée du serveur, jamais de l'entrée. Ordre total : l'`id` départage les égalités (même sens que `order`) ; les valeurs absentes (article sans date, article non regroupé) viennent **toujours en dernier**, dans les deux sens.

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

Paramètres : `page`, `page_size`, `sort` = `updated` (défaut, `updated_at`) | `title` | `articles` ; `order` (défaut `desc`). Item :

```json
{ "id": 7, "title": "Retraites", "updated_at": "2026-11-26T09:30:00Z", "article_count": 5, "source_count": 3, "image_url": "https://…" }
```

`source_count` : médias distincts. `image_url` : image du plus récent article qui en a une (comme les cartes citoyennes), ou `null`. Agrégats calculés par le SQL de la page (deux requêtes avec le `COUNT`). Plus de `state`, `wave`, `vote_count` ni de filtre `state` (V1). **Cible V2** : un champ `approvals` (approbations de l'édition en cours) s'ajoute avec la tâche admin.

#### `GET /api/admin/topics/{id}`

`404 {"detail": "Sujet introuvable."}` si inconnu. Sinon :

```json
{
  "id": 7, "title": "…", "summary": "…",
  "first_seen_at": "…", "updated_at": "…",
  "article_count": 5, "source_count": 3,
  "articles": [ { "id": 1, "title": "…", "url": "…", "source": { "id": 3, "name": "…", "active": true }, "published_at": "…|null" } ],
  "articles_truncated": false
}
```

- **Articles** : du plus récent au plus ancien (`published_at`, sans date en dernier, puis `id`), 200 au plus ; `articles_truncated` signale la coupe (`article_count` reste le vrai nombre).
- **Cible V2** : `approvals` courant et historique par édition s'ajoutent avec la tâche admin.

### Éditions (cible V2, tâche admin à venir)

| Route | Réponse |
|---|---|
| `GET /api/admin/edition/preview` | `{ "computed_at", "edition_date", "participants", "topics": [ItemAdmin ×≤10], "next": [ItemAdmin rangs 11–20], "ties": [{"approvals": 12, "topic_ids": [3, 9], "broken_by": "source_count\|updated_at\|id", "crosses_cut": true}] }`. Ne publie rien, ne fige rien, n'écrit rien (appelle `aggregate`). |
| `GET /api/admin/editions` | liste `{date, published_at, participants, topic_count}` |
| `GET /api/admin/editions/{date}` | édition avec approbations |

`ItemAdmin` : `{ "rank", "topic_id", "title", "approvals", "proportion", "source_count", "article_count", "updated_at", "tied_with": [ids], "broken_by": null | "source_count" | "updated_at" | "id" }`. Jamais d'e-mail dans les réponses admin.

## Santé (implémenté)

### `GET /api/health`

- `200` → `{"status": "ok"}` si la base répond.
- `503` → `{"detail": "Base de données indisponible"}`.
