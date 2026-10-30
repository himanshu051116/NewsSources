#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

EXPECTED_HEAD="0033_grounded_news_explainer"

echo "[1/7] Lockfile consistency"
uv lock --check --offline

echo "[2/7] Python compilation"
python -m compileall -q backend/src backend/tests backend/migrations

echo "[3/7] Unit/integration tests"
pytest -q

echo "[4/7] Alembic single-head check"
HEADS="$(PYTHONPATH=backend/src alembic -c backend/alembic.ini heads | awk '{print $1}')"
if [[ "$HEADS" != "$EXPECTED_HEAD" ]]; then
  echo "Expected Alembic head $EXPECTED_HEAD but found: $HEADS" >&2
  exit 1
fi

echo "[5/7] Offline migration SQL"
PYTHONPATH=backend/src alembic -c backend/alembic.ini upgrade head --sql >/tmp/newsintel-upgrade.sql

echo "[6/7] Release-tree integrity"
python scripts/release-integrity.py

echo "[7/7] Lint/type checks"
if python -c 'import ruff' >/dev/null 2>&1; then
  python -m ruff check backend/src backend/tests
else
  if [[ "${NEWSINTEL_STRICT_VALIDATION:-0}" == "1" ]]; then
    echo "ruff is required in strict release validation" >&2
    exit 1
  fi
  echo "[WARN] ruff is not installed in the active environment"
fi
if command -v mypy >/dev/null 2>&1; then
  mypy backend/src/newsintel
else
  if [[ "${NEWSINTEL_STRICT_VALIDATION:-0}" == "1" ]]; then
    echo "mypy is required in strict release validation" >&2
    exit 1
  fi
  echo "[WARN] mypy is not installed in the active environment"
fi

echo "Release validation completed."
