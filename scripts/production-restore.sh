#!/usr/bin/env bash
set -euo pipefail
DUMP="${1:?usage: production-restore.sh path/to/postgres.dump}"
BACKUP_DIR="$(dirname "$DUMP")"
COMPOSE=(docker compose --env-file .env.production -f compose.production.yaml)
printf 'This replaces database contents and may overwrite raw artifacts. Type RESTORE to continue: '
read -r answer
[ "$answer" = RESTORE ] || { echo "Cancelled"; exit 1; }
"${COMPOSE[@]}" stop api poller articles historical-enrichment briefings outbox recompute workspace-monitor || true
"${COMPOSE[@]}" exec -T postgres sh -ec 'dropdb -U "$POSTGRES_USER" --if-exists "$POSTGRES_DB" && createdb -U "$POSTGRES_USER" "$POSTGRES_DB"'
cat "$DUMP" | "${COMPOSE[@]}" exec -T postgres sh -ec 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner'
if [ -d "$BACKUP_DIR/minio" ]; then
  "${COMPOSE[@]}" run --rm -v "$(cd "$BACKUP_DIR" && pwd)/minio:/backup:ro" --entrypoint /bin/sh minio-init -ec \
    'until mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"; do sleep 2; done; mc mb --ignore-existing local/${NEWSINTEL_OBJECT_STORE_BUCKET:-newsintel}; mc mirror --overwrite /backup local/${NEWSINTEL_OBJECT_STORE_BUCKET:-newsintel}'
fi
"${COMPOSE[@]}" run --rm migrate
"${COMPOSE[@]}" up -d api poller articles historical-enrichment briefings outbox recompute workspace-monitor
