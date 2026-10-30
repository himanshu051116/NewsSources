# News Intelligence 1.21.0 — Search Promotion Gates & Production Evaluation

## Purpose

v1.21 turns the v1.20 lexical-vs-hybrid search experiment into an auditable release-readiness workflow. It does **not** enable semantic reranking in production. Instead, it persists a benchmark-specific promotion policy and evaluates comparable frozen benchmark runs against quality, coverage, latency, semantic-index freshness, and slice-regression thresholds.

## Promotion policy

Each benchmark set can persist one explicit policy covering:

- minimum query count;
- minimum relevance-judgment coverage;
- minimum relevant-query coverage;
- minimum NDCG@10, MRR and Recall@10 deltas;
- maximum hybrid p95 latency;
- maximum p95 latency regression over lexical search;
- minimum fresh semantic-index coverage;
- minimum judged queries per evaluated slice;
- maximum tolerated NDCG@10 regression for adequately judged slices;
- required language slices such as `en` and `hi`;
- optional required topic slices.

Default thresholds are conservative starting points, not universal standards. They are visible and editable by verification-capable users instead of being hidden constants.

## Gate semantics

A gate evaluation uses the newest lexical/hybrid pair that shares the exact same benchmark fingerprint. The fingerprint already includes query definitions, filters and relevance judgments.

The gate evaluates:

1. benchmark sample size;
2. judgment and relevant-query coverage;
3. ranking deltas;
4. absolute and relative p95 latency;
5. semantic-index freshness coverage;
6. required language/topic slices;
7. every other observed slice with enough judged queries.

States are `pass`, `warn`, `fail`, or `blocked`. A blocked run means like-for-like benchmark evidence is unavailable. A pass means only that the tested configuration met the saved thresholds; it never changes the production search mode automatically.

## Semantic-index coverage

Coverage is computed over **current article versions only**. A semantic entry counts as fresh only when:

- `semantic_indexed_at` is present;
- `semantic_content_sha256` matches the article version's current `content_sha256`;
- when an embedding model is configured, `semantic_model` matches that expected model.

The Search Quality UI reports current, indexed, fresh, missing, and stale article-version counts plus coverage percentages.

## Persistence and auditability

Alembic head: `0030_search_promotion_gates`.

New tables:

- `search_promotion_policies`
- `search_promotion_evaluations`
- `search_promotion_decisions`

Each evaluation stores:

- policy ID;
- lexical and hybrid benchmark run IDs;
- frozen benchmark fingerprint;
- gate state;
- every individual check and threshold;
- failures and warnings;
- semantic-coverage snapshot;
- evaluator identity;
- methodology version and interpretation.

## UI/API

New APIs:

- `GET /api/v1/search-quality/semantic-coverage`
- `GET /api/v1/search-quality/{benchmark_set}/promotion-policy`
- `PUT /api/v1/search-quality/{benchmark_set}/promotion-policy`
- `POST /api/v1/search-quality/{benchmark_set}/promotion-gate/evaluate`
- `GET /api/v1/search-quality/{benchmark_set}/promotion-gate/history`
- `POST /api/v1/search-quality/promotion-gate/{evaluation_id}/decisions`
- `GET /api/v1/search-quality/{benchmark_set}/promotion-decisions`

The Search Quality dashboard now contains a Promotion Gate panel and a separate Semantic Index Coverage panel. Policy editing and evaluation require verification permission; analysts can inspect policy and historical evaluations. A verifier can separately record `approve_candidate`, `hold`, or `reject` with rationale. Approval is accepted only for a PASS gate and remains governance metadata: it does not deploy or enable hybrid search.

## Additional correctness improvement

The normal lexical-vs-hybrid comparison now selects the newest **comparable** frozen-benchmark pair rather than blindly comparing the latest run of each mode when their benchmark fingerprints differ.

## Guardrails

- no automatic production switch exists;
- gate PASS is a release-review recommendation, not deployment authorization;
- no metric is interpreted without benchmark/judgment coverage;
- required Hindi/English slices can be made mandatory by policy;
- low-sample slices cannot silently satisfy a required-slice gate;
- semantic records with stale content hashes or obsolete embedding models do not count as fresh coverage;
- hybrid evaluation remains article-only and cannot introduce semantically-only results.

## Validation

Release validation includes:

- pure promotion-gate unit tests for pass/fail and required-slice behavior;
- schema/migration/API/UI contract tests;
- complete unit regression suite;
- Python compilation;
- rendered Search Quality JavaScript syntax validation;
- Alembic single-head and offline-SQL validation;
- OpenAPI generation;
- release-integrity validation, including the editable-project version stored in `uv.lock`.

`uv lock --check --offline` cannot complete in this sandbox because its local uv cache does not contain Alembic, and the normal online check cannot resolve PyPI DNS. The release-integrity checker therefore verifies the local editable-project lock version, but a full dependency-resolution lock check is not claimed here. The release sandbox also lacks the locked `asyncpg` driver, so the real PostgreSQL FastAPI lifespan integration test is not claimed when that dependency is unavailable.
