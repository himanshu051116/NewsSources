# Historical engineering assessment — 12 October 2026

**Historical planning document.** This assessment describes the v1.22 branch as of 12 October 2026 and is retained for traceability. It is **not the current project status**. See the [repository overview](../README.md), [release history](archive/README.md) and open GitHub pull requests for later changes.

**Assessment date:** 2026-10-12  
**Release under test:** 1.22.0 Production Search Deployment Control

## 1. Current stage

The platform is a functioning acquisition and provenance backend with a local operator
interface. It is not yet an evidence-grade autonomous news intelligence system.

### Implemented and working

- publisher homepage onboarding;
- RSS, Atom, sitemap, news-sitemap and listing-page discovery;
- SSRF-aware bounded fetching and redirect validation;
- recent-article admission and explicit rejection categories;
- asynchronous poller, article worker, historical-enrichment worker and outbox worker entry points;
- HTML metadata and text extraction, including optional Trafilatura extraction;
- immutable article versions and content hashes;
- deterministic preliminary event assignment;
- atomic deterministic claim extraction with normalized quantity/time metadata;
- transparent verification history plus evidence-readiness quality profiles;
- bounded execution of administrator-approved primary-evidence authority searches;
- evidence retrieval-attempt provenance and redirect-hop domain enforcement;
- Bayesian publisher/topic reliability snapshots used only as non-scoring context;
- temporal event knowledge graphs with evidence/verification revision nodes and as-of graph diffs;
- article, event, status and metrics APIs;
- local source-management dashboard;
- role-based access foundation;
- historical provider search, local corpus search, version diffs, claim history and event timelines;
- an authenticated historical research dashboard.

### Not yet complete

- exact fetch-job-to-worker correlation and truthful terminal progress;
- worker lease heartbeat and fencing;
- end-to-end PostgreSQL integration coverage for the large commit repository;
- cross-URL article identity and cross-publisher syndication lineage;
- multilingual entity, claim and event benchmark quality;
- additional authority-specific adapters beyond the CKAN/Socrata/configured-JSON adapters included in v0.7;
- benchmarked multilingual semantic event/entity retrieval beyond the optional local historical vector index;
- production high availability, disaster recovery and security operations.





## 2. Development completed in 1.9.0 Blind Adjudication & Failure Attribution

- snapshots model predictions privately at benchmark sampling time instead of exposing them to reviewers;
- adds deterministic stratified sampling across prediction label, language and topic with source-document diversity;
- prevents event/source-document leakage when sampling a later train/dev/test split;
- exports blind JSONL review sheets that intentionally omit prediction labels and confidence;
- supports two independent reviewer passes and stores only SHA-256 reviewer-key fingerprints;
- measures pairwise reviewer agreement and nominal Krippendorff alpha;
- requires a separate adjudicator when independent reviewers disagree;
- finalizes only double-review consensus or explicitly adjudicated cases into the held-out benchmark table;
- adds diagnostic attribution for wrong verdicts across extraction fidelity, event identity, evidence retrieval, evidence independence, conflict resolution and final verification decision;
- exposes human-review agreement and diagnostic actions in the `/accuracy` workspace;
- advances Alembic to the single head `0023_blind_adjudication_diagnostics`.

See [Blind adjudication & failure attribution 1.9.0](BLIND_ADJUDICATION_1.9.0.md).


## 2. Development completed in 1.8.0 Accuracy Measurement & Adjudication

- separates extraction fidelity, event-link quality and factual-verification performance instead of blending them into one misleading accuracy score;
- advances verification benchmarking to methodology v3 with decided-case accuracy/F1, decision coverage, abstention rate and unsafe high-confidence error rate;
- keeps confidence calibration focused on substantive verdicts while measuring abstention separately through coverage;
- adds human-adjudication JSONL export/import tooling for building held-out benchmark sets from the local corpus;
- adds an analyst `/accuracy` workspace for benchmark, corpus-audit and quality-gate results;
- expands the event-link regression fixture to 20 positive/hard-negative pairs across multiple domains and Hindi/English examples;
- advances event matching to `event-matching-structured-lexical-v4` with safer location/entity anchors and harder over-merge guards while retaining the existing 0.62 candidate threshold;
- adds aggregate live extraction-fidelity auditing across multiple publisher URLs;
- retains Alembic head `0022_browser_recompute` because no schema change is required.

See [Accuracy Measurement & Adjudication 1.8.0](ACCURACY_MEASUREMENT_UPGRADE_1.8.0.md).


## 2. Development completed in 1.7.0 Accuracy & Source Fidelity

- expands HTML feed-directory discovery so `/rss` pages that link to real RSS/Atom feeds are not discarded as malformed XML;
- advances event identity to `event-matching-structured-lexical-v3` with contextual numeric facts, containment and gated strong-anchor conjunctions without lowering the global candidate threshold;
- adds a same-event/hard-negative accuracy fixture including cross-publisher maritime, space and Hindi election cases;
- adds publisher-page extraction fidelity for headline, canonical URL, publication time, structured-body coverage and numeric retention;
- stores extraction-fidelity diagnostics on immutable article versions and surfaces human labels in News and Article Intelligence;
- fixes the missing article-summary projection helper used by the news feed path;
- adds a live `newsintel-accuracy-audit` command for real publisher URLs;
- retains Alembic head `0022_browser_recompute` because no schema change is required.

See [Accuracy & Source Fidelity 1.7.0](ACCURACY_SOURCE_FIDELITY_UPGRADE_1.7.0.md).


## 2. Development completed in 1.6.0 Seamless Intelligence UI

- unifies News, Article Intelligence, Event Intelligence, Research, Sources, Workspace and Access under a shared responsive design system;
- adds progressive story loading, feed filters, language filter and sort controls;
- makes Article Intelligence permission-resilient and progressive rather than all-or-nothing;
- adds human event pages, expandable claim/evidence cards, timeline views and clearer non-probabilistic status language;
- combines internal-corpus and external-provider research in one UI;
- separates source operations from news consumption;
- retains Alembic head `0022_browser_recompute` because no schema change is required.

See [Seamless Intelligence UI 1.6.0](SEAMLESS_UI_UPGRADE_1.6.0.md).

## 3. Previously completed in 1.5.0 Browser Recovery & Dependency Recompute

- adds an optional isolated Playwright browser-renderer service for genuinely JavaScript-only pages;
- keeps browser rendering globally disabled and publisher opt-in, with explicit additional asset-domain allow-lists;
- re-validates every browser navigation/subresource target against public-network and approved-domain rules;
- blocks downloads, service workers, WebSockets, media/font/image requests and private-network targets in the renderer;
- preserves ordinary safe HTTP/hydration extraction as the first path and fails open to it when rendering is unavailable;
- adds a generalized derived-artifact dependency registry, stale state and generation-scoped recompute queue;
- registers historical-context dependencies and invalidates affected contexts after corrections/retractions;
- adds a recompute worker with expired-lease recovery and bounded retry/backoff;
- surfaces stale/recompute state in Article Intelligence and labels browser-recovered article versions;
- advances Alembic to the single head `0022_browser_recompute`.

See [Browser Recovery & Dependency Recompute 1.5.0](BROWSER_RENDERING_RECOMPUTE_UPGRADE_1.5.0.md).

## 2. Development completed in 1.4.0 Adaptive Extraction & Semantic History

- adds persisted publisher extraction profiles with operator-defined cleanup rules and conservative repeated-sample method recommendations;
- adds bounded recovery of article bodies/metadata from common server-delivered JSON hydration state;
- integrates the profile resolver/learning loop into normal article processing without bypassing access policy;
- adds optional local Ollama embeddings plus Qdrant indexing for historical retrieval while retaining PostgreSQL as the source of truth;
- enforces the existing historical observation cutoff inside semantic retrieval and merges vector matches with explainable lexical/entity reranking;
- requeues already-enriched historical contexts once semantic retrieval is newly enabled;
- stops starting unused Redis by default while retaining an explicit `event-bus` Compose profile;
- intentionally defers networked headless-browser rendering until a separately sandboxed SSRF-safe renderer exists;
- advances Alembic to the single head `0021_adaptive_extraction_semantic`.

See [Adaptive Extraction & Semantic History 1.4.0](ADAPTIVE_EXTRACTION_SEMANTIC_UPGRADE_1.4.0.md).

## 2. Development completed in 1.3.0 Coherence & Retrieval

- replaces misleading semantic naming in event matching with an explicit structured lexical v2 policy while retaining API compatibility;
- adds Unicode-aware event/history tokenization and real event-type/action compatibility;
- selects active-event candidates by recent material change rather than original creation time;
- replaces bounded 800-version historical scans with full-corpus PostgreSQL FTS plus explainable reranking;
- replaces 1,000-row claim-history scanning with indexed exact `claim_family_key` retrieval;
- aligns manual internal research with the same full-corpus text index;
- adds a viewer news feed and a unified Article Intelligence workspace instead of raw JSON navigation;
- adds bounded SSE intelligence-state updates and a canonical presentation state;
- bulk-loads article-list versions/history to remove the main N+1 query pattern;
- advances Alembic to the single head `0020_coherence_retrieval`.

See [Coherence & Retrieval 1.3.0](COHERENCE_RETRIEVAL_UPGRADE_1.3.0.md).

## 2. Development completed in 1.2.0 Historical Context Quality

- upgraded automatic historical matching from count-based context to ranked, explainable relevance scoring;
- deduplicates the same historical story across event/internal/external channels before calculating depth;
- adds source/channel diversity and duplicate-aware historical context confidence, explicitly not a truth score;
- classifies recurring claim evolution into numeric, temporal, wording and revision-candidate changes;
- adds structured `what_changed` and high-level continuity/material-update/conflict patterns to every context;
- automatically requeues contexts when a late-ingested older same-event report becomes available while preserving the original cutoff;
- exposes reconciliation count/reason/time plus historical depth/confidence/change pattern in API/dashboard views;
- hardens readiness checks for the new reconciliation columns;
- advances Alembic to the single head `0019_historical_context_quality`.

See [Historical Context Quality 1.2.0](HISTORICAL_CONTEXT_QUALITY_1.2.0.md).

## 2. Development completed in 1.1.0 Automatic Historical Enrichment

- historical enrichment is now automatically queued for every newly committed immutable article version;
- added a separate lease/retry worker so external historical search cannot block article extraction or visibility;
- automatic history includes prior same-event reporting, previous versions, prior claim families, internal corpus matches and bounded external-provider results;
- enrichment uses the article version's retrieval time as a strict automatic historical cutoff;
- added claim-evolution summaries for new, recurring, changed, numeric-change and temporal-change claim families;
- existing article versions are idempotently backfilled after upgrading;
- article detail/list APIs and the source dashboard now expose historical-enrichment state/context;
- extraction now persists usable public partial content with warnings instead of rejecting it solely for subscription/paywall boilerplate indicators;
- advanced Alembic to the single head `0018_historical_enrichment`.

See [Automatic Historical Enrichment 1.1.0](AUTOMATIC_HISTORICAL_ENRICHMENT_1.1.0.md).

## 3. Development completed in 1.0.0 Production Readiness

- added immutable verification reproducibility manifests with deterministic SHA-256 digests and as-of decision context;
- added bounded backfill for historical verification revisions without rerunning or changing their verdicts;
- extended correction/retraction propagation to downstream claims that depend on corrected evidence, covering both legacy evidence links and passage-level evidence evaluations;
- added persisted production-readiness assessments combining schema, held-out benchmark, manifest coverage, critical review and authority-availability checks;
- fixed readiness and doctor schema validation to use the exact v1.0 relation contract;
- strengthened production settings by rejecting default PostgreSQL credentials and non-HTTPS public URLs;
- added validated/generated request IDs, server timing and operational metrics for correction reviews and manifests;
- added offline release-tree integrity validation, strict lint/type-check mode, and a bounded deployment smoke/load probe;
- advanced Alembic to the single head `0017_production_readiness`.

See [Production Readiness 1.0.0](PRODUCTION_READINESS_UPGRADE_1.0.0.md).

## 3. Verified test baseline

For the 1.0.0 build, final release validation records the exact current test counts and package
integrity after the code/documentation freeze. The release continues to require real locked
dependencies and PostgreSQL/PostGIS validation before production deployment; sandbox-only
validation shims are kept outside the release tree and are never packaged.

The migration chain has one head: `0023_blind_adjudication_diagnostics`. The current migration adds blind benchmark candidate/reviewer persistence plus agreement and diagnostic run records while retaining all earlier acquisition, evidence, extraction, event and historical intelligence data.



## 4. Development completed in 0.9.0 Validation & Propagation

- added persisted evidence-search stopping assessments with sufficient, exhausted, budget and conflict-escalation decisions;
- added deterministic correction/retraction candidate detection from immutable article-version diffs;
- added correction propagation that creates review flags and temporal graph state without silently rewriting historical claim verdicts;
- surfaced review-required and critical-retraction context in article evidence-readiness responses;
- added a held-out benchmark quality gate that combines macro F1, high-confidence error, selective performance and corpus leakage checks;
- upgraded benchmark corpus auditing to detect event/family (`group_key`) leakage and same-source-document leakage across splits;
- added constrained JSON entity-registry profiles and ambiguity-safe external-ID linking behind the existing approved-domain/redirect security boundary;
- added bounded, idempotent ownership-history ingestion with timestamped provenance;
- added cross-platform release-validation scripts and hardened `newsintel-doctor` against the exact v0.9 schema;
- advanced Alembic to the single head `0016_validation_propagation`.

See [Validation & Propagation 0.9.0](VALIDATION_PROPAGATION_UPGRADE_0.9.0.md).

## 3. Development completed in 0.8.0 Accuracy & Evidence Orchestration

- added bounded multi-authority evidence orchestration with coverage reporting and persisted selection rationale;
- added lineage-deduplicated conflict-resolution revisions with explicit temporal-evolution and unresolved-conflict states;
- added benchmark v2 classification metrics, high-confidence error measurement and selective accuracy/coverage curves;
- added benchmark split/topic/language/jurisdiction metadata plus cross-split leakage and duplicate-case auditing;
- added provenance-preserving external entity identifiers that feed the existing ambiguity-safe resolver;
- added timestamped ownership-provenance records with passage hashes and validity windows;
- added as-of temporal graph neighborhood traversal for analyst historical research;
- surfaced latest conflict-state counts in article evidence-readiness profiles without changing the truth-score guardrail;
- hardened `newsintel-doctor` against the exact v0.8 tables/indexes;
- advanced Alembic to the single head `0015_accuracy_orchestration`.

See [Accuracy & Evidence Orchestration 0.8.0](ACCURACY_ORCHESTRATION_UPGRADE_0.8.0.md).

## 3. Development completed in 0.7.0 Provenance, Entity & Calibration

- added CKAN, Socrata and explicit-field JSON authority adapters while preserving the v0.6 authority allow-list and redirect protections;
- added bounded CSV/TSV evidence text extraction for official numeric datasets;
- added time-bounded media ownership groups and publisher memberships solely for corroboration-independence estimation;
- added explicit circular-sourcing detection when a purported corroborating source attributes the assertion back to the origin;
- upgraded article quality to `evidence-readiness-v4`, replacing raw evidence-link depth with effective independence weight and exposing `source_independence_integrity`;
- added a canonical entity and alias registry with ambiguity-safe deterministic resolution and graph reuse;
- added a PostgreSQL GIN full-text index and as-of cross-event temporal-knowledge search;
- added externally adjudicated verification benchmark cases and persisted calibration snapshots with Brier score and expected calibration error;
- hardened `newsintel-doctor` and readiness checks against the exact release migration/schema;
- advanced Alembic to the single head `0014_ownership_entities_calibration`.

See [Provenance, Entity & Calibration 0.7.0](PROVENANCE_CALIBRATION_UPGRADE_0.7.0.md).

## 3. Development completed in 0.6.0 Evidence Graph & Reliability

- added a bounded authority-search adapter that executes only administrator-approved evidence domains;
- enforced the approved authority-domain allow-list on every HTTP redirect hop, including robots retrieval;
- rejected authority search templates that embed API keys, access tokens, secrets or equivalent query credentials;
- persisted every authority retrieval attempt and retained its relationship to the originating evidence-search run;
- added evidence-content lineage fingerprints, same-domain/authority lineage grouping and conservative independence caps for near-republished material;
- added a deterministic news-topic classifier and Bayesian publisher/topic reliability snapshots with uncertainty intervals and sample-size shrinkage;
- excluded `UNSUPPORTED`/`NOT_CHECKABLE` outcomes from publisher-failure counts so lack of evidence is not treated as inaccuracy;
- exposed historical publisher reliability as context only, with zero weight in the current article evidence-readiness score;
- added persistent temporal knowledge-graph nodes and edges for claims, entities, actors, commitments, evidence and verification revisions;
- added as-of graph retrieval and graph diffs so analysts can see what became known, expired or changed between two timestamps;
- advanced Alembic to the single head `0013_evidence_graph_reliability`.

## 4. Development completed in 0.5.0 Primary Evidence & Temporal Knowledge

- added deterministic primary-evidence requirement plans and durable evidence-search runs;
- added a scoped evidence-authority registry so source labels alone cannot receive primary-record weight;
- added temporal stance reasoning that separates same-time contradictions from later/earlier updates;
- added durable passage evaluations with exact passage hashes and temporal/authority provenance;
- upgraded article evidence readiness to v2 with primary-record coverage, completed-search coverage and temporal-context resolution;
- added immutable claim confidence-history views;
- added event commitment discovery and evidence-scoped outcome tracking;
- added as-known-then event knowledge snapshots to reduce hindsight bias in historical analysis;
- added direct `python-dateutil` dependency for explicit temporal reasoning;
- advanced Alembic to the single head `0012_evidence_temporal_knowledge`.

See [Primary Evidence & Temporal Knowledge 0.5.0](PRIMARY_EVIDENCE_TEMPORAL_UPGRADE_0.5.0.md).

## 4. Development completed in 0.4.0 Evidence & Historical Intelligence

- upgraded claim extraction to deterministic atomic v2 with claim types, quantity/date
  normalization, checkability and expected primary-evidence classes;
- added revision-tolerant claim-family keys and complete claim-verification history views;
- added exact evidence passage provenance and a passage matcher for potential numeric/temporal
  conflicts without turning textual similarity into a truth verdict;
- added evidence-weighted verification with primary-evidence weighting and lineage
  deduplication;
- added article evidence-readiness quality profiles with an explicit non-truth-score scope;
- added article-version diffs, correction detection and event observation timelines;
- added local historical corpus search and improved external-provider chronology/provenance;
- added content-lineage fingerprints to article-version metadata;
- advanced package version to 0.4.0 while retaining Alembic head
  `0011_source_fabric_registry` because no schema migration is required.

See [Evidence & Historical Intelligence 0.4.0](EVIDENCE_HISTORICAL_UPGRADE_0.4.0.md).

## 5. Development completed in 0.3.0 Source Fabric

### Source acquisition and discovery

- added JSON Feed 1.0/1.1 discovery, validation and polling;
- added feed discovery from HTTP `Link` headers;
- added true Google News Sitemap detection and runtime channel self-correction;
- added gzip sitemap parsing and News Sitemap publication metadata;
- expanded and scored homepage/section discovery with initial multilingual navigation evidence;
- added JSON-LD article discovery for opaque publisher URL patterns.

### Crawl policy

- added robots parsing and enforcement around source/article fetching;
- added per-host concurrency and request-spacing budgets;
- added configurable robots caching and fail-closed behavior.

### Source intelligence

- added `publisher_domains`, `robots_snapshots` and quarantined `source_candidates`;
- added per-channel source-health scoring;
- added discovery overlap, unique-contribution and first-discovery auditing;
- added safe external-source candidate inference from extracted article links without
  automatically authorizing those domains for crawling.

### Repository integrity

- restored the local and S3 raw-artifact adapters referenced by the worker/test code;
- advanced the package and migration head to 0.3.0 / `0011_source_fabric_registry`.

See [Source Fabric 0.3.0 upgrade](SOURCE_FABRIC_UPGRADE_0.3.0.md) for the implementation
and validation details.

## 6. Development completed in 0.2.0

### Acquisition quality

- detects dates embedded in common article URL formats;
- rejects old URLs even when a feed incorrectly presents them as current;
- rejects explicit future URL dates;
- persists a URL-derived publication date when feed metadata is absent;
- prevents legacy BBC-style dated paths from flooding recent acquisition.

### Extraction correctness

- filters subscription, promotional and low-value boilerplate after optional
  Trafilatura extraction;
- restores deterministic publisher policy enforcement regardless of extractor path.

### Security

- removes unsafe dynamic dashboard interpolation paths;
- escapes external and database-controlled dashboard values;
- validates external link schemes;
- stops HTTPX from logging full URLs that can contain query-string API keys;
- rejects weak or ambiguous production JWT configurations;
- distinguishes S3 missing-object responses from access, network and service failures;
- binds Qdrant to localhost in the supplied Compose topology.

### Historical research

- added GDELT, Guardian, NYT, NewsAPI and Google Fact Check search adapters;
- added Wayback and Common Crawl archive lookup;
- added provider-level timeout and failure isolation;
- added canonical URL deduplication;
- added safe provider status and error responses;
- added authenticated APIs and a safe historical research page;
- added empty secret placeholders, never bundled real keys.

### Reproducibility and hygiene

- aligned local PostgreSQL, Redis, MinIO and API ports across templates and docs;
- removed uploaded runtime logs, backup launchers, backup Compose and generated coverage
  output from the tracked release source;
- added a cross-platform `uv.lock` and reproducible `uv sync` workflow;
- added a test runner that enforces compilation, Ruff, strict mypy, 99 tests, a 60 percent coverage floor and a single Alembic head;
- advanced the package version to 0.2.0.

## 6. Further development outline

### Phase A — Truthful acquisition orchestration

**Goal:** every operator-triggered fetch has accurate, job-scoped progress.

Development:

1. Create `fetch_job_publishers`, `fetch_job_channels`, `fetch_job_poll_runs` and
   `fetch_job_article_runs` relationships.
2. Replace inferred publisher progress with worker-owned transactional counters.
3. Add explicit `scheduled`, `running`, `partial`, `completed`, `failed` and `cancelled`
   transitions.
4. Separate request, poll-start, poll-success and article-completion timestamps.
5. Implement cancellation and retry of a specific job.
6. Add job-scoped crawl and candidate budgets.

Acceptance tests:

- unrelated scheduled polling never changes manual-job progress;
- a job always reaches one terminal state;
- counters reconcile with its linked poll and article runs;
- cancellation prevents new leases without corrupting completed work.

### Phase B — Worker durability

**Goal:** process crashes and slow requests do not create duplicate work.

Development:

1. Add lease version and fencing token.
2. Add worker heartbeat and bounded lease extension.
3. Validate token ownership before artifact writes and database commit.
4. Add idempotency keys to external side effects.
5. Add an artifact reconciliation worker.
6. Add failure injection at fetch, extraction, object-write, flush, commit and outbox
   stages.

Acceptance tests:

- two workers cannot commit the same leased operation;
- a stale worker is fenced after lease expiry;
- killing any worker stage leaves a recoverable state;
- no committed article is reported before all mandatory writes succeed.

### Phase C — Article identity, corrections and source lineage

**Goal:** represent the story rather than only its URL.

Development:

1. Add URL-variant and canonical-identity tables.
2. Add exact and near-duplicate content detection.
3. Add syndication and republication lineage.
4. Detect headline-only changes, factual corrections, retractions and major rewrites.
5. Compute changed claims, numbers, dates, entities and attribution.
6. Re-run affected event membership and evidence when material versions change.

Acceptance tests:

- AMP, mobile and tracking variants converge on one article identity;
- identical syndicated copies are linked, not treated as independent evidence;
- correction and retraction changes propagate to affected assessments.

### Phase D — Research search and workspace

**Goal:** analysts can investigate without direct database access.

Development status through 1.22:

1. **Implemented:** PostgreSQL full-text search with weighted GIN indexes and snapshot-bound keyset cursor pagination.
2. **Partially implemented:** publisher, language, date, result-type and event-lifecycle filters. URL type, extraction-quality and claim-status facets remain.
3. **Implemented:** labelled search-quality benchmark infrastructure with graded relevance judgments, Precision@K, Recall@K, MRR, NDCG@K, judgment coverage and latency distributions. No search-quality score is claimed until a sufficiently judged benchmark is populated.
4. **Implemented:** privacy-preserving search latency observations that store fingerprints/filters/timing rather than raw analyst queries, plus fingerprint-group slow-query diagnostics for staging plan analysis.
5. **Implemented:** canonical-entity and approved-alias search, entity profile pages, external identifiers and conservative exact normalized claim-to-entity mention linking. Fuzzy similarity is not allowed to create identity links.
6. **Implemented in 1.19:** deterministic alias/canonical collision detection, human-reviewed entity merge/split workflows, preserved merged-source audit records and resolution-action history. No fuzzy conflict candidate is auto-merged.
7. **Implemented in 1.19:** portable search-benchmark JSON import/export and language/topic/result-type metric slices so weak retrieval segments cannot be hidden by aggregate metrics.
8. **Implemented:** Event directory, Event Dossier and material timeline.
9. **Implemented:** saved searches, watchlists, evidence-grounded alerts and durable scheduled search monitoring, including entity-result monitoring.
10. **Implemented:** collaborative investigation collections, analyst notes and reproducible evidence manifests.
11. **Implemented:** article-version comparison, correction workflow and manifest export; richer human-readable briefing export remains.
12. **Implemented as a controlled 1.20 experiment:** article-only semantic reranking can be evaluated against the lexical candidate pool using the existing local Ollama/Qdrant article-version index. It never changes production search automatically and cannot inject semantically-only results. Promotion remains deferred until labelled benchmarks show worthwhile gains.
13. **Implemented in 1.20:** Unicode-normalized multilingual query handling, a language-neutral simple FTS path for Hindi/other scripts, concurrent indexed English morphology fallback for Latin queries, and suggestion-only query assistance using approved aliases/publishers/recent-event vocabulary. Suggestions never rewrite or execute an analyst query automatically.
14. **Implemented in 1.21:** persistent per-benchmark search promotion policies, frozen-fingerprint lexical/hybrid promotion gates, current-version semantic-index freshness diagnostics, required language/topic slice gates, latency budgets, auditable evaluation history and separately recorded human approve/hold/reject decisions. Gate PASS or human approval never changes production search automatically.
15. **Implemented in 1.22:** production search deployment control with OFF/SHADOW/CANARY/PAUSED states, deterministic per-user bucketing, approval-gated article-only canary exposure, lexical fallback on semantic failure, privacy-preserving live rollout telemetry, engagement-proxy result-open outcomes, automatic latency/error circuit breakers, emergency manual pause and auditable rollout actions. Exposure remains 0% until explicitly configured.

Acceptance tests:

- search Precision@K, Recall@K, MRR and NDCG are measurable on a labelled graded-relevance query set, with judgment coverage reported alongside metrics;
- every displayed result exposes provenance and version;
- exports can reproduce the evidence view seen by the analyst.

### Phase E — Multilingual event intelligence

**Goal:** reliable event grouping across supported languages and long-running events.

Development:

1. Rename the current lexical feature accurately.
2. Add multilingual embeddings for candidate retrieval.
3. Add language-aware entity and location resolution.
4. Add event-type and temporal-continuity models.
5. Add provisional membership, merge, split, reassignment and aliases.
6. Build labelled benchmarks for English, Hindi and priority regional languages.

Acceptance tests:

- report precision, recall, fragmentation and incorrect-merge rates per language;
- a long-running event remains linked beyond the current short lookback window;
- uncertain membership does not contaminate confirmed event views.

### Phase F — Evidence-grade claim verification

**Goal:** no conclusion without independently traceable evidence.

Development:

1. Sentence segmentation by language.
2. Factuality and check-worthiness classification.
3. Atomic claim decomposition, speaker attribution, negation and modality.
4. Primary-source connectors for government releases, filings, court records and
   official datasets.
5. Passage-level evidence storage.
6. Source independence and circular-sourcing detection.
7. Evidence stance and a deterministic versioned decision policy.
8. Mandatory abstention and correction propagation.

Acceptance tests:

- each conclusive assessment has exact evidence passages and source lineage;
- syndicated sources never count as independent confirmations;
- unavailable, ambiguous or conflicting evidence produces abstention or a conflict
  state rather than invented certainty.

### Phase G — Production operations

**Goal:** a controlled institutional pilot with recoverable operations.

Development:

1. CI with lint, typing, unit, PostgreSQL integration, migration and coverage gates.
2. Dependency lock and signed release manifest.
3. OIDC/SSO, MFA policy and four-eyes administration.
4. Secret manager and key rotation.
5. Backup of PostgreSQL and object data, point-in-time recovery and restoration drills.
6. Metrics for queue age, lease expiry, job truth, outbox lag and provider failures.
7. SIEM integration, incident response and audit retention.
8. Load, soak and chaos testing.

Acceptance tests:

- clean installation from documented files succeeds;
- backup restoration is demonstrated, timed and documented;
- service and worker objectives are measured under representative load;
- a security review finds no unresolved critical or high-severity issue.

## 7. Recommended order

Do not add model-generated summaries as the next priority. Complete phases A and B first,
then article identity and search. Evidence-grade claims should be built only after source
lineage, correction handling and analyst-visible provenance are trustworthy.

The safest release sequence is:

```text
0.2.0 acquisition foundation
→ 0.3.0 Source Fabric and source-health observability
→ 0.4.0 Evidence & Historical Intelligence
→ 0.5.0 Primary Evidence & Temporal Knowledge
→ 0.6.0 Evidence Graph & Reliability
→ 0.7.0 specialized authority adapters, calibrated entity/lineage intelligence and search
→ 0.8.0 benchmarked evidence orchestration, conflict resolution and provenance research
→ 1.0 controlled production release
```


## 1.10.0 Accuracy Validation Program

Added content-addressed benchmark fingerprints, Wilson confidence intervals, slice-level quality gates, and active-sampling recommendations on top of the blind-adjudicated v1.9 corpus. No schema migration is required; the database head remains `0023_blind_adjudication_diagnostics`.
