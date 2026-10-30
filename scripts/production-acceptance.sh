#!/usr/bin/env bash
set -euo pipefail
PROFILE="${1:-24h}"
case "$PROFILE" in
  24h) HOURS=24 ;;
  72h) HOURS=72 ;;
  7d) HOURS=168 ;;
  *) echo "usage: production-acceptance.sh {24h|72h|7d}" >&2; exit 2 ;;
esac
INTERVAL="${NEWSINTEL_ACCEPTANCE_INTERVAL_SECONDS:-60}"
BASE_URL="${NEWSINTEL_ACCEPTANCE_BASE_URL:-http://127.0.0.1:8000}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR="acceptance-results/${STAMP}-${PROFILE}"
mkdir -p "$OUT_DIR"
SAMPLES="$OUT_DIR/samples.ndjson"
REPORT_JSON="$OUT_DIR/report.json"
REPORT_MD="$OUT_DIR/report.md"
TRIAL_START="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

echo "News Intelligence acceptance trial"
echo " profile:      $PROFILE"
echo " duration:     ${HOURS}h"
echo " interval:     ${INTERVAL}s"
echo " trial start:  $TRIAL_START"
echo " results:      $OUT_DIR"
echo

echo "Running monitor inside the API container. Keep this terminal/session alive for the trial window."
docker compose --env-file .env.production -f compose.production.yaml exec -T api \
  newsintel-acceptance monitor \
  --trial-start "$TRIAL_START" \
  --duration-hours "$HOURS" \
  --interval-seconds "$INTERVAL" \
  --base-url "$BASE_URL" > "$SAMPLES"

set +e
docker compose --env-file .env.production -f compose.production.yaml exec -T api \
  newsintel-acceptance evaluate --input - --profile "$PROFILE" --format json \
  < "$SAMPLES" > "$REPORT_JSON"
JSON_RC=$?
docker compose --env-file .env.production -f compose.production.yaml exec -T api \
  newsintel-acceptance evaluate --input - --profile "$PROFILE" --format markdown \
  < "$SAMPLES" > "$REPORT_MD"
MD_RC=$?
set -e

echo
echo "Acceptance report: $REPORT_MD"
cat "$REPORT_MD"
if [ "$JSON_RC" -ne 0 ] || [ "$MD_RC" -ne 0 ]; then
  echo "Acceptance gate did not PASS. Inspect $OUT_DIR before launch." >&2
  exit 1
fi
echo "Acceptance gate PASS for $PROFILE."
