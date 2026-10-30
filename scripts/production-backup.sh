#!/usr/bin/env bash
set -euo pipefail
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="${1:-backups/$STAMP}"
mkdir -p "$DEST/minio"
COMPOSE=(docker compose --env-file .env.production -f compose.production.yaml)
"${COMPOSE[@]}" exec -T postgres sh -ec 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$DEST/postgres.dump"
"${COMPOSE[@]}" run --rm -v "$(pwd)/$DEST/minio:/backup" --entrypoint /bin/sh minio-init -ec \
  'until mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"; do sleep 2; done; mc mirror --overwrite local/${NEWSINTEL_OBJECT_STORE_BUCKET:-newsintel} /backup'
cat > "$DEST/README.txt" <<TXT
Backup created: $STAMP
- postgres.dump: logical PostgreSQL dump
- minio/: immutable/raw object-store artifacts
Qdrant is a derived semantic index and can be rebuilt from canonical article versions. For production DR, also enable provider-native PostgreSQL PITR and object-store replication/versioning.
TXT
find "$DEST" -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > "$DEST/SHA256SUMS"
echo "Backup written to $DEST"
