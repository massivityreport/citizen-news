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

- PostgreSQL (service `db`, volume nommé `pgdata`) puis l'API (service `api`).
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

Fichiers dans `api/config/` : `feeds.yaml` (flux RSS, rempli par la tâche d'ingestion) et `halving.yaml` (sévérité du halving ; valeurs validées au chargement, hors bornes refusées).

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
docker-compose.yml        db (PostgreSQL 16) + api
api/
  Dockerfile, pyproject.toml, alembic.ini
  alembic/versions/       migrations
  app/
    main.py               application FastAPI, CORS
    db.py                 moteur et session SQLAlchemy
    models/               schéma de données
    routers/              routes HTTP (préfixe /api)
    services/             logique métier
  config/                 settings.py, halving.py + halving.yaml, feeds.yaml
  tests/                  pytest (base PostgreSQL réelle)
docs/                     brief produit, contrat HTTP
```
