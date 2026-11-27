# Citizen News

**Citizen News, ce n'est pas Google News : c'est la une choisie par les citoyens.** Chaque jour, des articles de médias français sont regroupés en sujets (un sujet = un événement, au moins 2 médias). Chaque citoyen, connecté par lien magique, compose **sa une de 10 sujets** (sans ordre, poids égaux) dans le bassin du jour, modifiable jusqu'à 17 h ; à 17 h le serveur agrège toutes les unes et publie **la une collective du jour, figée**, consultable à une adresse stable (`/une/AAAA-MM-JJ`). Un backoffice protégé par mot de passe montre l'aperçu du classement avant publication, les égalités, les statistiques et gère les sources. Produit : [brief V2](docs/citizen-news-brief-v2.md) ; routes : [contrat HTTP](docs/api-contract.md) ; backend : [api/README.md](api/README.md). La V1 (vote, Successive Halving) a été **remplacée** : [brief V1](docs/citizen-news-brief.md), conservé pour mémoire.

## Cycle quotidien

```
flux RSS ─ingest─▶ articles ─cluster─▶ sujets ──▶ bassin du jour (articles des POOL_WINDOW_HOURS dernières heures, >= 2 médias)
                                                     │  onglets : Au hasard (graine du navigateur) · Récents · Sous les radars (<= RADAR_MAX_SOURCES médias)
citoyen connecté : compose sa une (<= 10 sujets) jusqu'à EDITION_HOUR h ───┘
17 h (EDITION_HOUR, EDITION_TIMEZONE) : le worker agrège (score = nombre de unes qui contiennent le sujet ; égalités :
   médias distincts, puis fraîcheur, puis id) et publie l'édition : les 10 premiers, figés (titre, résumé, sources, approbations)
```

- **Worker** : un seul processus (`python -m app.cli run`) avec deux boucles : ingestion + regroupement toutes les `INGEST_INTERVAL_MINUTES` (15), et un tick de **clôture chaque minute** (séparé : une ingestion lente ne retarde jamais la clôture). La clôture est idempotente (verrou PostgreSQL + contrainte d'unicité) : un worker arrêté rattrape au redémarrage, sans éditions fantômes pour les jours vides.
- **Heure** : `EDITION_HOUR` h dans le fuseau `EDITION_TIMEZONE` (17 h Europe/Paris = 16 h UTC en hiver, 15 h en été ; le changement d'heure est géré). `edition_date` est la date **locale** du jour de clôture : c'est la clé de l'édition et son permalien. Dès l'heure de clôture, la une du jour n'est plus modifiable (même si le worker a du retard) ; la une du lendemain s'ouvre à la publication.
- **Bassin** : un sujet y est s'il a un article daté dans les `POOL_WINDOW_HOURS` (24) dernières heures **et** au moins 2 médias distincts. Le bassin n'expose **aucun compteur** d'approbation avant la publication. À la clôture, seuls comptent les sujets encore dans le bassin à cet instant.
- **Sous les radars** : sujets du bassin couverts par au plus `RADAR_MAX_SOURCES` (3) médias.
- **Limites de débit** (en mémoire, par processus API ; `429` + `Retry-After`) : lien magique par e-mail (5/h) et par IP (20/h), vérification par IP (30/h), connexion admin par IP (10 par 15 min), écritures de la une par compte (`RATE_LIMIT_UNE_WRITES_PER_ACCOUNT`, 60 par `RATE_LIMIT_UNE_WINDOW_SECONDS`, 60 s). Détail dans [api/README.md](api/README.md#limitation-de-débit).

## Prérequis

- Docker et Docker Compose (v2).
- Pour lancer l'API hors Docker : Python 3.12 et une base PostgreSQL 16.

## Démarrer

```bash
cp .env.example .env   # optionnel : les valeurs par défaut conviennent au développement local
docker compose up --build db api worker   # sans le front ; l'application complète (avec `web`) : voir « Lancer toute l'application »
```

- PostgreSQL (service `db`, volume nommé `pgdata`), l'API (service `api`), puis le `worker` qui récupère les flux RSS et regroupe les articles en sujets toutes les 15 minutes (`INGEST_INTERVAL_MINUTES`). La une se remplit après le premier cycle (quelques secondes).
- L'API applique les migrations Alembic (`alembic upgrade head`) puis lance uvicorn sur <http://localhost:8000>.
- Vérification : `curl http://localhost:8000/api/health` → `{"status":"ok"}`. Documentation interactive : <http://localhost:8000/docs>.
- Repartir d'une base vide : `docker compose down -v`.

## Lancer toute l'application

> Le front (`web/`) est livré par une pile séparée. Tant qu'elle n'est pas fusionnée, le service `web` ne se construit pas (`docker compose up` échoue sur lui) : lancez alors `docker compose up --build db api worker` (voir « Démarrer »).

Prérequis : Docker et Docker Compose v2, Python 3 (pour `scripts/smoke.py`, bibliothèque standard seule), un accès réseau sortant pour les flux RSS et pour `npm ci` au build du front.

```bash
cp .env.example .env
# Pour recevoir le lien de connexion dans mailpit, dans .env :
#   MAIL_BACKEND=smtp  SMTP_HOST=mailpit  SMTP_PORT=1025  SMTP_STARTTLS=false  DEMO_SEED=true
docker compose --profile mail up --build -d      # db, api, worker, web, mailpit
docker compose exec worker python -m app.cli refresh   # premier ingest + regroupement (le worker le refera toutes les 15 min)
docker compose run --rm -e DEMO_SEED=true api python -m app.cli seed-demo   # optionnel : données de démonstration (voir « Données de démonstration »)
python3 scripts/smoke.py                         # vérification de bout en bout de l'API (voir « Vérification : smoke.py »)
```

| Quoi | Où |
|---|---|
| Application (nginx : front + proxy `/api`) | <http://localhost:8080> (`WEB_BIND` / `WEB_PORT` pour changer l'interface ou le port ; `127.0.0.1` par défaut) |
| API directe, documentation | <http://localhost:8000>, <http://localhost:8000/docs> |
| Mails (profil `mail`) | <http://localhost:8025> |

- `APP_BASE_URL` vaut `http://localhost:8080` par défaut : le lien magique pointe sur le front. Sans mailpit (`MAIL_BACKEND=console`), le lien est écrit dans `docker compose logs api`.
- Le navigateur n'appelle que `http://localhost:8080` : nginx proxifie `/api/` vers `api:8000`, donc même origine, pas de CORS ni de souci de cookie (`CORS_ORIGINS` reste configuré pour `npm run dev`, port 5173). `TRUST_PROXY` vaut `true` par défaut dans le compose : l'API lit l'IP cliente dans `X-Forwarded-For` posé par nginx, sinon toutes les limites par IP verraient l'adresse de nginx. Si vous atteignez l'API directement sur le port 8000, un client peut forger cet en-tête : c'est pourquoi le port 8000 n'est publié que sur `127.0.0.1` (`API_BIND`, à ne changer que derrière un pare-feu ou si `TRUST_PROXY=false`).
- La une collective est publiée par le worker à `EDITION_HOUR` h (17 h Europe/Paris), vérifiée chaque minute ; `docker compose exec worker python -m app.cli close-edition --dry-run` affiche le classement sans publier.
- Tests de l'API : `scripts/test-api.sh` (voir « Tests »). Arrêt : `docker compose --profile mail down` (`-v` pour supprimer aussi la base).

### Limites connues

- Le service `web` dépend de `web/` (pile front) : voir l'ordre de merge ci-dessus.
- Le build du front exécute `npm ci` : accès au registre npm requis ; l'image est `node:24-alpine` puis `nginx:1.27-alpine`.
- Le front n'a pas de healthcheck : `depends_on` ne l'attend pas, il attend `api`.
- Pas de HTTPS : en production, placez un proxy TLS devant, passez `COOKIE_SECURE=true`, `MAIL_BACKEND=smtp`, retirez `DEMO_SEED`, et faites journaliser `$uri` (pas la query string) par ce proxy : le jeton du lien magique est dans l'URL.
- Les compteurs de limites de débit sont en mémoire, par processus API.
- `GET /api/me` répond `401` à un visiteur anonyme : le navigateur affiche cette ligne dans sa console à chaque chargement du front (comportement du contrat, sans effet).

## Configuration

Variables d'environnement (voir `.env.example`) :

| Variable | Rôle |
|---|---|
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Base PostgreSQL (le mot de passe par défaut n'est valable qu'en développement) |
| `DATABASE_URL` | URL SQLAlchemy de l'API (construite par le compose) |
| `CORS_ORIGINS` | Origines autorisées par CORS, séparées par des virgules |
| `INGEST_INTERVAL_MINUTES` | Minutes entre deux cycles d'ingestion du `worker` (défaut 15) |
| `APP_BASE_URL` | URL publique du front : le lien de connexion est `{APP_BASE_URL}/connexion?token=…` (défaut `http://localhost:8080`, le service `web`) |
| `API_BIND` | Interface du port 8000 de l'API (`127.0.0.1` par défaut). Avec `TRUST_PROXY=true`, ne pas l'ouvrir : un hôte pourrait forger `X-Forwarded-For` et contourner les limites par IP |
| `WEB_BIND`, `WEB_PORT` | Interface (`127.0.0.1`) et port (`8080`) du service `web` sur la machine hôte |
| `COOKIE_SECURE` | `true` dès que l'API est servie en HTTPS (cookie `Secure`) ; `false` en développement |
| `ADMIN_PASSWORD` | Mot de passe unique du backoffice (`/admin`). Défaut de développement : `make-media-great-again`. L'API **refuse de démarrer** avec ce défaut et `COOKIE_SECURE=true` (et journalise un avertissement avec `COOKIE_SECURE=false`) : **à changer en production**, par un secret long qui ne figure dans aucun dépôt. Jamais écrit dans les logs ni les réponses |
| `ADMIN_SESSION_HOURS` | Durée de la session admin, en heures (défaut 8) |
| `RATE_LIMIT_ADMIN_LOGIN_PER_IP`, `RATE_LIMIT_ADMIN_LOGIN_WINDOW_SECONDS` | Tentatives de connexion admin par IP (10) sur la fenêtre (900 s) ; `429` + `Retry-After` au-delà |
| `SESSION_TTL_DAYS`, `LOGIN_TOKEN_TTL_MINUTES` | Durée de la session (30 jours) et du lien magique (15 minutes) |
| `MAIL_BACKEND` | `console` (défaut) : le lien est écrit dans les logs de l'API, **développement seulement** ; `smtp` : envoi réel |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_STARTTLS`, `MAIL_FROM` | Serveur SMTP (port 587 et STARTTLS par défaut ; `SMTP_HOST` obligatoire avec `smtp`). Le mot de passe ne vient que de l'environnement |
| `TRUST_PROXY` | `true` derrière un reverse proxy (défaut du compose : nginx du service `web`) : l'IP cliente est la dernière entrée de `X-Forwarded-For` (sinon l'en-tête est ignoré) |
| `EDITION_HOUR`, `EDITION_TIMEZONE` | Heure de clôture (17) et fuseau (`Europe/Paris`) ; changement d'heure géré. **L'API et le worker doivent avoir les mêmes valeurs** (le compose les passe aux deux) |
| `POOL_WINDOW_HOURS` | Fenêtre du bassin, en heures (24) : un sujet y est s'il a un article plus récent (et au moins 2 médias). Même remarque : API et worker |
| `RADAR_MAX_SOURCES` | Onglet « Sous les radars » : sujets couverts par au plus ce nombre de médias distincts (3) |
| `RATE_LIMIT_UNE_WRITES_PER_ACCOUNT`, `RATE_LIMIT_UNE_WINDOW_SECONDS` | Écritures de la une par compte (60) sur la fenêtre (60 s) ; `429` au-delà |
| `DEMO_SEED` | `true` autorise `python -m app.cli seed-demo` (données fictives, développement seulement ; refusé avec `COOKIE_SECURE=true`) et `close-edition --now` sans `--dry-run` |
| `RATE_LIMIT_*` | Limites de débit (voir [api/README.md](api/README.md)) |

Fichiers dans `api/config/` : `feeds.yaml` (flux RSS de départ : il n'initialise que la base, qui reste la référence, gérée depuis /admin, onglet Sources), `clustering.yaml` (seuil de similarité, fenêtre de temps, sources minimales pour qu'un sujet soit éligible) ; valeurs validées au chargement, hors bornes refusées.

## Backoffice

- **Accès** : <http://localhost:8080/admin> (page non indexée). Connexion par le mot de passe unique `ADMIN_PASSWORD` (voir « Configuration » : à changer en production), session de `ADMIN_SESSION_HOURS` heures dans un cookie `cn_admin` distinct de la session citoyenne. Pas de comptes ni de rôles.
- **Accueil** : chiffres clés (articles ingérés, participants et sélections, sur les 24 dernières heures glissantes et au total) et courbe sur 30 jours (jours en UTC). Le bouton « Actualiser » recharge ; pas de rafraîchissement automatique.
- **Édition** : l'**aperçu** du classement que la clôture publierait maintenant (les 10 de la une, les 10 suivants, les égalités et celle qui chevauche la coupure 10/11, critère de départage), calculé par la même fonction que la clôture ; la liste des éditions publiées et chaque édition avec ses approbations.
- **Sources** : ajouter un flux RSS (vérifié côté serveur, adresses publiques seulement), le désactiver (l'ingestion l'ignore, ses articles et sujets restent) ou le supprimer définitivement (avec confirmation du nombre d'articles supprimés). La base est la référence ; `feeds.yaml` ne fait qu'initialiser.
- **Articles** : liste paginée et triable, filtres par source, sujet, dates (date de publication ; un article sans date n'apparaît pas avec un filtre de date) et « non regroupés ».
- **Sujets** : liste triable (approbations de l'édition en cours par défaut, titre, articles, mise à jour) ; détail d'un sujet (articles, approbations, historique par édition publiée).
- **Avis** : les avis envoyés par le formulaire « Votre avis » du site public. L'onglet affiche le nombre d'avis non lus ; la liste va du plus récent au plus ancien (date, type, e-mail, page, début du message, marque « non lu », marque « répondu » dès qu'une réponse a été envoyée), avec un filtre « non lus seulement ». Le détail montre le message complet, l'e-mail, la page (nom et adresse), la taille d'écran, le navigateur et, si le visiteur l'a joint, son parcours récent avec l'heure de chaque action. Ouvrir un avis le passe en « lu » ; un bouton le remet en « non lu » ; sous le message, l'historique des réponses déjà envoyées (avec leur date) et un champ pour en écrire une nouvelle : elle part par e-mail à l'auteur (objet « Citizen News : réponse à votre avis « début de l'avis… » ») et n'est enregistrée qu'une fois l'envoi réussi ; s'il échoue, rien n'est enregistré, une erreur s'affiche et le texte reste dans le champ pour réessayer. Les réponses de l'utilisateur ne reviennent pas dans le backoffice et il n'a pas d'espace pour relire les réponses. La suppression (après confirmation) est définitive et emporte l'avis, son parcours et ses réponses. **C'est le seul endroit du backoffice qui affiche des adresses e-mail** (celles que les visiteurs ont laissées pour qu'on leur réponde) : elles ne figurent dans aucun autre onglet ni dans aucune autre réponse admin, et restent derrière la session admin. Pas d'effacement automatique, d'export ni de notification pour l'instant.
- **Limites connues** : lecture seule pour les articles, sujets et statistiques (aucune modification, aucun export) ; les adresses e-mail ne sont affichées que dans l'onglet Avis (nulle part ailleurs) ; les statistiques ne se rafraîchissent pas seules ; un sujet qui perd des articles (suppression d'une source) reste en base avec ses sélections et garde son titre jusqu'au prochain regroupement ; un seul mot de passe partagé, sans journal d'audit. Détail des routes : [docs/api-contract.md](docs/api-contract.md), section Admin.

## Alimentation en sujets

```bash
docker compose run --rm api python -m app.cli refresh   # ingest + cluster, une fois
```

Commandes `ingest`, `cluster`, `refresh`, `close-edition`, `run`, `seed-demo`, réglage du seuil de regroupement et détail des endpoints : [api/README.md](api/README.md).

## Données de démonstration

```bash
docker compose run --rm -e DEMO_SEED=true api python -m app.cli seed-demo [--seed 1] [--reset]
```

Développement seulement : refusé sans `DEMO_SEED=true` et avec `COOKIE_SECURE=true` ; ne l'exécutez jamais en production (`DEMO_SEED` doit y rester `false`), et le compose ne le lance jamais tout seul. Crée 5 médias fictifs inactifs (le worker ne les interroge pas), 20 sujets « [Démo] … » avec des articles des dernières 24 h (la plupart couverts par 3 à 5 médias, quelques-uns par 2 ou 3 pour « Sous les radars », certains avec une image `https://images.demo.invalid/…`), 12 comptes fictifs `demo-NN@example.invalid` (aucun e-mail n'est jamais envoyé) dont les unes pour l'édition en cours donnent un classement avec des égalités et une égalité à cheval sur la coupure 10/11 (visible dans l'aperçu admin), et 3 éditions passées publiées (veilles, avant-veilles…) pour l'historique, les permaliens et le backoffice. Idempotent : relancer remplace les données de démo, sans doublon et sans toucher aux données réelles ; `--reset` supprime en plus **toutes** les éditions et toutes les unes (calendrier vierge). Pour tester la clôture sans attendre 17 h : `python -m app.cli close-edition --dry-run --now 2026-11-27T16:05:00Z` (classement à cette heure) puis, avec `DEMO_SEED=true`, la même commande sans `--dry-run` (publie vraiment : l'option `--now`, fuseau obligatoire, est refusée sans `--dry-run` hors développement).

## Vérification : `smoke.py`

```bash
python3 scripts/smoke.py [--base http://localhost:8000] [--radar-max 3]   # --base : l'API, ou le front nginx (8080) qui la proxifie
ADMIN_PASSWORD=… python3 scripts/smoke.py                                 # ajoute la partie admin
```

Bibliothèque standard seule, contre une pile qui tourne (après `seed-demo` pour avoir de la matière). Il vérifie : la santé ; le bassin (3 onglets, graine stable, `422` sans graine, cartes complètes, `image_url` null ou https, **aucun compteur ni classement dans le bassin**) ; `GET /api/edition/current`, `/api/editions`, `/api/editions/{date}` (200 pour une édition existante, 404 sinon, 422 si mal formée) ; `401` sans session sur `/api/me`, `/api/me/une`, `/api/admin/edition/preview` et `/api/admin/stats` ; une demande de lien magique avec un brouillon (`202`) ; avec `ADMIN_PASSWORD` (variable d'environnement, jamais en argument) : mauvais mot de passe `401`, connexion, aperçu, éditions, statistiques, sujets (tri, aucune adresse e-mail), déconnexion. Il **ne vérifie pas le front** et dit quand un contrôle est sauté (bassin ou historique vide, `ADMIN_PASSWORD` absent). Code 1 et ligne `ÉCART : …` au premier écart. Il n'écrit en base qu'un jeton de lien magique (e-mail `smoke-<horodatage>@example.org` ; avec `MAIL_BACKEND=console`, aucun e-mail réel) : pas plus de quelques lancements par heure (limites de débit).

## Mise à niveau depuis la V1 : suppression irréversible des données de vote

La migration **0009** (appliquée au démarrage de l'API, `alembic upgrade head`) **supprime définitivement** la table `votes` et les colonnes de halving des sujets (`state`, `wave`, `state_changed_at`, `evaluated_at`, `votes_at_eval`) : tous les votes et états V1 sont perdus (décision produit : remplacement net de la V1). `downgrade` ne recrée que des structures **vides** ; il ne ramène aucune donnée. Marche à suivre en production, **avant** de déployer la nouvelle image (c'est son démarrage qui migre) :

```bash
# 1. sauvegarde (le dump contient les votes V1 : à conserver ou détruire selon votre politique de données)
docker compose exec -T db pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc > citizen_news-avant-0009.dump
# 2. vérifier que le dump est lisible
pg_restore --list citizen_news-avant-0009.dump | head
# 3. déployer : l'API migre au démarrage ; le worker démarre une fois l'API saine
docker compose up -d --build
# restauration éventuelle (retour à la V1 : ancienne image + ce dump) :
docker compose exec -T db pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists < citizen_news-avant-0009.dump
```

Avant le premier déploiement : `COOKIE_SECURE=true`, `MAIL_BACKEND=smtp`, `ADMIN_PASSWORD` propre, `DEMO_SEED=false`. Les comptes (e-mails) et les sujets sont conservés ; les anciennes sessions restent valides.

## Comptes : connexion par lien magique

Pas de mot de passe : l'utilisateur saisit son e-mail, reçoit un lien à usage unique, et le front l'échange contre un cookie de session.

1. Le front appelle `POST /api/auth/magic-link {email}` (toujours `202`, que le compte existe ou non).
2. L'e-mail contient `{APP_BASE_URL}/connexion?token=…`. La page `/connexion` du front lit `token` et appelle `POST /api/auth/verify {token}` : `200 {email}` et cookie de session `httpOnly`, `SameSite=Lax` (`Secure` avec `COOKIE_SECURE=true`). Le compte est créé au premier lien vérifié.
3. Ensuite `GET /api/me` et `POST /api/auth/logout`. Un brouillon de une (`draft`) peut accompagner la demande de lien ; il est fusionné dans la une du compte à la vérification si l'édition est ouverte.

Le front envoie ses requêtes avec `credentials: "include"` ; derrière le service `web` tout passe par la même origine, `CORS_ORIGINS` ne sert que pour `npm run dev` (5173).

### Essayer en local avec mailpit

```bash
# .env : MAIL_BACKEND=smtp  SMTP_HOST=mailpit  SMTP_PORT=1025  SMTP_STARTTLS=false
docker compose --profile mail up --build
```

Les e-mails arrivent dans l'interface de mailpit, <http://localhost:8025> (SMTP sur le port 1025 ; les deux ports ne sont exposés que sur `127.0.0.1`). Sans mailpit, `MAIL_BACKEND=console` (défaut) écrit le message, lien compris, dans `docker compose logs api` : n'utilisez jamais `console` en production, le lien y donne accès au compte : l'API **refuse de démarrer** avec `MAIL_BACKEND=console` et `COOKIE_SECURE=true`, et journalise un avertissement au démarrage dès que `console` est actif.

## Tests

Les tests utilisent une vraie base PostgreSQL (une base jetable `citizen_news_test` est créée, migrée, puis supprimée), dans un service `db-test` léger (profil `test`, données en tmpfs), séparé de `db`.

```bash
scripts/test-api.sh                      # toute la suite
scripts/test-api.sh tests/test_auth.py   # un seul fichier
```

Le code est monté en lecture seule : aucun rebuild après une modification. Un fichier à la fois (mémoire limitée) ; mémoire nécessaire, pics mesurés et marche à suivre si elle manque : [api/README.md](api/README.md#tests). Les fichiers de `api/tests/` :

| Fichier | Ce qu'il vérifie |
|---|---|
| `test_health.py` | `GET /api/health` (200, 503 si la base est indisponible) et CORS |
| `test_schema.py` | contraintes du schéma V2 (une sélection par compte, jour et sujet ; date d'édition unique ; rang 1..10 ; suppressions en cascade ; plus de colonnes de halving) |
| `test_migration_0009.py` | migration 0009 sur une base peuplée en V1 : données V2 créées, votes supprimés, `downgrade` |
| `test_ingest.py` | ingestion RSS (parsing, doublons, flux en erreur, images, ré-ingestion), sans réseau |
| `test_clustering.py` | regroupement TF-IDF : seuil, fenêtre, idempotence |
| `test_feeds_config.py` | validation de `feeds.yaml` |
| `test_safe_fetch.py` | garde SSRF de la récupération d'un flux (adresses privées, redirections, DNS) |
| `test_topic_cards.py` | construction des cartes de sujet (sources, compteurs, image) |
| `test_pool.py` | bassin : éligibilité, 3 onglets, graine, plafond, nombre de requêtes constant, aucun compteur |
| `test_edition_calendar.py` | calendrier : `edition_date`, ouverture/fermeture, changement d'heure, retard du worker |
| `test_me_une.py` | une personnelle `/api/me/une*` : limite de 10, concurrence, clôture, bassin |
| `test_aggregation.py` | `aggregate` : scores, classement, égalités, coupure, données de publication, aucune écriture |
| `test_close.py` | `close_due_edition` : publication figée, idempotence, rattrapage, atomicité, concurrence |
| `test_worker.py` | tick de clôture du worker et commande `close-edition` |
| `test_editions_api.py` | routes publiques des éditions ; aucun compteur accessible à un citoyen avant publication |
| `test_auth.py`, `test_auth_draft.py`, `test_sessions.py` | lien magique, brouillon de une, sessions (jetons hachés, expiration, purge) et cookie |
| `test_mailer.py`, `test_ratelimit.py` | envoi (SMTP/console) et limites de débit |
| `test_admin_auth.py` | connexion admin : mot de passe, cookie, limite, protection de toutes les routes |
| `test_admin_sources.py` | sources : liste, ajout (garde SSRF), désactivation, suppression confirmée |
| `test_admin_articles.py`, `test_admin_topics.py`, `test_admin_topics_approvals.py` | articles et sujets admin : pagination, tri, filtres, approbations, historique |
| `test_admin_stats.py` | statistiques (24 h, total, série de 30 jours) |
| `test_admin_preview.py`, `test_admin_editions.py` | aperçu (même classement que la clôture, égalités, coupure, aucune écriture) et éditions admin |
| `test_demo.py` | `seed-demo` (garde dev, idempotence, bassin, égalités et coupure, éditions passées, `--reset`) et `close-edition --now` |
| `test_cli.py` | commandes `refresh` et boucle ; `halve` n'existe plus |

## Migrations

Créer une migration après modification des modèles (avec `db` démarré) :

```bash
docker compose run --rm --user root -v "$PWD/api:/srv/api" api \
  sh -c 'alembic revision --autogenerate -m "description" && chown -R $(stat -c %u:%g .) alembic'
```

## Structure

```
docker-compose.yml        db (PostgreSQL 16) + api + worker (ingestion et regroupement périodiques, clôture de l'édition à 17 h) + web (front nginx, pile front) + mailpit (profil `mail`)
scripts/                  test-api.sh (tests), smoke.py (vérification de l'API en marche)
api/
  Dockerfile, pyproject.toml, alembic.ini
  alembic/versions/       migrations
  app/
    main.py               application FastAPI, CORS
    db.py                 moteur et session SQLAlchemy
    models/               schéma de données
    routers/              routes HTTP (préfixe /api)
    services/             logique métier (ingestion, regroupement, sujets)
    cli.py                commandes ingest / cluster / refresh / close-edition / run / seed-demo
  config/                 settings.py, feeds.py/.yaml, clustering.py/.yaml
  tests/                  pytest (base PostgreSQL réelle)
docs/                     brief produit V2 (le V1, remplacé, est gardé pour mémoire), contrat HTTP V2
```
