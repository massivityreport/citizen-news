#!/usr/bin/env bash
# Lance les tests de l'API : construit l'image de test si besoin, démarre un PostgreSQL léger (tmpfs),
# exécute pytest, puis arrête PostgreSQL. Arguments = arguments de pytest.
#   scripts/test-api.sh                       # toute la suite
#   scripts/test-api.sh tests/test_auth.py    # un seul fichier
#   scripts/test-api.sh -k halving -x
set -u
cd "$(dirname "$0")/.."
docker compose --profile test run --rm api-test pytest -q "$@"
rc=$?
docker compose --profile test stop db-test >/dev/null 2>&1
docker compose --profile test rm -f db-test >/dev/null 2>&1
exit $rc
