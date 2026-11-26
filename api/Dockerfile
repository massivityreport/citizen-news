# syntax=docker/dockerfile:1
# Cibles : `api` (exécution : api + worker, sans pytest) et `test` (api + pytest, pour `api-test`).
# Roues précompilées seulement (--only-binary) : aucune compilation, donc un pic mémoire bas à la construction.
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /srv/api

# Dépendances d'exécution. Seuls pyproject.toml et constraints.txt invalident cette couche, pas le code.
# Le projet n'est pas packagé : le code tourne depuis /srv/api.
FROM base AS deps-runtime
COPY pyproject.toml constraints.txt ./
RUN python - <<'PY' > requirements.txt
import tomllib
print("\n".join(tomllib.load(open("pyproject.toml", "rb"))["project"]["dependencies"]))
PY
RUN pip install --prefix=/install --only-binary=:all: -c constraints.txt -r requirements.txt

# Dépendances de test (pytest), en plus de celles d'exécution.
FROM deps-runtime AS deps-test
RUN python - <<'PY' > requirements-test.txt
import tomllib
print("\n".join(tomllib.load(open("pyproject.toml", "rb"))["project"]["optional-dependencies"]["dev"]))
PY
RUN pip install --prefix=/install --only-binary=:all: -c constraints.txt -r requirements-test.txt

FROM base AS test
COPY --from=deps-test /install /usr/local
COPY . .
# Le code est normalement monté en lecture seule par le compose (pas de rebuild) ; la copie sert à `docker build` seul.
ENV PYTEST_ADDOPTS="-p no:cacheprovider"
CMD ["pytest", "-q"]

# Dernière étape = cible par défaut : l'image d'exécution.
FROM base AS api
COPY --from=deps-runtime /install /usr/local
COPY . .
RUN useradd --system --no-create-home app && chown -R app /srv/api
USER app

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
