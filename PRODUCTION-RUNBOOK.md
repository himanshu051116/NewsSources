# News Intelligence 1.25 Production Runbook

## Scope
This is the final deployable single-host production/pilot topology. It continuously discovers sources, fetches and versions articles, enriches historical context, builds grounded event briefings, processes derived state, and serves the authenticated analyst UI.

For larger/high-availability deployments use managed PostgreSQL with PITR, replicated object storage and an external reverse proxy/ingress; do not treat one Docker host as disaster-recovery HA.

## 1. Host prerequisites
- Linux server with Docker Engine + Compose v2
- DNS A/AAAA record for `NEWSINTEL_DOMAIN`
- inbound TCP 80/443
- minimum recommended pilot: 8 vCPU, 16 GB RAM, 150+ GB SSD
- outbound HTTPS/DNS access to configured publishers/history providers

## 2. Secrets and configuration
```bash
cp .env.production.example .env.production
chmod 600 .env.production
$EDITOR .env.production
```
Replace every `CHANGE_ME`. Configure an OIDC issuer/client. Never enable development auth in production.

Validate configuration without starting the whole stack:
```bash
docker compose --env-file .env.production -f compose.production.yaml config
```

## 3. Build and migrate
```bash
docker compose --env-file .env.production -f compose.production.yaml build
docker compose --env-file .env.production -f compose.production.yaml up -d postgres qdrant minio minio-init
docker compose --env-file .env.production -f compose.production.yaml run --rm migrate
```

## 4. Start live application
```bash
docker compose --env-file .env.production -f compose.production.yaml up -d \
  api poller articles historical-enrichment briefings outbox recompute workspace-monitor caddy
```
If browser fallback is required:
```bash
docker compose --env-file .env.production -f compose.production.yaml --profile browser-renderer up -d browser-renderer
```

## 5. Seed launch sources
The bundled `config/live-source-pack.json` is a validation starter pack, not a blanket content-rights grant. Review each publisher's terms/licence and retention policy first.
```bash
docker compose --env-file .env.production -f compose.production.yaml exec api \
  newsintel-seed-sources --file config/live-source-pack.json
```

## 6. Verify
```bash
NEWSINTEL_PUBLIC_BASE_URL=https://your-domain.example ./scripts/production-smoke.sh
```
Then verify in the authenticated UI:
1. Source Operations shows healthy channels.
2. New articles arrive without manual fetch.
3. Historical enrichment contexts complete.
4. Event dossiers group related reporting.
5. `/events/<id>/briefing` shows a grounded explanation with evidence references.
6. No stale poll/article leases accumulate.

## 7. Operational acceptance gate
Do not call the deployment production-proven until it completes:
- 24-hour load/smoke run;
- 72-hour worker/restart soak;
- 7-day live-source trial across the approved launch source pack;
- restore drill from PostgreSQL backup/PITR;
- OIDC/MFA/access-role test;
- human review of extraction fidelity, event grouping, historical-match relevance and grounded-briefing citations.

The package now contains an automated acceptance recorder/evaluator. Run each stage from the project root after the production stack is healthy:
```bash
./scripts/production-acceptance.sh 24h
./scripts/production-acceptance.sh 72h
./scripts/production-acceptance.sh 7d
```
Each command writes timestamped NDJSON samples plus `report.json` and `report.md` under `acceptance-results/`. A non-PASS report exits non-zero. Low-volume trials are reported as `BLOCKED` rather than passing without enough evidence.

The evaluator measures:
- API readiness availability over every monitor interval, including failed/error intervals;
- candidate-level terminal processing success, excluding rejected non-article URLs and avoiding retry-attempt inflation;
- publication-to-first-discovery p95 only for records with usable publisher timestamps;
- historical-context completion within 10 minutes, counting only versions old enough to have consumed the full SLO window;
- grounded event-briefing coverage within 12 minutes using the same eligibility rule;
- worst observed stale poll/article lease age;
- publisher-level processed/failed terminal outcomes.

Default launch SLOs:
- feed/API priority discovery p95 <= 2 minutes when upstream provides timely feed entries;
- article processing/extraction terminal success >= 95% on the approved launch-source set;
- historical enrichment completion >= 95% within 10 minutes of article commit;
- grounded briefing completion >= 95% within 12 minutes of article commit;
- no stale worker lease older than 2x configured lease duration;
- API readiness availability >= 99.5% during pilot.

The automated gate intentionally does **not** certify publisher licensing, event-clustering correctness, historical relevance or factual-truth quality. Those require the human review step below.

### 7.1 Human quality review before launch
For each acceptance stage, sample reporting across every launch publisher and review at least:
1. extracted text against the original publisher page;
2. event assignment / accidental event merges;
3. historical links for temporal leakage or irrelevant matches;
4. briefing statements against their stored evidence references;
5. source-lineage/ownership reductions for obvious syndication;
6. corrections/retractions propagating into claim review state.

Record the reviewer, sampled IDs and findings alongside the automated acceptance report. A technically green SLO report does not override a material grounding or source-rights problem.

These are acceptance targets, not claims about this packaged build until measured in your environment.

## 8. Backup/restore
```bash
./scripts/production-backup.sh
./scripts/production-restore.sh backups/<stamp>/postgres.dump
```
Use infrastructure-native PostgreSQL PITR and replicated S3/object storage for real disaster recovery. Test restoration before launch.

## 9. Updating
1. backup;
2. pull/build new image;
3. run migrations;
4. run doctor;
5. restart workers/API;
6. run smoke checks;
7. keep previous image tag for rollback.

## 10. Incident rollback
- Search semantic rollout: use the existing Search Quality emergency pause.
- Source-specific crawler incident: disable the publisher/channel.
- Application release incident: restore previous image; never downgrade schema without an explicit tested migration/restore plan.
