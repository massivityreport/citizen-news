# Citizen News

Plateforme d'actualité participative : les citoyens votent sur les sujets qui méritent davantage d'attention, et une « une citoyenne » émerge par Successive Halving. Voir [le brief](docs/citizen-news-brief.md) et [le contrat HTTP](docs/api-contract.md).

## Prérequis

- Docker et Docker Compose (v2).
- Pour lancer l'API hors Docker : Python 3.12 et une base PostgreSQL 16.

## Démarrer

```bash
cp .env.example .env   # optionnel : les valeurs par défaut conviennent au développement local
docker compose up --build
```

- PostgreSQL (service `db`, volume nommé `pgdata`), l'API (service `api`), puis le `worker` qui récupère les flux RSS et regroupe les articles en sujets toutes les 15 minutes (`INGEST_INTERVAL_MINUTES`). La une se remplit après le premier cycle (quelques secondes).
- L'API applique les migrations Alembic (`alembic upgrade head`) puis lance uvicorn sur <http://localhost:8000>.
- Vérification : `curl http://localhost:8000/api/health` → `{"status":"ok"}`. Documentation interactive : <http://localhost:8000/docs>.
- Repartir d'une base vide : `docker compose down -v`.

## Configuration

Variables d'environnement (voir `.env.example`) :

| Variable | Rôle |
|---|---|
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Base PostgreSQL (le mot de passe par défaut n'est valable qu'en développement) |
| `DATABASE_URL` | URL SQLAlchemy de l'API (construite par le compose) |
| `CORS_ORIGINS` | Origines autorisées par CORS, séparées par des virgules |
| `INGEST_INTERVAL_MINUTES` | Minutes entre deux cycles d'ingestion du `worker` (défaut 15) |
| `APP_BASE_URL` | URL publique du front : le lien de connexion est `{APP_BASE_URL}/connexion?token=…` (défaut `http://localhost:5173`) |
| `COOKIE_SECURE` | `true` dès que l'API est servie en HTTPS (cookie `Secure`) ; `false` en développement |
| `SESSION_TTL_DAYS`, `LOGIN_TOKEN_TTL_MINUTES` | Durée de la session (30 jours) et du lien magique (15 minutes) |
| `MAIL_BACKEND` | `console` (défaut) : le lien est écrit dans les logs de l'API, **développement seulement** ; `smtp` : envoi réel |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_STARTTLS`, `MAIL_FROM` | Serveur SMTP (port 587 et STARTTLS par défaut ; `SMTP_HOST` obligatoire avec `smtp`). Le mot de passe ne vient que de l'environnement |
| `TRUST_PROXY` | `true` derrière un reverse proxy : l'IP cliente est la dernière entrée de `X-Forwarded-For` (sinon l'en-tête est ignoré) |
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

Le front envoie ses requêtes avec `credentials: "include"` ; `CORS_ORIGINS` doit contenir son origine.

### Essayer en local avec mailpit

```bash
# .env : MAIL_BACKEND=smtp  SMTP_HOST=mailpit  SMTP_PORT=1025  SMTP_STARTTLS=false
docker compose --profile mail up --build
```

Les e-mails arrivent dans l'interface de mailpit, <http://localhost:8025> (SMTP sur le port 1025 ; les deux ports ne sont exposés que sur `127.0.0.1`). Sans mailpit, `MAIL_BACKEND=console` (défaut) écrit le message, lien compris, dans `docker compose logs api` : n'utilisez jamais `console` en production, le lien y donne accès au compte : l'API **refuse de démarrer** avec `MAIL_BACKEND=console` et `COOKIE_SECURE=true`, et journalise un avertissement au démarrage dès que `console` est actif.

## Tests

Les tests utilisent une vraie base PostgreSQL : une base jetable `citizen_news_test` est créée sur le service `db`, migrée, puis supprimée.

```bash
docker compose run --rm api pytest
```

Après une modification du code, reconstruire l'image (`docker compose build api`) : le code est copié dans l'image, pas monté.

## Migrations

Créer une migration après modification des modèles (avec `db` démarré) :

```bash
docker compose run --rm --user root -v "$PWD/api:/srv/api" api \
  sh -c 'alembic revision --autogenerate -m "description" && chown -R $(stat -c %u:%g .) alembic'
```

## Structure

```
docker-compose.yml        db (PostgreSQL 16) + api + worker (ingestion, regroupement et halving périodiques) + mailpit (profil `mail`)
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
