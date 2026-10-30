#!/usr/bin/env bash
set -euo pipefail
BASE_URL="${1:-${NEWSINTEL_PUBLIC_BASE_URL:-}}"
[ -n "$BASE_URL" ] || { echo "usage: production-smoke.sh https://host" >&2; exit 2; }
check() { printf '%-35s' "$1"; curl -fsS --max-time 15 "$2" >/dev/null && echo ' OK'; }
check "liveness" "$BASE_URL/api/v1/health/live"
# Readiness can require auth depending on deployment, so run the in-container doctor as the authoritative schema/runtime check.
docker compose --env-file .env.production -f compose.production.yaml exec -T api newsintel-doctor
printf '%-35s' "containers"
docker compose --env-file .env.production -f compose.production.yaml ps --status running >/dev/null && echo ' OK'
echo "Smoke checks passed. Next: validate live-source ingestion counters and at least one event briefing in the authenticated UI."
