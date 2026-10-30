#!/usr/bin/env bash
set -euo pipefail

workspace="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$workspace"

if command -v uv >/dev/null 2>&1; then
  run=(uv run --extra dev --extra extractors --frozen)
else
  run=(python)
fi

"${run[@]}" -m compileall -q backend/src backend/tests
"${run[@]}" -m ruff check backend/src backend/tests
"${run[@]}" -m mypy backend/src/newsintel
PYTHONPATH=backend/src "${run[@]}" -m pytest \
  --cov=backend/src/newsintel \
  --cov-branch \
  --cov-report=term-missing \
  --cov-fail-under=60
"${run[@]}" -m alembic -c backend/alembic.ini heads
