# News Intelligence 1.18.0 — Search Quality & Entity Intelligence

## Purpose

Version 1.18 turns the v1.17 indexed-search foundation into a **measurable retrieval system** and makes the existing canonical entity registry a first-class analyst surface. The release deliberately does **not** add semantic reranking merely because vector search is available. Instead, it creates the benchmark and latency evidence needed to decide whether semantic retrieval would measurably improve the system.

## Search-quality programme

The release adds persistent benchmark queries, graded relevance judgments, benchmark runs and privacy-preserving search observations. Search quality can now be evaluated with:

- Precision@K;
- Recall@K;
- mean reciprocal rank (MRR);
- NDCG@K for graded relevance;
- judgment coverage / relevant-query coverage;
- p50, p95, mean and maximum benchmark latency.

An unjudged returned result is treated as non-relevant for benchmark calculations, so low judgment coverage is surfaced explicitly and must not be presented as a release-quality claim. Benchmark execution disables normal search telemetry to avoid contaminating operational latency observations.

The `/search-quality` analyst workspace supports creating benchmark queries, opening the live ranked search, reviewing the top ranked results directly, assigning relevance grades 0–3, and running benchmark evaluations. Manual UUID-based judgment entry remains only as a fallback.

## Privacy-preserving search telemetry

Operational search observations store query fingerprints, filter/scope metadata, result count/timing and cursor-page state. Raw analyst query text is not persisted in the search-observation table. Telemetry is used for latency and slow-query analysis rather than user profiling.

## Entity intelligence

Canonical entities and approved aliases now participate in analyst search. New surfaces include:

- `/entities` — searchable canonical entity directory;
- `/entities/{entity_id}/intelligence` — entity profile with aliases, external identifiers, linked claim/article/event counts and recent linked mentions;
- `/api/v1/entities/search` — indexed entity/alias search;
- `/api/v1/entities/{entity_id}/profile` — structured profile;
- `/api/v1/entities/{entity_id}/refresh-mentions` — verifier-only conservative mention refresh.

Automatic entity mention linking is intentionally precision-first. It accepts exact normalized canonical names and approved aliases already extracted in claim entity features. Fuzzy similarity is never allowed to silently create an identity link. An empty entity profile therefore means “no exact approved links recorded”, not “the entity is absent from the corpus”.

Entity mention refresh streams the current-version claim corpus in bounded batches instead of silently truncating at an arbitrary claim count.

## Global search changes

The v1.17 ranked PostgreSQL search now supports `entity` as a first-class result type for analyst-scoped users. Entity results use canonical/alias full-text indexes and keep the existing query-bound opaque cursor model.

Article-specific filters (publisher, language, lifecycle and dates) are rejected for entity-only search rather than silently returning an empty page. When those filters are used with an `all` query, entity matches are conservatively excluded because those filters do not have an equivalent meaning for canonical registry entities.

Saved-search monitoring preserves entity result type and executes through the same indexed search path.

## Database migration

Alembic advances to:

`0027_search_quality_entity_intelligence`

New durable tables:

- `search_benchmark_queries`;
- `search_relevance_judgments`;
- `search_benchmark_runs`;
- `search_query_observations`;
- `entity_mentions`.

New entity FTS indexes are created concurrently:

- `ix_canonical_entities_search_fts`;
- `ix_entity_aliases_search_fts`.

Production schema-readiness checks require the v1.18 tables/indexes rather than trusting only the Alembic revision marker.

## Validation completed in this build

- Python source/test/migration compilation: PASS.
- Focused v1.18/v1.17 search contracts: 18 PASS.
- Full unit suite with a sandbox-only `structlog` stand-in: 352/352 PASS.
- Rendered JavaScript syntax checked with Node for Search, Entity Directory, Entity Profile and Search Quality: PASS.
- FastAPI OpenAPI generation: PASS, 152 paths, application version 1.18.0.
- Alembic single head: `0027_search_quality_entity_intelligence`.
- Offline migration SQL `0026 -> 0027`: PASS.
- `uv lock --check --offline`: PASS.
- Integration tests: 1 PASS; the liveness integration test cannot start the real database lifespan in this sandbox because the frozen `asyncpg` runtime driver is not installed. This is an environment limitation and is not reported as a production integration pass.

The temporary logging stand-in used for sandbox unit-test collection lives outside the release tree and is not packaged.

## Guardrails retained

- Search metrics describe retrieval, not factual truth.
- Entity identity is not inferred from fuzzy text similarity.
- Entity profile absence is not evidence that an entity is absent from reporting.
- Semantic reranking is deferred until a labelled benchmark with adequate judgment coverage demonstrates a measurable benefit.
- PostgreSQL remains canonical; any future vector index remains derived/rebuildable.

## Next recommended release

v1.19 should use the now-measurable lexical baseline to improve **entity resolution and search evaluation quality**, not immediately add generic embeddings. High-value next work includes multilingual benchmark slices, alias-conflict review, entity merge/split workflow, slow-query diagnostics, benchmark dataset import/export and only then an A/B semantic reranking experiment if Recall@K/MRR/NDCG show a clear lexical gap.
