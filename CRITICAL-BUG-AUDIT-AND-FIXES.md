# News Intelligence v1.25 — Critical bug audit and remediation

**Candidate:** v1.25 source as supplied in `news-intelligence-1.25.0-live-qa-reviewed.zip`  
**Scope:** ingestion and worker reliability, historical enrichment, evidence-driven event briefings, safe external URL handling, UI browser behavior, production validation boundaries.

## Findings fixed

| Severity | Subsystem | Reproduced defect / risk | Fix |
|---|---|---|---|
| High | Grounded-briefing queue | Expired `running` jobs were not eligible for leasing, leaving briefings stranded after a worker crash. | Lease query also reclaims expired `running` jobs with row-level `SKIP LOCKED` and increments the fencing version. |
| High | Grounded-briefing lease | A worker could heartbeat or complete its job after its lease had expired but before ownership was reassigned. | Require `running` status, current owner/version and unexpired lease for heartbeat/success writes. |
| High | Historical enrichment | A stale historical worker could persist a context or failure after another attempt had reclaimed the job, potentially replacing newer evidence. | Validate the locked job row before any context/dependency/queue write; fence with exact owner and attempt start timestamp, state and unexpired lease. Stale attempts are discarded. |
| High | Historical enrichment | Slow live historical searches had no worker heartbeat; their lease could expire during external provider calls. | Added periodic lease renewal during processing and safe handling of lost leases. |
| Medium | Briefing backfill | Two briefing workers could both select a missing event and cause a unique-constraint failure. | Backfill now uses `ON CONFLICT DO NOTHING`, counting only inserted rows. |
| Medium | Briefing refresh | Requeue counters counted upserts skipped due to an active lease; retry budget accumulated across distinct newer evidence snapshots. | Count actual changed rows, reset the attempt budget on a fresh requeue, clear stale lease fields without changing an active lease. |
| High | Briefing citations | A supported claim could show no supporting source among the first 8 citations if many more recent context/contradiction links came first. | Prioritize traceable supporting and primary evidence before other linked records. Existing support/verdict consistency check remains. |
| Medium | Historical explanation | Change counts from a single latest article historical context could be phrased as event-wide totals; missing contexts were rendered as `unknown / zero changes`. | Explicitly identify article-level comparison scope, report missing historical comparisons as unavailable, and disclose the 30-report sample cap. |
| Medium | Historical citations | Mixed historical channels were not globally chronological, tracking-URL duplicates could repeat, and future-dated records could be displayed. | Deterministic historical citation ordering, URL normalization and deduplication, strict cutoff exclusion for known dates, and honest publication-vs-observation labels. Undated references remain marked unknown. |
| Medium | Historical link parser | A malformed port in an external URL could raise `ValueError` and interrupt downstream processing; IPv6 reconstructions could be malformed. | Fail closed on invalid ports, retain valid bracketed IPv6 hosts and add regression tests. |

## What was actually tested

- **411/411 unit tests passed**, including **7 newly added tests** (worker fencing/reclaim contracts, historical chronology/date/cutoff, citation ordering and malformed URL normalization).
- All modified Python code compiles.
- Real server-generated JavaScript checked with Node on five core pages (10 script blocks): passed.
- Chromium/Playwright source-replay browser suite: **28/28 passed** on desktop and mobile with no browser JavaScript errors.
- Local replay extraction: 2 source snapshots, 8 *candidate* claims (not verified facts).
- Alembic remains at the single head `0033_grounded_news_explainer`; no schema change required.
- `uv lock --check --offline` passed.

## Critical limitations — NOT passed or not run

1. **Full PostgreSQL/asyncpg integration:** `asyncpg` is absent in this sandbox. One no-DB integration test passes; the app-lifespan integration test stops during driver import. PostgreSQL concurrency transactions, migrations on a populated database and full worker recovery still need to be tested in Docker.
2. **Docker execution:** Docker is absent; production images and Compose cannot be started in this environment. YAML parsing is not the same as running the services.
3. **Real, permitted publisher crawling:** direct networking for the application sandbox is restricted. Browser QA uses explicitly marked, recorded-source replay data. No claim of successful live ingestion is made.
4. **24-hour / 72-hour / 7-day source acceptance:** not run here. Run the included acceptance harness against real approved publishers.
5. **Security/load completeness:** this is a targeted deep audit, not a guarantee of zero undiscovered bugs, formal penetration test, accessibility certification, or exhaustive evaluation across publishers and languages.

## Recommended next verification in a real deployment

1. Start Compose against a disposable/staging PostgreSQL database, run migrations, health/doctor and create a test event.
2. Kill a briefing worker while it owns a job; let the lease expire and verify another worker finishes it exactly once.
3. Kill a historical enrichment worker during external provider retrieval, recover the job and verify a stale earlier worker cannot overwrite the later context.
4. Run a 24-hour approved-source trial. Verify article versions, historical cutoffs, source citations and unsupported/ambiguous claims manually.
5. Continue the 72-hour and 7-day readiness trials, test backup/restore and review source licensing and authentication before public release.

**Status:** Code and QA-replay defects above fixed; **live production acceptance remains open**. A successful test suite must not be described as proof of live newsroom-grade factual correctness.
