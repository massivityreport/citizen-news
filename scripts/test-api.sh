#!/usr/bin/env bash
# Lance les tests de l'API : construit l'image de test si besoin, démarre un PostgreSQL léger (tmpfs),
# exécute pytest, puis arrête PostgreSQL (même sur Ctrl-C ou kill). Arguments = arguments de pytest.
#   scripts/test-api.sh                       # toute la suite
#   scripts/test-api.sh tests/test_auth.py    # un seul fichier
#   scripts/test-api.sh -k halving -x
set -u
cd "$(dirname "$0")/.."

cleanup() {
  trap - EXIT INT TERM
  docker compose --profile test stop db-test >/dev/null 2>&1
  docker compose --profile test rm -f db-test >/dev/null 2>&1
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

docker compose --profile test run --rm api-test pytest -q "$@"
