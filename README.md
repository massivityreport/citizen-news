# Citizen News

Plateforme d'actualité participative : les citoyens votent sur les sujets qui méritent davantage d'attention, et une « une citoyenne » émerge par Successive Halving. Voir [le brief](docs/citizen-news-brief.md) et [le contrat HTTP](docs/api-contract.md).

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

> **Ordre de merge des piles** : pile backend (`agent/api-test-env`), puis pile front (`agent/front-auth-how`, qui apporte `web/`), puis cette branche. Tant que `web/` n'existe pas, le service `web` du compose ne se construit pas (`docker compose up` échoue sur lui) : sur la pile backend seule, lancez `docker compose up --build db api worker` (voir « Démarrer »).

Prérequis : Docker et Docker Compose v2, Python 3 (pour `scripts/smoke.py`, bibliothèque standard seule), un accès réseau sortant pour les flux RSS et pour `npm ci` au build du front.

```bash
cp .env.example .env
# Pour recevoir le lien de connexion dans mailpit, dans .env :
#   MAIL_BACKEND=smtp  SMTP_HOST=mailpit  SMTP_PORT=1025  SMTP_STARTTLS=false  DEMO_SEED=true
docker compose --profile mail up --build -d      # db, api, worker, web, mailpit
docker compose exec worker python -m app.cli refresh   # premier ingest + regroupement (le worker le refera toutes les 15 min)
docker compose run --rm -e DEMO_SEED=true api python -m app.cli seed-demo   # optionnel : sujets, comptes et votes fictifs
python3 scripts/smoke.py --mailpit http://localhost:8025   # (pile backend seule : ajouter --api-only --base http://localhost:8000) parcours de bout en bout
```

| Quoi | Où |
|---|---|
| Application (nginx : front + proxy `/api`) | <http://localhost:8080> (`WEB_BIND` / `WEB_PORT` pour changer l'interface ou le port ; `127.0.0.1` par défaut) |
| API directe, documentation | <http://localhost:8000>, <http://localhost:8000/docs> |
| Mails (profil `mail`) | <http://localhost:8025> |

- `APP_BASE_URL` vaut `http://localhost:8080` par défaut : le lien magique pointe sur le front. Sans mailpit (`MAIL_BACKEND=console`), passez `--logs` à `smoke.py` au lieu de `--mailpit` : il lit le lien dans `docker compose logs api`.
- Le navigateur n'appelle que `http://localhost:8080` : nginx proxifie `/api/` vers `api:8000`, donc même origine, pas de CORS ni de souci de cookie (`CORS_ORIGINS` reste configuré pour `npm run dev`, port 5173). `TRUST_PROXY` vaut `true` par défaut dans le compose : l'API lit l'IP cliente dans `X-Forwarded-For` posé par nginx, sinon toutes les limites par IP verraient l'adresse de nginx. Si vous atteignez l'API directement sur le port 8000, un client peut forger cet en-tête : c'est pourquoi le port 8000 n'est publié que sur `127.0.0.1` (`API_BIND`, à ne changer que derrière un pare-feu ou si `TRUST_PROXY=false`).
- `scripts/smoke.py [--base URL] (--mailpit URL | --logs)` : crée un compte jetable `smoke-<horodatage>@example.org` et vérifie la une, `vote/next` (résultats masqués), `halving/config`, le front (`/`, repli SPA, `Referrer-Policy`), le lien magique (usage unique, cookie `httpOnly` `SameSite=Lax`), le rattachement des votes, le vote connecté, `votes/mine`, la déconnexion. Code de sortie 1 et ligne `ÉCART : …` au premier écart. Il consomme un lien magique et quelques votes sur les limites de débit : pas plus de quelques lancements par heure. `--api-only` (avec `--base http://localhost:8000`) le lance contre l'API seule, sans vérifier le front ; sans cette option il exige le HTML du front.
- La une ne change qu'après le prochain cycle de halving du worker (`python -m app.cli halve` pour le forcer), et la réponse est mise en cache 5 secondes côté API.
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
| `SESSION_TTL_DAYS`, `LOGIN_TOKEN_TTL_MINUTES` | Durée de la session (30 jours) et du lien magique (15 minutes) |
| `MAIL_BACKEND` | `console` (défaut) : le lien est écrit dans les logs de l'API, **développement seulement** ; `smtp` : envoi réel |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_STARTTLS`, `MAIL_FROM` | Serveur SMTP (port 587 et STARTTLS par défaut ; `SMTP_HOST` obligatoire avec `smtp`). Le mot de passe ne vient que de l'environnement |
| `TRUST_PROXY` | `true` derrière un reverse proxy (défaut du compose : nginx du service `web`) : l'IP cliente est la dernière entrée de `X-Forwarded-For` (sinon l'en-tête est ignoré) |
| `DEMO_SEED` | `true` autorise `python -m app.cli seed-demo` (données fictives, développement seulement ; refusé avec `COOKIE_SECURE=true`) |
| `RATE_LIMIT_*`, `CLAIM_MAX_VOTES` | Limites de débit (dont `RATE_LIMIT_VOTE_PER_ACCOUNT`, 120 votes par minute et par compte) et plafond du rattachement de votes (voir [api/README.md](api/README.md)) |

Fichiers dans `api/config/` : `feeds.yaml` (flux RSS des médias), `clustering.yaml` (seuil de similarité, fenêtre de temps, sources minimales pour la une) et `halving.yaml` (sévérité du halving) et `front.yaml` (seuils et classement de la une) ; valeurs validées au chargement, hors bornes refusées. Le fonctionnement du halving est expliqué dans [docs/halving.md](docs/halving.md).

## Alimentation en sujets

```bash
docker compose run --rm api python -m app.cli refresh   # ingest + cluster, une fois
curl 'http://localhost:8000/api/topics/front?limit=5'
```

Commandes `ingest`, `cluster`, `halve`, `refresh`, `run`, `seed-demo`, réglage du seuil de regroupement et détail des endpoints : [api/README.md](api/README.md).

## Vote et halving

`POST /api/votes` enregistre (ou remplace) le vote d'un compte sur un sujet. Le worker recalcule ensuite, à chaque cycle, l'état des sujets (`new`, `active`, `reserve`, `emerged`) par Successive Halving ; le flux `GET /api/vote/next` et la une `GET /api/topics/front` s'en servent. Fonctionnement et exemple chiffré : [docs/halving.md](docs/halving.md). Pour voir la une bouger sans attendre de vrais votes :

```bash
docker compose run --rm -e DEMO_SEED=true api python -m app.cli seed-demo
curl 'http://localhost:8000/api/topics/front?limit=10'
```

## Comptes : connexion par lien magique

Pas de mot de passe : l'utilisateur saisit son e-mail, reçoit un lien à usage unique, et le front l'échange contre un cookie de session.

1. Le front appelle `POST /api/auth/magic-link {email}` (toujours `202`, que le compte existe ou non).
2. L'e-mail contient `{APP_BASE_URL}/connexion?token=…`. La page `/connexion` du front lit `token` et appelle `POST /api/auth/verify {token}` : `200 {email}` et cookie de session `httpOnly`, `SameSite=Lax` (`Secure` avec `COOKIE_SECURE=true`). Le compte est créé au premier lien vérifié.
3. Ensuite `GET /api/me`, `POST /api/auth/logout`, et le rattachement des votes anonymes du navigateur : `POST /api/votes/claim`, puis `GET /api/votes/mine`.

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
scripts/test-api.sh                      # toute la suite (221 tests)
scripts/test-api.sh tests/test_auth.py   # un seul fichier
```

Le code est monté en lecture seule : aucun rebuild après une modification. Mémoire nécessaire, pics mesurés et marche à suivre si elle manque : [api/README.md](api/README.md#tests).

## Migrations

Créer une migration après modification des modèles (avec `db` démarré) :

```bash
docker compose run --rm --user root -v "$PWD/api:/srv/api" api \
  sh -c 'alembic revision --autogenerate -m "description" && chown -R $(stat -c %u:%g .) alembic'
```

## Structure

```
docker-compose.yml        db (PostgreSQL 16) + api + worker (ingestion, regroupement et halving périodiques) + web (front nginx, pile front) + mailpit (profil `mail`)
scripts/                  test-api.sh (tests), smoke.py (parcours de bout en bout)
api/
  Dockerfile, pyproject.toml, alembic.ini
  alembic/versions/       migrations
  app/
    main.py               application FastAPI, CORS
    db.py                 moteur et session SQLAlchemy
    models/               schéma de données
    routers/              routes HTTP (préfixe /api)
    services/             logique métier (ingestion, regroupement, sujets)
    cli.py                commandes ingest / cluster / halve / refresh / run / seed-demo
  config/                 settings.py, halving.py/.yaml, feeds.py/.yaml, clustering.py/.yaml
  tests/                  pytest (base PostgreSQL réelle)
docs/                     brief produit, contrat HTTP, halving
```
