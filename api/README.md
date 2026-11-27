# API Citizen News

Backend FastAPI + PostgreSQL. Contrat HTTP : [`docs/api-contract.md`](../docs/api-contract.md). Lancement et variables d'environnement : [README racine](../README.md). Tests : [section Tests](#tests).

## Alimentation en sujets

```
flux RSS ──ingest──▶ articles ──cluster──▶ topics ◀──halve── votes
                                              └──▶ GET /api/topics/front, GET /api/vote/next
```

### Commandes

Dans le conteneur (le service `worker` du compose les lance en boucle) :

```bash
docker compose run --rm api python -m app.cli ingest    # récupère les flux de config/feeds.yaml
docker compose run --rm api python -m app.cli cluster   # regroupe les articles en sujets
docker compose run --rm api python -m app.cli halve     # recalcule état et vague des sujets d'après les votes
docker compose run --rm api python -m app.cli refresh   # ingest, cluster puis halve
docker compose run --rm api python -m app.cli run --interval-minutes 15   # refresh en boucle
```

Le service `worker` exécute `run`. Intervalle : variable `INGEST_INTERVAL_MINUTES` (défaut 15). Un flux en erreur (réseau, 404, XML invalide) est consigné dans les logs et n'arrête pas les autres ; `ingest` ne retourne un code d'erreur que si **aucun** flux n'a pu être lu. `halve` n'a besoin d'aucun accès réseau. Toutes les commandes sont idempotentes : les relancer ne duplique rien.

### `config/feeds.yaml`

Une entrée par média : `name` et `feed_url`. Chargement validé (`config/feeds.py`) : URL `http(s)` valide, doublons de nom ou d'URL refusés, champs inconnus refusés. **Ce fichier ne sert qu'à initialiser la base.** La base (`media_sources`) est la référence, gérée depuis /admin (onglet Sources) : à chaque `ingest`, `sync_sources` n'ajoute que les flux du YAML qui manquent (clé : `feed_url`). Elle ne renomme jamais une source existante, ne réactive jamais une source désactivée et ne recrée jamais une source supprimée définitivement (table `deleted_sources`). Modifier un nom dans le YAML n'a donc aucun effet sur une source déjà en base ; retirer un flux du YAML ne le retire pas de la base.

La liste de départ compte 12 médias ; les URL ont été vérifiées le 26/11/2026. Les Echos (403/503 pour un client automatique) n'est pas inclus. Les articles sont dédupliqués par URL ; le résumé est nettoyé du HTML.

### `config/clustering.yaml`

| Paramètre | Défaut | Effet |
|---|---|---|
| `similarity_threshold` | 0.35 | Similarité cosinus minimale (entre 0 et 1, exclus) pour rattacher un article à un sujet existant. |
| `window_hours` | 48 | Fenêtre de temps : seuls les articles publiés dans la fenêtre sont regroupés, et un sujet sans nouvel article depuis plus longtemps n'accepte plus de rattachement. La une et `vote/next` ne montrent que les sujets actifs dans cette fenêtre. |
| `min_sources_for_front` | 2 | Nombre de **médias distincts** minimal pour qu'un sujet soit visible. Plusieurs articles d'un même média comptent pour une seule source. |

#### Comment ça marche

Chaque article devient un vecteur TF-IDF : le titre compte 3 fois (il est répété avant le résumé), les accents et la casse sont normalisés (« Élysée » = « elysee »), les mots vides français sont ignorés. Les articles non rattachés sont traités du plus ancien au plus récent : chacun rejoint le sujet dont le centroïde est le plus proche si la similarité atteint le seuil, sinon il crée un sujet (`state=new`, `wave=0`). Un article déjà rattaché n'est jamais déplacé, d'où l'idempotence.

Le titre du sujet est celui de l'article le plus représentatif (le plus proche du centroïde ; à 0,01 près, le plus court) et le résumé est celui du même article, tronqué à ~280 caractères. `first_seen_at` et `updated_at` sont la date du plus ancien et du plus récent article du sujet.

#### Choisir le seuil

- Trop **bas** : des sujets distincts fusionnent (le même ministre dans deux affaires différentes).
- Trop **haut** : un même événement reste éclaté en plusieurs sujets à une seule source, donc invisible.
- Méthode : lancer `refresh` sur une base vide, parcourir `GET /api/topics/front?limit=50` et repérer, d'une part, les sujets qui mélangent des articles sans rapport (monter le seuil), d'autre part les doublons évidents entre sujets (baisser le seuil). Sur les vrais flux (~350 articles), 0,35 regroupe correctement les articles d'un même événement (10 médias sur une même affaire judiciaire) sans fusion abusive observée.
- Le TF-IDF est réajusté à chaque exécution sur les articles de la fenêtre (les poids IDF varient donc d'un run à l'autre) ; le résultat reste déterministe pour un état de base et une date donnés. Un article déjà rattaché n'est jamais réévalué : **changer le seuil ne recalcule pas l'existant** et ne vaut que pour les nouveaux articles.
- Après changement, repartir d'une base vide (`docker compose down -v`) : les rattachements existants ne sont pas recalculés.

### Endpoints

- `GET /api/topics/front?limit=10` : la une citoyenne (`limit` 1–50, défaut 10 ; réponse `{items, has_more}`, `has_more` vrai s'il reste des sujets classés au-delà de `limit` ; le front « Voir plus » redemande avec un `limit` croissant, sans offset : voir [`docs/api-contract.md`](../docs/api-contract.md)). Sujets actifs dans la fenêtre, hors `reserve`, avec au moins `min_sources_for_front` médias distincts **ou** la raison `under_the_radar`, et au moins `ranking.min_votes` votes ou récents ; classés par un mélange du score collectif et de la fraîcheur ; chaque carte a un `support` (`level`, `votes_count`) et une `reason` réels. Réponse mise en cache 5 secondes ; 4 requêtes SQL au plus. Règles et seuils : [`docs/halving.md`](../docs/halving.md) et `config/front.yaml`.
- `GET /api/vote/next?count=10&seen=1,2` : flux de vote piloté par le halving (nouveaux, repêchage, actifs, proches de l'émergence ; voir [`docs/halving.md`](../docs/halving.md)), hors `seen` et, avec une session, hors sujets déjà votés ; sans `support` ni `reason` ni compteur. Utilisable sans compte.
- `POST /api/votes {topic_id, choice}` (session) : voir « Votes » ci-dessous. `GET /api/halving/config` : paramètres du halving et leur description française (public).

## Votes et Successive Halving

`POST /api/votes` : un vote par compte et par sujet (`UNIQUE(account_id, topic_id)`), modifiable : un `INSERT … ON CONFLICT DO UPDATE` remplace le choix et met `updated_at` à jour. Réponse `{topic_id, choice}` et rien d'autre (résultats masqués avant le vote). `401` sans session, `404` sujet inconnu, `422` choix invalide, `429` + `Retry-After` au-delà de `RATE_LIMIT_VOTE_PER_ACCOUNT` votes (120) par `RATE_LIMIT_VOTE_WINDOW_SECONDS` (60 s) et par compte.

Le **halving** (`app/services/halving.py`, fonction pure `decide` + `halve` qui écrit en base) tourne dans le worker, jamais dans la requête de vote : `python -m app.cli halve`, lancé aussi à chaque cycle `refresh`. Idempotent et déterministe. Il met à jour `topics.state`, `topics.wave`, `state_changed_at`, `evaluated_at`, `votes_at_eval` ; **jamais `updated_at`**, qui reste la date du dernier article (le modèle n'a plus d'`onupdate` sur cette colonne ; un test le garantit). Algorithme complet, exemple chiffré et paramètres : [`docs/halving.md`](../docs/halving.md).

### Données de démonstration

```bash
docker compose run --rm -e DEMO_SEED=true api python -m app.cli seed-demo [--seed 1]
```

Crée des sujets « [Démo] … », trois médias fictifs, 120 comptes `demo-N@demo.invalid` et leurs votes (profils : priorité commune, mobilisation, sous les radars, émergent, peu soutenu, nouveau), puis lance le halving. Relancer remplace les données de démo. Refusé sans `DEMO_SEED=true` et avec `COOKIE_SECURE=true`.

## Comptes et sessions

Flux (détail des routes dans le [contrat](../docs/api-contract.md)) :

```
POST /api/auth/magic-link ─▶ login_tokens (hash) ─▶ e-mail {APP_BASE_URL}/connexion?token=…
POST /api/auth/verify     ─▶ jeton consommé, compte créé au 1er usage ─▶ sessions (hash) + cookie cn_session
GET /api/me · POST /api/auth/logout · POST /api/votes/claim · GET /api/votes/mine   (cookie requis)
```

- **Jetons** : `secrets.token_urlsafe(32)`, stockés uniquement hachés (SHA-256) : lien magique dans `login_tokens` (expire après `LOGIN_TOKEN_TTL_MINUTES`, usage unique consommé par un `UPDATE … WHERE used_at IS NULL` atomique), session dans `sessions` (`SESSION_TTL_DAYS`). Pas de JWT : la déconnexion révoque la session côté serveur. Jetons expirés ou utilisés et sessions expirées sont purgés à chaque demande de lien et à chaque vérification (au bout d'un jour pour les jetons).
- **Cookie** `cn_session` : `httpOnly`, `SameSite=Lax`, `Secure` si `COOKIE_SECURE=true`, `Max-Age` = durée de session.
- **Pas d'énumération** : `magic-link` répond `202 {}` dans tous les cas (l'e-mail est envoyé aussi pour une adresse inconnue : le compte n'est créé qu'à la vérification) ; l'échec d'envoi n'est pas visible de l'appelant. `verify` répond `400` au message unique « Lien de connexion invalide ou expiré » (inconnu, expiré ou déjà utilisé).
- **Données personnelles** : `accounts` ne contient que l'e-mail et la date de création. Aucune IP en base ; le limiteur de débit les garde en mémoire, le temps de la fenêtre. L'e-mail dans `login_tokens` est supprimé un jour après expiration ou usage.
- **Protéger une route** : `account: Account = Depends(current_account)` (`app/deps.py`) ; `401 {"detail": "Authentification requise"}` sans session valide.

### Backoffice (`/api/admin`)

- Mot de passe unique `ADMIN_PASSWORD` (comparaison en temps constant ; `SecretStr`, jamais journalisé). Refus de démarrer avec le défaut de développement si `COOKIE_SECURE=true`, avertissement au démarrage sinon.
- `POST /api/admin/login` → cookie `cn_admin` (`httpOnly`, `SameSite=Lax`, `Secure` selon `COOKIE_SECURE`, `Path=/api/admin`, 8 h) ; session hachée dans `admin_sessions`, purgée à l'expiration lors d'un login. Limite par IP : `RATE_LIMIT_ADMIN_LOGIN_PER_IP` / `RATE_LIMIT_ADMIN_LOGIN_WINDOW_SECONDS`.
- **Sources** (`app/services/sources.py`, routes `/api/admin/sources`, contrat dans `docs/api-contract.md`) : `media_sources.active` ; l'ingestion ne lit que les sources actives. Désactiver garde les articles et les sujets (historique conservé : le regroupement, la une et les votes ne filtrent pas sur `active`). Supprimer est définitif et exige `?confirm=<nombre d'articles>` ; les articles partent en cascade, l'URL est inscrite dans `deleted_sources`. Un sujet qui perd tous ses articles reste en base (ses votes aussi) mais n'est plus éligible nulle part.
- **Articles, sujets, votes** (`app/services/admin_articles.py`, `admin_topics.py`, contrat dans `docs/api-contract.md`) : lecture seule, pagination et tri côté serveur (`ORDER BY` pris dans une table fermée, jamais dans l'entrée ; `id` en départage), pas de N+1 (jointures, agrégats en sous-requêtes ; des tests comptent les requêtes). Le détail d'un sujet réutilise `support.py` (score, niveau) et `front.front_entry` (la décision de la une, extraite de `front_topics` : une seule règle pour la une et pour l'admin). Jamais d'adresse e-mail dans une réponse admin : un vote expose le numéro de compte. Migration 0007 : index `articles.source_id` (filtre par source, cascade à la suppression d'une source) ; `published_at`, `topic_id` (articles) et `topic_id` (votes) étaient déjà indexés.
- **Statistiques** (`app/services/admin_stats.py`, `GET /api/admin/stats`, contrat dans `docs/api-contract.md`) : accueil du backoffice. 24 h glissantes et total (articles par date d'ingestion `fetched_at`, votes par `created_at`, votants distincts), série de 30 jours UTC (jours vides à 0 ; les votants par jour ne se cumulent pas). 4 requêtes agrégées, nombre constant (un test le vérifie) ; les helpers de jours UTC viennent d'`admin_topics`. Migration 0008 : index `articles.fetched_at` et `votes.created_at` (fenêtres de 24 h et de 30 jours sans parcourir toute la table ; les totaux restent un comptage complet).
- **Garde SSRF** (`app/services/safe_fetch.py`) : l'URL d'une nouvelle source est récupérée par le serveur ; hôte public seulement (logique partagée avec `images.py`), toutes les adresses résolues vérifiées, connexion à l'IP validée (DNS rebinding), redirections suivies à la main (5) et revérifiées, 10 s, 5 Mo, proxys d'environnement ignorés, un seul message d'erreur générique. L'ingestion périodique passe par la même garde (`ingest()` appelle `fetch_public` pour chaque flux, ceux de `feeds.yaml` compris) : une source qui redirige plus tard vers une adresse interne, ou dont le DNS change, est refusée et son erreur reste isolée. **Limite** : `getaddrinfo` n'a pas de délai propre, le délai de 10 s n'est vérifié qu'entre les étapes : un serveur DNS qui ne répond pas peut retenir une requête plus longtemps. URL de flux normalisées (schéma et hôte en minuscules, sans fragment) partout où elles sont stockées ou comparées (formulaire, `feeds.yaml`, `deleted_sources`) ; `sync_sources` et la suppression se sérialisent par un verrou consultatif PostgreSQL et l'insertion de départ est un seul `INSERT … WHERE NOT EXISTS (deleted_sources)`.
- **Ajouter une route admin** : l'écrire sur `admin.protected` (`app/routers/admin.py`) : `require_admin` (`app/deps.py`) s'applique à tout le routeur, rien à déclarer par route. Les réponses `/api/admin/*` portent `Cache-Control: no-store` et `X-Robots-Tag: noindex` (middleware de `main.py`).

### E-mail

`app/services/mailer.py` : interface `Mailer.send(to, subject, body)`, deux implémentations choisies par `MAIL_BACKEND`. `smtp` : `smtplib`, `SMTP_HOST` obligatoire (l'application refuse de démarrer sans), STARTTLS par défaut, authentification si `SMTP_USER` est défini. `console` : écrit le message (lien compris) dans le logger `app.mail` : développement seulement. L'envoi se fait après la réponse (`BackgroundTasks`) ; un échec est journalisé sans adresse ni lien.

### Limitation de débit

`app/services/ratelimit.py` : fenêtre glissante en mémoire (interface `RateLimiter`, horloge injectable), **par processus API** (plusieurs processus multiplient la limite ; brancher un stockage partagé derrière l'interface si besoin). Au-delà : `429 {"detail": …}` et en-tête `Retry-After` (secondes).

| Route | Clé | Variable (défaut) |
|---|---|---|
| `POST /api/auth/magic-link` | IP | `RATE_LIMIT_MAGIC_LINK_PER_IP` (20) |
| `POST /api/auth/magic-link` | e-mail normalisé (haché en mémoire) | `RATE_LIMIT_MAGIC_LINK_PER_EMAIL` (5) |
| `POST /api/auth/verify` | IP | `RATE_LIMIT_VERIFY_PER_IP` (30) |
| `POST /api/votes/claim` | compte | `RATE_LIMIT_CLAIM_PER_ACCOUNT` (30) |
| `POST /api/votes` | compte | `RATE_LIMIT_VOTE_PER_ACCOUNT` (120) |

Fenêtre : `RATE_LIMIT_WINDOW_SECONDS` (3600) ; pour les votes directs, `RATE_LIMIT_VOTE_WINDOW_SECONDS` (60). Ces variables sont transmises à l'API par le compose.

**Limites connues** : la limite par e-mail est aussi un verrou. Quelqu'un qui connaît l'adresse d'une victime peut épuiser ses 5 demandes et l'empêcher de recevoir un lien pendant une heure (compromis assumé : sans cela, l'API servirait à inonder une boîte de courriels). Derrière un reverse proxy **sans** `TRUST_PROXY=true`, tous les clients partagent l'IP du proxy et donc la limite par IP (20/h) : un seul abus bloque tout le monde ; avec `TRUST_PROXY=true`, la limite redevient individuelle. L'IP est celle de la connexion ; avec `TRUST_PROXY=true`, c'est la **dernière** entrée de `X-Forwarded-For` (celle qu'ajoute le proxy de confiance : les entrées précédentes sont falsifiables). N'activez `TRUST_PROXY` que derrière un proxy qui écrase ou complète cet en-tête, sinon n'importe qui contourne la limite.

### Votes anonymes

Les votes faits sans compte restent dans le navigateur : rien n'est stocké côté serveur avant `claim`, donc ils ne comptent pas dans le classement. `POST /api/votes/claim {votes:[{topic_id,choice}]}` : un vote déjà présent sur le sujet n'est jamais écrasé (contrainte `UNIQUE(account_id, topic_id)` + `ON CONFLICT DO NOTHING`), les sujets inconnus sont ignorés, un sujet répété dans le lot compte une fois (le premier gagne), `claimed` est le nombre de votes réellement créés. Un lot de plus de `CLAIM_MAX_VOTES` (200, au plus 1000) votes est refusé en `422` (rien n'est enregistré) ; au-delà de 1000, le refus intervient dès la lecture de la requête.

Toute erreur de validation (`422`) renvoie `{"detail": "Requête invalide (champ : …)"}` comme le contrat le demande.

### Code

```
app/cli.py                  ingest / cluster / halve / refresh / run / seed-demo
app/services/ingest.py      récupération (httpx), parsing (feedparser), upsert
app/services/clustering.py  TF-IDF + similarité cosinus
app/services/topics.py      éligibilité des sujets, construction des TopicCard
app/services/halving.py     Successive Halving (score, vagues, états)
app/services/voteflow.py    sélection du flux de vote
app/services/support.py     niveau de soutien et raison d'une carte
app/services/front.py       éligibilité et classement de la une
app/services/demo.py        données fictives (seed-demo)
app/routers/topics.py       /api/topics/front, /api/vote/next
app/routers/auth.py         /api/auth/*, /api/me
app/routers/votes.py        /api/votes, /api/votes/claim, /api/votes/mine
app/routers/halving.py      /api/halving/config
app/services/auth.py        jetons, comptes, sessions
app/services/mailer.py      Mailer (SMTP, console)
app/services/ratelimit.py   limitation de débit
app/deps.py                 current_account, IP cliente
config/feeds.py, clustering.py, halving.py, front.py   chargeurs validés
tests/fixtures/             flux RSS d'exemple (aucun accès réseau dans les tests)
```

## Tests

```bash
scripts/test-api.sh                         # depuis la racine du dépôt : build si besoin, Postgres léger, pytest, arrêt de Postgres
scripts/test-api.sh tests/test_auth.py      # un fichier ; les arguments vont à pytest (-k, -x, …)
# équivalent sans le script :
docker compose --profile test run --rm api-test pytest -q [tests/test_auth.py]
docker compose --profile test rm -sf db-test   # arrêter Postgres ensuite
```

- Cible `test` du `api/Dockerfile` (l'image `api`, utilisée par `api` et `worker`, n'a pas pytest). Le code (`./api`) est monté en **lecture seule** sur `/srv/api` : modifier le code ne demande aucun rebuild ; seul un changement de `pyproject.toml` ou de `constraints.txt` réinstalle les dépendances.
- `db-test` : `postgres:16` (même image que `db`), `shared_buffers=16MB`, `max_connections=30`, `fsync=off`, données en tmpfs ; environ 50 Mio au repos. Il n'est lancé que par le profil `test` et ne touche pas au volume `pgdata`.
- Dépendances : roues précompilées seulement (`pip install --only-binary=:all: --no-cache-dir`), versions exactes dans `constraints.txt` (transitives comprises, pytest compris). numpy, scipy et scikit-learn sont **indispensables** : `app/services/clustering.py` les importe et l'API les charge au démarrage ; ils pèsent l'essentiel de l'image (≈ 380 Mio installés).
- Image de base : `python:3.12-slim` + roues précompilées, plutôt qu'une image publique contenant déjà numpy/scipy/scikit-learn (comparaison sur les tailles publiées, 2026-11-26) : il n'existe pas d'image officielle avec ces paquets ; `jupyter/scipy-notebook` fait ≈ 1,25 Go compressé et ses tags récents sont en Python 3.11 ; les autres images « scikit-learn » du Docker Hub sont communautaires et invérifiables. Les roues (≈ 380 Mio installés) sont plus légères et plus sûres.
- Mettre à jour les dépendances : élargir les bornes de `pyproject.toml`, puis régénérer `constraints.txt` depuis une image reconstruite sans contraintes (`pip install -r` sans `-c`, puis `pip freeze`), relancer les tests.

### Mémoire mesurée

Pic mémoire du container entier (anonyme + noyau, cache de pages exclu) au-dessus de son état de repos, ce container ayant au repos ≈ 500–560 Mio (claude, dockerd, containerd) ; mesures du 2026-11-26, Python 3.12-slim, cache de construction vide pour les builds :

| Commande | Avant (pip sans contraintes, pytest dans `api`) | Après |
|---|---|---|
| `docker compose build --no-cache` (dépendances installées par pip) | +190 Mio (36 s) | +165 Mio (59 s, `api-test`) |
| `docker compose build api worker` avec couches en cache | — | +75 Mio (23 s) |
| Suite complète (221 tests) | +196 Mio (20 s) | +246 Mio (26 s) avec Postgres léger |
| Un fichier (`tests/test_auth.py`, 23 tests) | — | +193 Mio (8 s) |

Postgres léger : ≈ 50 Mio au repos (`docker stats`). Je n'ai pas mesuré la configuration par défaut de Postgres sous la même charge, donc je ne chiffre pas son gain. Le gros du pic est le processus pytest (≈ 150 Mio de RSS une fois numpy, scipy et scikit-learn importés, contre ≈ 65 Mio pour l'API seule) et le moteur Docker pendant le build. Les mesures « avant » et « après » sont du même ordre : le gain est surtout un build sans compilation, reproductible (versions exactes) et qui ne réinstalle rien quand seul le code change.

**Limite non vérifiée** : ces mesures viennent d'un container de 2 Go, pas de 1 Go sans swap. Un total de ≈ 770 Mio (repos ≈ 520 + 250) tient sous 1 Go sur le papier, avec ≈ 250 Mio de marge, mais le repos d'un container varie (session `claude`, navigateur, autres processus).

**`/tmp` compte dans la limite** : dans un container de 1 Go, `/tmp` est un tmpfs imputé à la mémoire (des restes de pip/venv de plus de 400 Mio ont été observés chez le Reviewer). Vider `/tmp` avant de lancer (`find /tmp -mindepth 1 -delete`), et dans un container de 1 Go ne pas faire build et tests ensemble : construire d'abord, puis tester.

**Mémoire recommandée : 1,5 Go** ; en dessous de ≈ 1 Go la suite ne passe pas de façon fiable. Ne jamais lancer le build et les tests en même temps. Si la limite est atteinte :

1. Lancer fichier par fichier : `for f in api/tests/test_*.py; do scripts/test-api.sh tests/$(basename $f) || break; done` (le pic d'un fichier, +193 Mio, est proche de celui de la suite, +246 Mio : l'économie est modeste).
2. Construire l'image seule avant de lancer les tests (`docker compose --profile test build api-test`), sans autre commande lourde en parallèle.
3. Si un build à 1 Go échoue malgré tout, c'est que le container n'a pas la marge : augmenter la mémoire du Reviewer.
