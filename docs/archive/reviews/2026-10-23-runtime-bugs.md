# Bug analysis and fixes — 23 October 2026

The confirmed runtime defects below were fixed and loaded into the local deployment at `http://127.0.0.1:8010/news`. The existing news database was retained. PostgreSQL regression tests use a separate `newsintel_audit_20261021` database and roll back their test data.

## Confirmed defects fixed

| Area | Failure | Fix and verification |
| --- | --- | --- |
| Article acquisition | Both fetch startup and pre-fetch rejection supplied `fetch_job_id` and `lease_version` to an ORM model that did not map those migrated columns. Jobs stayed leased and were repeatedly reclaimed; logs showed attempts above 100. | Map the existing columns. Verify real PostgreSQL fetch-run persistence and rejection/recovery. No new schema revision is needed. |
| Stored HTML snapshots | Article persistence and browser recovery called a missing `RawFetchArtifact.to_metadata()` method. | Implement JSON-safe metadata serialization and verify that a committed article version retains its raw snapshot reference. |
| Windows storage | Deep storage paths exceeded Windows' legacy path limit, failing with `FileNotFoundError`. Concurrent in-process writes also shared a temporary filename. | Use extended absolute Windows paths and unique temporary files with cleanup. Exercise a path longer than 260 characters. |
| Source discovery | Payload sniffing called `.casefold()` on bytes, breaking responses with missing or non-HTML content types. | Use byte-safe lowercase matching. Test HTML, JSON and RSS payloads without a content type. |
| Historical retrieval | Semantic-match scoring called undefined `_set_overlap` and `_title_entities` helpers. | Reuse the existing lexical-overlap and entity-phrase scorers. Verify scores and provenance preservation. |
| Benchmark export | Export referenced an undefined `command` and incorrectly applied evaluation-only semantic-runtime restrictions. | Remove the misplaced evaluation branch. Verify that an event benchmark exports without an embedding runtime. |
| Global and entity search | asyncpg could not prepare queries with null optional filters or an initial null pagination cursor. The live endpoints returned HTTP 500. | Bind SQL parameters with explicit types. Test default filters, selected entity filters and tied-score pagination against PostgreSQL. |
| Worker scheduling | Article, polling and historical workers claimed more jobs than they could start; queued tasks could lose their leases before receiving a processing slot. | Limit claims to processing capacity. Sequential monitoring and recompute workers claim one job at a time. |
| Article/polling lease integrity | Expired leases could be renewed or used for writes. Article mutations were not protected by row locks; run startup did not check the expected attempt version. | Check owner, version, state and expiry as applicable; lock article rows before mutation; reject expired heartbeats. Verify stale-writer rejection and reclaim in PostgreSQL. |
| Worker task cleanup | A database exception could escape `gather` while sibling tasks kept running, allowing work from one leasing round to overlap another. Unexpected article/polling failures could also disappear without a log. | Drain tasks before propagating failures and log unexpected failures. Test a failing task alongside an unfinished sibling. |
| Recompute recovery | A temporary database outage terminated the recompute worker. Reclaimed recompute jobs could also be overwritten by a stale attempt. | Add bounded database retry and lock/fence writes using owner, attempt count, state and expiry. Test outage recovery and stale attempts. |
| Scheduled monitoring | Alert keys used a run ID before SQLAlchemy had assigned it, producing `scheduled-search:None`. Monitoring failure handling could terminate on database errors. | Assign the run ID before creating its alert, check lease expiry and recover from database outages. Verify the run-to-alert key relationship. |
| Windows service control | Stale PID files could identify an unrelated application. Stopping a Windows venv launcher left its child Python process alive. API checks and startup arguments also ignored configured host/port. | Validate executable and recorded creation time, stop the verified process tree, honor configured API settings and wait for database readiness. Verify stale/reused PID handling and a live stop/start cycle. |
| Clean installation | Revision `0014_ownership_entities_calibration` exceeded Alembic's default `VARCHAR(32)` version column, preventing migration from an empty database. | Widen the version metadata column before recording the first long revision. Verify the complete migration chain through `0033_grounded_news_explainer`, online and as offline SQL. |
| Windows tests and setup | A multilingual fixture used the Windows default encoding. Python/uv discovery could return multiple executables as one command. | Read the fixture as UTF-8 and select one executable. |

## Validation

- **441 tests passed**, including five PostgreSQL integration tests and Windows-specific storage/process tests.
- Complete migration from an empty test database to the single head `0033_grounded_news_explainer`: passed.
- Every mapped ORM column exists in the migrated database: passed.
- Python compilation, dependency consistency, and checks for undefined names/redefinitions: passed.
- Generated JavaScript: five pages, ten inline script blocks, zero syntax errors.
- Live API sweeps: 75 routes before the final restart and 68 after it, with zero HTTP 5xx or transport failures. The final sweep returned 66 HTTP 200 responses and two expected HTTP 404 responses for a newly captured report's historical context and briefing, which had not yet been generated. The sampled report changed as live ingestion resumed. Results are recorded in `.run/audit/http-smoke.json`.
- Local API and seven workers restarted with the fixes; readiness checks passed.

Evidence files are in `.run/audit`, including `pytest-final.xml`, `http-smoke.json`, `migrations.sql` and `ruff-final.json`.

## Limits and remaining diagnostics

This report describes confirmed defects and the tested flows; it does not certify that every possible defect has been eliminated. Browser interaction was not revalidated because the browser tool previously failed. External provider acceptance, production identity-provider flows and sustained load/concurrency trials remain outside these checks.

The full Ruff configuration still reports 1,287 diagnostics, predominantly existing line-length/style findings (1,145 `E501` findings). The initial strict type-check also reported existing typing/stub issues. Those checks are **not** represented as clean. The runtime-critical undefined-name/redefinition checks pass, and their concrete crash paths were fixed.

To rerun the complete tests, set `NEWSINTEL_TEST_DATABASE_URL` to the dedicated audit database and run the virtual-environment Python with `-m pytest`. Use a new workspace-local `--basetemp` directory if the system temporary directory has incompatible permissions. Without that environment variable, the five database integration tests explicitly skip.
