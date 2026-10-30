# Evidence & Historical Intelligence Upgrade — 0.4.0

Release 0.4.0 builds on the 0.3.0 Source Fabric. It does not replace the acquisition
pipeline; it upgrades the intelligence applied after an article has been acquired and
versioned.

## Scope and safety principle

The release deliberately separates **evidence readiness** from **factual truth**. A high
article-quality score means that the stored article is extractable, its claims are specific,
and independent evidence has been attached and evaluated. It does not mean that every
claim is true merely because a source appears reputable.

## Claim extraction v2

`deterministic-atomic-claim-extractor-v2` adds:

- conservative decomposition of reconstructable compound claims;
- claim types such as numeric, temporal, legal, scientific, causal, predictive,
  attribution, event-occurrence, comparative and statistical;
- normalized percentages, currency/scaled quantities and temporal references;
- attribution metadata;
- per-claim checkability scores;
- expected primary-evidence classes;
- canonical claim keys and revision-tolerant claim-family keys;
- source sentence and clause provenance.

Existing v1 claims remain readable. New article versions receive v2 metadata automatically.

## Passage-level evidence provenance

Origin evidence links now retain the exact claim passage, passage hash, sentence index,
clause index, source sentence, claim type and family key. This makes later verification
reproducible without treating the entire article body as one opaque evidence object.

`deterministic-evidence-passage-v1` can retrieve candidate passages from evidence text and
classify them as:

- matching assertion;
- potential numeric conflict;
- potential temporal conflict;
- related context;
- low relevance.

These labels are retrieval signals, not truth verdicts.

## Evidence-weighted verification

`evidence-weighted-verification-v1` aggregates already-classified evidence while:

- excluding the originating article from independent confirmation;
- deduplicating evidence with the same lineage key;
- giving explicit primary evidence greater weight;
- distinguishing support, contradiction, dispute and context;
- refusing to treat missing evidence as contradiction;
- emitting `unsupported` from absence only when an evidence search is explicitly marked
  complete.

`POST /api/v1/claims/{claim_id}/verify` persists a new verification revision instead of
overwriting historical decisions. The action is protected by the new `claims:verify`
permission.

## Article evidence-readiness profile

`GET /api/v1/articles/{article_id}/quality` returns a transparent profile containing:

- extraction integrity;
- claim checkability;
- verification coverage;
- independent-evidence depth;
- evidence-source diversity;
- verification confidence;
- revision transparency;
- overall evidence readiness.

The response includes `assessment_scope=evidence_readiness_not_factual_truth` to prevent the
score from being misrepresented as a source reputation or truth score.

## Article version intelligence

`article-version-diff-v1` compares immutable article versions and detects:

- title changes;
- sentence additions/removals/replacements;
- high-significance numeric changes;
- high-significance temporal changes;
- explicit correction/update notices.

`GET /api/v1/historical/articles/{article_id}/versions` exposes the ordered history and
per-version diffs.

## Claim evolution

Claim-family keys mask volatile quantities and dates, allowing versions such as “31 people”
and “13 people” to be grouped as revisions of the same proposition.

`GET /api/v1/historical/articles/{article_id}/claim-history` exposes:

- first/last version containing each claim family;
- whether it remains active in the latest version;
- whether its wording/value changed;
- normalized quantities and temporal references per revision;
- complete verification-revision history for each extracted claim.

## Event timeline

`GET /api/v1/historical/events/{event_id}/timeline` reconstructs the platform-observed event
history from stored article versions, publishers and claims. It reports article observations,
article revisions, material/numeric/temporal changes and claim counts.

The API explicitly states its time semantics: `occurred_at` is the platform observation time,
while publisher `published_at` is retained separately. Neither is silently treated as the
real-world event time.

## Local historical corpus search

`POST /api/v1/historical/internal/search` searches the platform's own immutable article
versions with optional date bounds and returns event/version identifiers, snippets, claim
counts and lineage metadata. External providers remain supplementary rather than becoming
the only historical memory.

External historical search now also preserves which configured providers returned a
collapsed result and emits a chronology summary containing earliest/latest publication time,
yearly result counts, source count and provider count.

## Content lineage foundation

New article versions persist `content-lineage-minhash-v1` metadata containing an exact
normalized signature and a compact shingle fingerprint. This is a foundation for detecting
wire-service republication and near-syndication so copied stories do not automatically count
as independent evidence.

## New/changed API surface

- `GET /api/v1/articles/{article_id}/quality`
- `POST /api/v1/claims/{claim_id}/verify`
- `POST /api/v1/historical/internal/search`
- `GET /api/v1/historical/articles/{article_id}/versions`
- `GET /api/v1/historical/articles/{article_id}/claim-history`
- `GET /api/v1/historical/events/{event_id}/timeline`
- external `/api/v1/historical/search` responses now include `timeline_summary` and
  duplicate-provider provenance in result metadata.

## Database compatibility

0.4.0 adds no new database migration. It uses existing immutable article versions,
`article_claims`, `claim_evidence_links` and `claim_verifications`; the additional claim,
lineage and evidence provenance is stored in their existing JSON metadata fields. The
migration head therefore remains `0011_source_fabric_registry`.

## Validation in the build environment

Validation performed for this build:

- 39/39 evidence/historical intelligence tests pass natively;
- the pre-existing 63/63 source-fabric regression set still passes natively;
- 130/130 unit tests that do not import the missing sandbox `structlog` package pass natively;
- 141/141 unit tests pass with a temporary test-only `structlog` shim outside the release
  package, allowing article-worker and logging-dependent imports to execute;
- the OpenAPI synchronization integration test passes with that external shim;
- the migration graph remains a single head at `0011_source_fabric_registry`;
- Python compilation succeeds across source, tests and migrations.

The sandbox still lacks the project-declared `structlog` and `asyncpg` packages and cannot
download dependencies. Consequently the real application lifespan/liveness integration test
cannot initialize the async PostgreSQL engine here. The shim is not included in the archive.
Run `uv sync --frozen --extra dev`, migrations, and the complete suite in the locked deployment
environment before a pilot release.

## Remaining high-value work after 0.4.0

- automatic primary-record retrieval by claim type;
- evidence stance classification from independent documents;
- durable evidence-search run records so “retrieval complete” is system-proven rather than
  operator-asserted;
- learned/empirical source reliability by topic, language, geography and time;
- near-duplicate lineage clustering across the full corpus;
- outcome tracking and promise-vs-outcome analysis;
- temporal event knowledge graph and structured historical analog retrieval;
- benchmark datasets for claim extraction, stance, contradiction, correction and timeline
  quality.
