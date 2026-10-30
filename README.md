> **Latest reader and freshness upgrade:** see [READER-UI-FRESHNESS-AUDIT-2026-10-31.md](READER-UI-FRESHNESS-AUDIT-2026-10-31.md) for simpler reading pages, publication-date checks, article identity fixes and verification.
>
> **Previous reader upgrade:** see [READER-MVP-UPGRADE-2026-10-28.md](READER-MVP-UPGRADE-2026-10-28.md) for remembered reading choices, cleaner excerpts, bounded correction refresh, faster briefs and validation.
>
> **Earlier MVP assessment:** see [MVP-CRITICAL-REVIEW-2026-10-27.md](MVP-CRITICAL-REVIEW-2026-10-27.md) for the critical functionality review and the original findings.
>
> **Earlier brief-quality upgrade:** see [NEWS-BRIEF-QUALITY-2026-10-23.md](NEWS-BRIEF-QUALITY-2026-10-23.md) for daily/weekly selection, source-text cleanup, reading limits and live verification.
>
> **Publisher-fetching audit:** see [PUBLISHER-FETCH-AUDIT-2026-10-23.md](PUBLISHER-FETCH-AUDIT-2026-10-23.md) for acquisition fixes, 480 passing tests, live browser/database verification and remaining processing limits.
>
> **Earlier local runtime audit:** see [BUG-ANALYSIS-2026-10-23.md](BUG-ANALYSIS-2026-10-23.md) for confirmed fixes, 441 passing tests, live API checks and remaining validation limits.
>
> **Earlier QA/bugfix audit:** see [CRITICAL-BUG-AUDIT-AND-FIXES.md](CRITICAL-BUG-AUDIT-AND-FIXES.md).

# News Intelligence Platform

An event-centric news intelligence system with recall-optimized global acquisition, primary-source trace-back, historical context, claim-level verification, propagation analysis, geographic intelligence, knowledge-graph exploration, and evidence-backed assessments, briefings, and research.

This repository now contains the first production-oriented backend slices: acquisition
setup, discovery polling, frontier admission, article fetching, article extraction,
article versioning, and read APIs for ingested articles/events.

## Design documents

- [Daily & weekly news briefs and custom streams](docs/NEWS_DIGESTS.md)
- [System architecture](docs/ARCHITECTURE.md)
- [Event-centric intelligence architecture](docs/EVENT_INTELLIGENCE_ARCHITECTURE.md)
- [Recall-optimized acquisition architecture](docs/ACQUISITION_ARCHITECTURE.md)
- [Implementation roadmap](docs/IMPLEMENTATION_PLAN.md)
- [Critical implementation guardrails](docs/IMPLEMENTATION_GUARDRAILS.md)
- [Zero-cost local AI strategy](docs/LOCAL_AI_STRATEGY.md)
- [Module synchronization contract](docs/MODULE_SYNCHRONIZATION.md)
- [Historical research providers](docs/HISTORICAL_RESEARCH.md)
- [Current stage and development roadmap](docs/CURRENT_STAGE_AND_ROADMAP.md)
- [Source Fabric 0.3.0 upgrade](docs/SOURCE_FABRIC_UPGRADE_0.3.0.md)
- [Evidence & Historical Intelligence 0.4.0 upgrade](docs/EVIDENCE_HISTORICAL_UPGRADE_0.4.0.md)
- [Primary Evidence & Temporal Knowledge 0.5.0 upgrade](docs/PRIMARY_EVIDENCE_TEMPORAL_UPGRADE_0.5.0.md)
- [Evidence Graph & Reliability 0.6.0 upgrade](docs/EVIDENCE_GRAPH_RELIABILITY_UPGRADE_0.6.0.md)
- [Provenance, Entity & Calibration 0.7.0 upgrade](docs/PROVENANCE_CALIBRATION_UPGRADE_0.7.0.md)
- [Accuracy & Evidence Orchestration 0.8.0 upgrade](docs/ACCURACY_ORCHESTRATION_UPGRADE_0.8.0.md)
- [Validation & Propagation 0.9.0 upgrade](docs/VALIDATION_PROPAGATION_UPGRADE_0.9.0.md)
- [Production Readiness 1.0.0 upgrade](docs/PRODUCTION_READINESS_UPGRADE_1.0.0.md)
- [Browser Recovery & Dependency Recompute 1.5.0 upgrade](docs/BROWSER_RENDERING_RECOMPUTE_UPGRADE_1.5.0.md)
- [Adaptive Extraction & Semantic History 1.4.0 upgrade](docs/ADAPTIVE_EXTRACTION_SEMANTIC_UPGRADE_1.4.0.md)
- [Coherence & Retrieval 1.3.0 upgrade](docs/COHERENCE_RETRIEVAL_UPGRADE_1.3.0.md)
- [Historical Context Quality 1.2.0 upgrade](docs/HISTORICAL_CONTEXT_QUALITY_1.2.0.md)
- [Automatic Historical Enrichment 1.1.0 upgrade](docs/AUTOMATIC_HISTORICAL_ENRICHMENT_1.1.0.md)
- [Historical Enrichment 1.1.0 release notes](docs/HISTORICAL_ENRICHMENT_UPGRADE_1.1.0.md)
- [Accuracy & Source Fidelity 1.7.0 upgrade](docs/ACCURACY_SOURCE_FIDELITY_UPGRADE_1.7.0.md)
- [Accuracy Measurement & Adjudication 1.8.0 upgrade](docs/ACCURACY_MEASUREMENT_UPGRADE_1.8.0.md)
- [Blind adjudication & failure attribution 1.9.0](docs/BLIND_ADJUDICATION_1.9.0.md)
- [Accuracy validation program 1.10.0](docs/ACCURACY_VALIDATION_PROGRAM_1.10.0.md)
- [Frontend correctness 1.11](NEWS-INTELLIGENCE-1.11-UI-CORRECTNESS-PASS.md)
- [Search, Command Center & Event Dossier 1.12](NEWS-INTELLIGENCE-1.12.0-SEARCH-EVENT-DOSSIER.md)
- [Lineage & Claim Investigation 1.13](NEWS-INTELLIGENCE-1.13.0-LINEAGE-CLAIM-INVESTIGATION.md)
- [Article Evolution & Correction Intelligence 1.14](NEWS-INTELLIGENCE-1.14.0-ARTICLE-EVOLUTION-CORRECTIONS.md)
- [Analyst Workspace 1.15](NEWS-INTELLIGENCE-1.15.0-ANALYST-WORKSPACE.md)
- [Collaboration & Scheduled Monitoring 1.16](NEWS-INTELLIGENCE-1.16.0-COLLABORATION-MONITORING.md)
- [Indexed Search Infrastructure 1.17](NEWS-INTELLIGENCE-1.17.0-INDEXED-SEARCH.md)
- [Search Quality & Entity Intelligence 1.18](NEWS-INTELLIGENCE-1.18.0-SEARCH-QUALITY-ENTITY-INTELLIGENCE.md)
- [Entity Resolution & Benchmark Expansion 1.19](NEWS-INTELLIGENCE-1.19.0-ENTITY-RESOLUTION-BENCHMARK-EXPANSION.md)
- [Multilingual Retrieval & Controlled Reranking 1.20](NEWS-INTELLIGENCE-1.20.0-MULTILINGUAL-RERANKING.md)
- [Search Promotion Gates & Production Evaluation 1.21](NEWS-INTELLIGENCE-1.21.0-SEARCH-PROMOTION-GATES.md)
- [Production Search Deployment Control 1.22](NEWS-INTELLIGENCE-1.22.0-SEARCH-DEPLOYMENT-CONTROL.md)
- [Live Pipeline Hardening 1.23](NEWS-INTELLIGENCE-1.23.0-LIVE-PIPELINE-HARDENING.md)
- [Grounded News Explainer 1.24](NEWS-INTELLIGENCE-1.24.0-GROUNDED-NEWS-EXPLAINER.md)
- [Final Production Release 1.25](NEWS-INTELLIGENCE-1.25.0-FINAL-PRODUCTION-RELEASE.md)


## Accuracy measurement workflow

News Intelligence intentionally keeps three accuracy dimensions separate instead of publishing one blended "news accuracy" percentage:

1. **Publisher-page extraction fidelity** — whether the stored headline, canonical URL, publication time, body and numeric facts match the publisher page.
2. **Event-link accuracy** — whether reports about the same real-world event are joined without over-merging different incidents.
3. **Claim-verification accuracy and coverage** — performance on externally adjudicated benchmark claims, including abstention/coverage and high-confidence error rates.

Useful local commands on Windows:

```powershell
.\scripts\accuracy-audit.ps1 -Url "https://publisher.example/story" -Summary -Json
.\scripts\event-benchmark.ps1 -Json

# Recommended blind factual-verification benchmark workflow.
.\scripts\verification-benchmark.ps1 -Mode sample -BenchmarkSet local-held-out-v2 -Limit 200 -Seed 20260824
.\scripts\verification-benchmark.ps1 -Mode review-sheet -BenchmarkSet local-held-out-v2 -ReviewerKey reviewer-a -Path .\review-a.jsonl
.\scripts\verification-benchmark.ps1 -Mode review-sheet -BenchmarkSet local-held-out-v2 -ReviewerKey reviewer-b -Path .\review-b.jsonl
# Each reviewer independently fills adjudicated_label/adjudication_source.
.\scripts\verification-benchmark.ps1 -Mode review-import -BenchmarkSet local-held-out-v2 -ReviewerKey reviewer-a -Path .\review-a.jsonl
.\scripts\verification-benchmark.ps1 -Mode review-import -BenchmarkSet local-held-out-v2 -ReviewerKey reviewer-b -Path .\review-b.jsonl
.\scripts\verification-benchmark.ps1 -Mode agreement -BenchmarkSet local-held-out-v2
.\scripts\verification-benchmark.ps1 -Mode finalize -BenchmarkSet local-held-out-v2
```

If reviewers disagree, export `-Mode adjudicator-sheet`, have a separate adjudicator review those cases, import with `-Role adjudicator`, then finalize again. Analysts can inspect benchmark, agreement and diagnostic results at `/accuracy`. Benchmark results apply only to the adjudicated dataset and are not a universal factual-accuracy claim.

## Proposed stack

- Python 3.12+ and FastAPI
- PostgreSQL for canonical structured data
- PostGIS for geographic intelligence
- Optional Qdrant-derived vector index for local semantic historical retrieval
- S3-compatible object storage for raw and extracted artifacts
- Optional Redis profile reserved for a future event-bus/cache topology
- Kafka-compatible event streaming in the production topology
- Shared server-rendered FastAPI intelligence UI today; a separate typed frontend remains an optional future deployment choice
- Optional Neo4j projection when measured multi-hop graph workloads justify it

The implementation begins as a modular monolith with independently scalable API and worker processes. Service boundaries are explicit so high-load components can be separated later without rewriting the domain model.

## Current implementation

Phase 1 development has started. The repository currently contains:

- a FastAPI application with liveness and database-readiness endpoints;
- PostgreSQL/PostGIS persistence models and the initial Alembic migration;
- RSS, Atom, JSON Feed, XML sitemap, gzip sitemap, Google News sitemap parsing, and bounded HTML syndication-directory expansion;
- WebSub hub discovery with hub/self metadata retained on validated feed channels;
- an SSRF-aware bounded HTTP fetcher with conditional request support;
- a robots-aware crawl-policy wrapper with per-origin policy caching and process-local per-host request budgets;
- publisher-aware URL canonicalization and fingerprints;
- listing-page link-set change detection;
- auditable distributed-frontier priority calculations;
- provisional/candidate/confirmed event-assignment policy;
- transactional publisher/channel/discovery orchestration;
- versioned integration-event envelopes, transactional outbox, and consumer inbox;
- idempotent cross-channel discovery synchronization;
- lease-based asynchronous RSS/Atom/sitemap polling;
- conditional requests, `304 Not Modified` handling, adaptive scheduling, and failure backoff;
- persisted poll-run metrics and automatic sitemap-index expansion;
- a separate article-processing worker that leases URL candidates from the frontier;
- automatic per-version historical enrichment queued in the article commit transaction, with ranked/deduplicated same-event history, indexed full-corpus retrieval, exact claim-family history, internal/external matches, and late-history reconciliation;
- a durable article-processing state machine with explicit stages for queued,
  leased, fetching, fetched, extracting, extracted, validated, persisting,
  completed, rejected, retryable failure, and permanent failure;
- adaptive HTML article extraction using JSON-LD, bounded hydration-state recovery, OpenGraph/canonical metadata, publisher extraction profiles, and conservative visible-text heuristics;
- optional per-publisher browser-render recovery through an isolated localhost renderer with approved-domain subresource controls;
- generalized dependency tracking and stale/recompute jobs for derived historical contexts after upstream corrections or evidence changes;
- immutable article versions with extraction method, warnings, content hash,
  fetch-run provenance, and redirect metadata;
- publisher-page extraction fidelity checks for headline, canonical URL, publication time, structured-body coverage and numeric retention, explicitly separated from factual truth;
- a `newsintel-accuracy-audit` / `scripts/accuracy-audit.ps1` live audit command for real publisher URLs;
- structured multilingual lexical event matching v4 that compares incoming articles against active event
  records using Unicode token/action overlap, contextual numeric anchors, real event-type compatibility,
  entity/identifier overlap, temporal/geographic compatibility, containment, and gated strong-anchor conjunctions;
- existing-event linking, provisional new-event creation, and stored assignment
  feature scores for newly ingested articles;
- article fetch-run audit records and retry/terminal-failure tracking;
- structured article-worker logs for fetch, snapshot, extraction, validation,
  persistence flush, database commit, retry scheduling, dead-lettering, and final
  job completion;
- a local transactional outbox relay worker that marks committed outbox events as
  published idempotently through the consumer inbox;
- deterministic atomic claim extraction with claim typing, normalized quantities/dates,
  checkability, expected primary-evidence classes, and revision-tolerant claim-family keys;
- claim/evidence/verification lineage tables with origin evidence links;
- evidence-readiness article quality profiles that explicitly do not masquerade as truth scores;
- passage-level evidence candidate matching with numeric/temporal conflict detection;
- primary-evidence requirement plans persisted as auditable evidence-search runs;
- an administrator-configured evidence-authority registry that validates primary-source domain/class scope before granting primary-evidence weight;
- passage stance assessment with temporal-update detection so different as-of values are not automatically treated as contradictions;
- durable evidence-passage evaluation history with exact passage hashes, temporal relations and authority provenance;
- evidence-weighted claim verification with lineage deduplication and registry-validated primary-evidence weighting;
- specialized CKAN, Socrata and field-scoped JSON evidence-authority adapters behind the same authority-domain/SSRF/robots controls;
- ownership-aware and explicit circular-sourcing independence caps that affect corroboration weight without changing evidence stance;
- canonical entity/alias resolution with ambiguity-safe temporal graph reuse;
- indexed cross-event temporal-knowledge search with as-of filtering;
- externally adjudicated confidence-calibration benchmarks with Brier score and expected calibration error;
- benchmark v3 classification metrics with per-label precision/recall/F1, confusion matrices, high-confidence error rates and selective accuracy/coverage;
- benchmark corpus split-hygiene auditing for train/dev/test leakage, duplicate cases and adjudicator coverage;
- bounded multi-authority evidence orchestration that persists required classes, authority-selection rationale and uncovered evidence classes;
- immutable per-verification reproducibility manifests with claim/article hashes, evidence hashes, authority snapshots, retrieval body hashes, conflict/stopping context and code version;
- bounded correction/retraction dependency propagation across legacy article evidence links and passage-level evidence evaluations, with downstream review flags but no automatic verdict mutation;
- persisted production-readiness assessments combining current schema identity, held-out benchmark gates, verification-manifest coverage, critical review state and active evidence-authority availability;
- v1.0 schema-aware readiness/doctor checks, request IDs/server timing, correction-review/manifest operational metrics, strict release validation, and a bounded deployment smoke/load probe;
- lineage-deduplicated claim conflict-resolution history that preserves unresolved primary-source conflict and temporal evolution;
- provenance-preserving canonical-entity external identifiers with conflict-safe namespace linking;
- timestamped ownership-provenance evidence records for reproducible source-independence analysis;
- as-of temporal knowledge-graph neighborhood traversal for graph-backed historical research;
- content-lineage fingerprints persisted on article versions for syndication analysis;
- article-version diffs, claim revision histories, and event-observation timelines;
- claim confidence histories that preserve each evidence state instead of rewriting prior conclusions;
- trackable event commitments/outcomes for promise-vs-outcome and deadline analysis;
- as-known-then event knowledge snapshots that prevent later evidence from leaking into earlier historical states;
- local historical corpus search over immutable stored article versions;
- initial `not_checkable` claim verification records when independent evidence has
  not yet been retrieved, with reasoning traces and confidence-factor placeholders
  stored transparently rather than invented;
- publisher onboarding that discovers RSS/Atom/JSON Feed endpoints from HTML alternate
  links and HTTP Link headers, sitemap declarations from `robots.txt`, expanded common
  feed/sitemap paths, scored homepage section links, and optional manual fallback endpoints;
- JSON-LD `NewsArticle`/`Article` discovery for publisher pages whose article URLs are too
  short or opaque for URL-shape rules alone, while retaining asset and recency safeguards;
- persistent publisher-domain and robots-policy provenance through the 0.3.0 Source Fabric
  registry migration;
- per-publisher source-health and channel-contribution audit APIs for measuring channel
  reliability, unique discoveries and first-discovery wins;
- quarantined external source-candidate inference from article citations/links, with no
  automatic crawl activation;
- fetch job records and fetch scheduling endpoints that queue discovery work for the
  poller instead of doing extraction inside HTTP requests;
- a persistent analyst workspace with private investigations, tracked event/article/claim items, analyst notes, saved searches, watchlists, derived correction/review alerts, alert acknowledgements, and reproducible JSON evidence manifests;
- one-step workspace handoff from Event Dossiers, Article Intelligence and Claim Investigation, plus saved corpus searches that restore their complete indexed-search filter set;
- controlled investigation collaboration with owner/editor/reader access, auditable case activity, and durable scheduled saved-search monitoring;
- ranked PostgreSQL full-text intelligence search with weighted GIN indexes, exact first-page corpus counts, language/publisher/lifecycle/date filters, and snapshot-bound keyset pagination;
- multilingual-safe search query normalization with language-neutral FTS for Hindi/other scripts, indexed English morphology fallback for Latin queries, and suggestion-only alias/publisher/event query assistance;
- labelled lexical-vs-hybrid article reranking experiments that reuse the opt-in local Ollama/Qdrant article index without changing production search or injecting semantic-only results;
- a local `/news-sources` dashboard for adding sources, fetching one/all publishers,
  polling fetch progress, viewing source health, and visually browsing extracted
  article cards;
- recent-news URL classification before frontier admission: by default only
  article-like URLs with publication timestamps from the last 48 hours are admitted.
  Navigation pages such as categories, topics, tags, search, archives, feeds, and
  media assets are rejected, while story-bearing formats such as liveblogs,
  explainers, investigations, fact checks, individual video reports, and photo
  stories are admitted with an explicit `url_type`;
- per-channel poll cap for newly admitted URLs, defaulting to 200, tunable through
  `NEWSINTEL_MAX_NEW_URLS_PER_CHANNEL_POLL`;
- read APIs for article lists, article details, and event details;
- status and metrics endpoints for committed article count, queue depth, oldest
  pending candidate, candidate stages, pending outbox events, and migration revision;
- unit and API integration tests;
- a local zero-cost service topology for PostgreSQL/PostGIS, MinIO, and Qdrant, with Redis available only through the optional `event-bus` Compose profile;
- authenticated historical search across GDELT and optionally configured Guardian,
  New York Times, NewsAPI, and Google Fact Check providers;
- known-URL archive lookup through Internet Archive Wayback and Common Crawl;
- a `/historical-research` analyst page with per-provider status and safe external-link
  rendering.

Model-backed retrieval remains disabled by default. When explicitly configured with a local Ollama embedding model, Qdrant is used only as a rebuildable semantic-history index; PostgreSQL remains the canonical source of truth and no paid/remote AI fallback is used.

## Development setup

Windows PowerShell (first run):

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\bootstrap.ps1
.\scripts\services.ps1 init
.\scripts\run-platform.ps1 start
```

`bootstrap.ps1` now creates `.env` from `.env.example` when missing and creates a local-only `.env.local` with development authentication enabled. Existing files are never overwritten. The base Docker setup starts PostgreSQL only; Qdrant starts when semantic history is enabled and MinIO starts when S3 artifact storage is selected.

Run the API:

```powershell
.\.venv\Scripts\python.exe -m uvicorn newsintel.main:app --app-dir backend/src
```

The liveness endpoint is `GET http://127.0.0.1:8010/api/v1/health/live`.
Swagger UI is available at `http://127.0.0.1:8010/docs`.

Useful local service commands:

```powershell
.\scripts\services.ps1 status
.\scripts\services.ps1 logs
.\scripts\services.ps1 migrate
.\scripts\services.ps1 doctor
.\scripts\services.ps1 down
```

Start the full local platform with one command:

```powershell
.\scripts\run-platform.ps1 start
```

Check or stop those local processes:

```powershell
.\scripts\run-platform.ps1 status
.\scripts\run-platform.ps1 logs
.\scripts\run-platform.ps1 restart
.\scripts\run-platform.ps1 stop
```

The news workspace is available at:

```text
http://127.0.0.1:8010/news
```

Source operations remain available at `http://127.0.0.1:8010/news-sources`.

## Historical research setup

Keyless historical providers work immediately. Optional provider keys must be stored in
`.env` or a deployment secret manager and must never be committed:

```env
NEWSINTEL_GUARDIAN_API_KEY=
NEWSINTEL_NEW_YORK_TIMES_API_KEY=
NEWSINTEL_NEWS_API_KEY=
NEWSINTEL_GOOGLE_FACT_CHECK_API_KEY=
```

Approved analysts can use `http://127.0.0.1:8010/historical-research`. The API endpoints
are `POST /api/v1/historical/search` and
`POST /api/v1/historical/archives/lookup`. Provider capabilities and limitations are
documented in [Historical research providers](docs/HISTORICAL_RESEARCH.md).

## Run it like a normal Windows app

After the first setup, you do not need to keep typing terminal commands.

Portable launchers are included in the project folder:

- `Start-News-Intelligence.vbs` starts Docker if needed, starts the API, poller,
  article worker, historical-enrichment worker and outbox relay, then opens the News Sources dashboard.
- `Open-News-Dashboard.vbs` opens the dashboard.
- `Stop-News-Intelligence.vbs` stops the local app services and Docker Compose
  infrastructure without deleting stored data.

For Desktop icons, run this once from PowerShell:

```powershell
.\scripts\install-windows-shortcuts.ps1
```

This creates:

- **News Intelligence - Start**
- **News Intelligence - Stop**
- **News Intelligence - Dashboard**
- **News Intelligence - Status**

The first start may take a little longer because Docker Desktop, PostgreSQL, Qdrant, MinIO, migrations, the API, and workers all need to become ready. Redis is started only when the optional `event-bus` Compose profile is requested.
Launcher logs are written to:

```text
.run/logs/desktop-launcher.log
```

Recent article filtering can be tuned with:

```env
NEWSINTEL_RECENT_ARTICLE_WINDOW_HOURS=48
NEWSINTEL_MAX_NEW_URLS_PER_CHANNEL_POLL=200
NEWSINTEL_MAX_NEW_URLS_PER_PUBLISHER_FETCH=300
NEWSINTEL_MAX_NEW_URLS_PER_FETCH_JOB=2000
NEWSINTEL_MAX_ACTIVE_CHANNELS_PER_PUBLISHER=25
NEWSINTEL_DISCOVERY_RECOVERY_WINDOW_DAYS=7
NEWSINTEL_INITIAL_BACKFILL_DAYS=3
NEWSINTEL_MAX_RETRIES=3
NEWSINTEL_WORKER_LEASE_SECONDS=120
NEWSINTEL_DEAD_LETTER_AFTER_ATTEMPTS=3
NEWSINTEL_ARTICLE_FETCH_RETRY_JITTER_RATIO=0.15
```

### Article processing success semantics

The article worker treats each step separately. Downloading a page or extracting text
is not final article-processing success. A URL candidate is only counted as completed
after PostgreSQL has committed:

1. the `articles` row;
2. the immutable `article_versions` row;
3. event assignment or provisional event creation;
4. extracted claims, origin evidence links, and initial verification records when
   claims exist;
5. candidate state and processing-stage metadata;
6. transactional outbox events.

URL candidates also store a durable `url_type` classification, currently including
`standard_article`, `breaking_news`, `liveblog`, `explainer`, `analysis`, `opinion`,
`investigation`, `fact_check`, `press_release`, `video_report`, `photo_story`, and
navigation/rejection types such as `section_page`, `topic_page`, `tag_page`,
`search_page`, `archive_page`, `homepage`, and `invalid_page`. The classifier has
publisher-aware rules for The Hindu, Al Jazeera, Reuters, Indian Express, and BBC,
and the value is included in discovery outbox payloads for auditability.

Look for these logs in `.run/logs/articles.out.log`:

```text
extraction_succeeded          # extraction-only, not a committed article
database_flush_succeeded      # DB accepted pending writes inside transaction
database_commit_succeeded     # transaction committed
article_job_completed         # final durable success
database_commit_failed        # persistence failed; job is retried/dead-lettered
article_job_retry_scheduled
article_job_dead_lettered
```

The durable candidate processing stages are:

```text
discovered -> admitted -> queued -> leased -> fetching -> fetched ->
extracting -> extracted -> validated -> persisting -> persisted -> completed
```

Terminal or exceptional stages:

```text
partial
rejected
retryable_failure
permanent_failure
```

`GET /api/v1/articles` only returns committed articles.

### Status, metrics, and proof of persistence

Use these after starting the platform:

```powershell
Invoke-WebRequest http://127.0.0.1:8010/api/v1/status -UseBasicParsing
Invoke-WebRequest http://127.0.0.1:8010/api/v1/metrics -UseBasicParsing
Invoke-WebRequest "http://127.0.0.1:8010/api/v1/articles?limit=5" -UseBasicParsing
Select-String -Path .run\logs\articles.out.log -Pattern "database_commit_succeeded"
Select-String -Path .run\logs\articles.out.log -Pattern "article_job_completed"
```

The dashboard should show extracted article cards at:

```text
http://127.0.0.1:8010/news-sources
```

### Safe development cleanup command

Dry-run stale invalid BBC-like backlog cleanup:

```powershell
.\.venv\Scripts\python.exe -m newsintel.maintenance.cleanup_old_jobs --publisher BBC --older-than-hours 48 --invalid-only
```

Apply the cleanup safely:

```powershell
.\.venv\Scripts\python.exe -m newsintel.maintenance.cleanup_old_jobs --publisher BBC --older-than-hours 48 --invalid-only --apply
```

This marks old pending invalid URL candidates as rejected and marks stale pending
fetch jobs completed. It does not delete publishers, discovery channels, committed
articles, article versions, events, claims, evidence, or outbox records.

### Try the synchronized acquisition workflow

Start PostgreSQL through Compose, run the migrations, launch the API, and open:

```text
http://127.0.0.1:8010/docs
```

Protected API routes now require an approved platform account. For a local-only
developer checkout without an identity provider, set this explicitly in `.env.local`:

```env
NEWSINTEL_DEV_AUTH_BYPASS_ENABLED=true
NEWSINTEL_AUTH_SESSION_SECRET=replace-with-at-least-32-random-characters
```

Production refuses to start when development authentication is enabled. Online
deployments should configure OIDC/JWT settings instead.

Then call these endpoints in order:

1. Preferred: `POST /api/v1/publishers/discover` with publisher name and homepage URL
2. Fallback/manual mode: `POST /api/v1/admin/publishers`
3. Fallback/manual mode: `POST /api/v1/admin/discovery-channels`
4. `POST /api/v1/publishers/{publisher_id}/fetch` to schedule one publisher
5. `POST /api/v1/fetch/all` to schedule all publishers
6. `GET /api/v1/fetch-jobs/{job_id}` to poll fetch progress
7. `POST /api/v1/internal/discoveries` for collector integrations that push discoveries directly

The final request canonicalizes the URL, deduplicates it against the frontier, records channel provenance, calculates priority, and writes versioned outbox events in the same transaction.

### Run the workers

In a second PowerShell terminal, run the discovery poller:

```powershell
cd C:\Users\LENOVO\Documents\news
.\.venv\Scripts\python.exe -m newsintel.doctor
.\.venv\Scripts\python.exe -m newsintel.workers.poller
```

The worker leases due channels safely across multiple processes, uses conditional HTTP requests, parses feeds and sitemaps, records channel provenance, admits new URLs to the frontier, adapts polling intervals, and persists poll runs and failures.

In a third PowerShell terminal, run the article worker:

```powershell
cd C:\Users\LENOVO\Documents\news
.\.venv\Scripts\python.exe -m newsintel.workers.articles
```

The article worker leases URL candidates, fetches the article URL, extracts clean
article text and metadata, stores immutable article versions, creates a provisional
event for new articles or links the article to an existing event, extracts factual
claim candidates from exact article sentences, creates origin evidence links, writes
initial `not_checkable` verification records when evidence is insufficient, and emits
outbox events.

In a fourth PowerShell terminal, run automatic historical enrichment:

```powershell
cd C:\Users\LENOVO\Documents\news
.\.venv\Scripts\python.exe -m newsintel.workers.historical_enrichment
```

This worker automatically backfills older article versions and enriches every newly committed version with prior same-event reporting, earlier claim families, internal corpus matches and configured external historical providers. It never blocks article persistence.

In a fifth PowerShell terminal, run the local outbox relay:

```powershell
cd C:\Users\LENOVO\Documents\news
.\.venv\Scripts\python.exe -m newsintel.workers.outbox
```

For scheduled saved-search monitoring, run the workspace monitor worker in another terminal:

```powershell
cd C:\Users\LENOVO\Documents\news
.\.venv\Scripts\python.exe -m newsintel.workers.workspace_monitor
```

The monitor worker uses database leases and fencing tokens. The first successful run establishes a baseline; later runs create in-app alerts only when results enter the monitored top-result window. These alerts are monitoring signals, not truth judgments.

The one-command launcher starts the API, poller, article worker, historical-enrichment worker, outbox relay, derived-recompute worker, and workspace-monitor worker together, so separate terminals are only needed for manual development.

Useful read endpoints:

```text
GET /api/v1/publishers
POST /api/v1/publishers/discover
POST /api/v1/publishers/{publisher_id}/fetch
POST /api/v1/fetch/all
GET /api/v1/fetch-jobs/{job_id}
GET /api/v1/articles
GET /api/v1/articles/{article_id}/historical-context
GET /api/v1/articles/{article_id}
GET /api/v1/articles/{article_id}/claims
GET /api/v1/events/{event_id}
GET /api/v1/status
GET /api/v1/metrics
```

If the doctor reports that PostgreSQL is unreachable, install a free local database option first:

```powershell
# After installing Docker Desktop:
.\scripts\services.ps1 init
```

The poller now remains alive and retries with bounded exponential backoff if PostgreSQL temporarily becomes unavailable.

Docker Compose is provided for local infrastructure, but Docker must be installed separately.
If your terminal cannot find `docker`, use the helper script because it detects Docker
Desktop's standard Windows install path automatically:

```powershell
.\scripts\services.ps1 init
```

## 1.25 final product path

The final release closes the live product loop:

`sources -> discovery -> fetch -> immutable version -> event -> claims/evidence -> historical enrichment -> grounded event briefing -> analyst workspace`

Production/pilot deployment instructions are in `PRODUCTION-RUNBOOK.md`; the hardened single-host topology is `compose.production.yaml`.

After deployment, do not infer production readiness from a healthy API alone. The final package includes `newsintel-acceptance` and `scripts/production-acceptance.sh` for the required 24-hour, 72-hour and 7-day live trials. The evaluator measures API readiness, terminal article-processing success, publication-to-discovery p95 where usable publisher timestamps exist, historical-context completion, grounded-briefing completion and persistent lease staleness. Trials with too little traffic are `BLOCKED` rather than silently passing.

```bash
./scripts/production-acceptance.sh 24h
./scripts/production-acceptance.sh 72h
./scripts/production-acceptance.sh 7d
```

Automated acceptance does not replace manual review of extraction fidelity, event grouping, historical relevance, evidence grounding or source rights.

Important: `config/live-source-pack.json` is a validation starter pack, not a blanket licence to retain publisher content. Review source terms and configure retention before launch.

### UI clarity refinement (v1.25)

This package includes the refreshed navigation, clearer report/search/claim wording, source-numbered Event Briefings, sensitive-action dialogs and the Article Evolution render fix. See [`UI-REDESIGN-AND-COPY-AUDIT.md`](UI-REDESIGN-AND-COPY-AUDIT.md) for scope, decisions, limitations and validation. The application remains at version 1.25.0 and requires the same live acceptance steps before production use.
