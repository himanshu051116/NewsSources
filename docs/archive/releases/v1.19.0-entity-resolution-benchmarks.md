# News Intelligence 1.19.0 — Entity Resolution & Benchmark Expansion

## Purpose

Version 1.19 hardens two areas that become increasingly important as the corpus grows:

1. canonical identity maintenance must be reviewable when approved aliases collide; and
2. search quality must be diagnosable by language/topic/result type rather than only through one aggregate metric.

No fuzzy identity score is allowed to merge entities automatically, and this release still does not enable semantic reranking by default.

## Entity Resolution Queue

A new `/entities/resolution` analyst surface provides deterministic conflict discovery and human resolution.

Conflict discovery only considers shared normalized canonical names and approved aliases across active canonical entities. A candidate is explicitly labelled as a review signal, not evidence that two records are the same real-world entity.

Verifier actions include:

- choose an explicit source and target for merge;
- reject a candidate and keep identities separate with a written rationale;
- split a specific non-canonical approved alias into a new canonical entity;
- inspect resolution action history.

### Merge semantics

A merge:

- refuses source=target;
- refuses cross-type merges;
- refuses conflicting non-null country codes;
- moves unique aliases to the target and collapses duplicate aliases;
- moves external-identifier rows to the target;
- moves exact entity mentions, collapsing duplicate target mention keys;
- adds the source canonical name as a target alias when needed;
- preserves the source canonical record with `resolution_status=merged` and `merged_into_entity_id=<target>`;
- excludes merged records from active entity/global search;
- records an auditable `entity_resolution_actions` row with the verifier rationale and operation counts.

A merged source profile remains directly inspectable for audit and links to the active target profile.

### Alias split semantics

Alias split is intentionally narrow. A verifier selects one approved non-canonical alias and creates a new canonical entity. Only exact stored mention links matching that normalized alias move automatically. Similar-looking text is not reassigned.

The canonical-name alias cannot be split using this shortcut because doing so would redefine the original canonical identity rather than separating an alias.

## Search Benchmark Portability

Search-quality benchmark sets can now be exported as JSON bundles containing:

- benchmark set name;
- stable case key;
- query text;
- result type and search filters;
- language and topic labels;
- notes;
- graded relevance judgments and rationale.

The same bundle can be imported into another environment. Import merges by stable case key and upserts included judgments.

## Multidimensional Retrieval Slices

Benchmark evaluation continues to calculate Precision@K, Recall@K, MRR and NDCG@K, but now also stores slices by:

- language;
- topic key;
- result type.

Every slice includes query count, judged-query count, relevant-query count and judgment coverage. This is designed to prevent a strong high-volume segment from hiding weak retrieval in Hindi, entity search, or a specific policy topic.

## Slow-query Diagnostics

`/api/v1/search-quality/slow-diagnostics` groups slow observations by privacy-preserving query fingerprint, result type and filter shape. It reports p50/p95/max/mean latency, cursor-page ratio and result-volume statistics, then produces staging-oriented diagnostic suggestions.

Raw analyst query strings are not persisted in operational search telemetry.

Diagnostics are hints for reproducing the fingerprint with PostgreSQL `EXPLAIN ANALYZE` in staging. They are not automatic database-plan conclusions.

## Database Migration

New head:

`0028_entity_resolution_benchmark_expansion`

Changes:

- `canonical_entities.resolution_status`;
- `canonical_entities.merged_into_entity_id`;
- `entity_resolution_candidates`;
- `entity_resolution_actions`;
- indexes for active/merged lookup and resolution queue/history.

## Epistemic Guardrails

- Shared aliases are conflict candidates, not proof of identity.
- No fuzzy similarity automatically creates a merge.
- Merge direction is always explicit and human-approved.
- Alias split moves only exact persisted alias mentions.
- Merged source records remain visible for audit.
- Search benchmark aggregate metrics must be read together with judgment coverage and slice metrics.
- Slow-query telemetry stores fingerprints/filter shapes, not raw query strings.
- Semantic reranking remains deferred until a sufficiently judged lexical benchmark demonstrates a meaningful retrieval gap.

## Validation

Release validation performed in the development sandbox:

- Python compileall: PASS.
- Existing v1.18 + new v1.19 focused tests: PASS.
- Full unit suite under the sandbox-only external `structlog` stand-in: 360/360 PASS.
- Rendered JavaScript syntax for Entity Directory, Entity Resolution Queue, Entity Profile and Search Quality: PASS via `node --check`.
- Alembic single head: `0028_entity_resolution_benchmark_expansion`.
- Offline SQL generation from `0027` to `0028`: PASS.

The temporary logging stand-in is outside the repository and is not included in the release package.

Additional release-gate results:

- `uv lock --check --offline`: PASS.
- FastAPI/OpenAPI generation: PASS, application version `1.19.0`, 162 paths.
- Release-tree integrity: PASS with zero forbidden cache/bytecode/shim artifacts and zero populated example secrets.
- Integration tests: 1 PASS; liveness lifespan test BLOCKED by the sandbox's missing locked `asyncpg` driver. This is not reported as a PostgreSQL integration pass.
