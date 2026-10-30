# News Intelligence 1.20.0 — Multilingual Retrieval & Controlled Reranking

## Purpose

v1.20 improves multilingual lexical retrieval and introduces a controlled semantic reranking experiment without changing the platform's production-search guardrails.

Production Intelligence Search remains PostgreSQL-first and auditable. Semantic retrieval is available only inside labelled article-search benchmarks and cannot silently replace the production ordering.

## Multilingual lexical retrieval

The v1.17 `simple` PostgreSQL FTS path remains the language-neutral baseline for Hindi/Devanagari and other scripts. v1.20 adds a second indexed English morphology path for Latin queries:

- Unicode NFKC query normalization plus whitespace normalization;
- script detection without inferring language from script alone;
- `simple` FTS retained for all searches;
- English `websearch_to_tsquery`/`to_tsvector` fallback for Latin queries unless an explicit non-English language filter is selected;
- concurrent GIN indexes for weighted article content, claims and event titles using the English configuration;
- production search mode labelled `postgres_fts_v3_multilingual`.

The query string itself is never translated or semantically rewritten by this layer.

## Suggestion-only query assistance

`GET /api/v1/search/assist?q=...` provides optional explicit suggestions from bounded, trusted corpus vocabulary:

- active canonical entity names;
- approved entity aliases;
- active publisher names;
- recently active event titles.

Suggestions use Unicode normalization and bounded spelling similarity. Cross-script fuzzy suggestions are rejected. Approved aliases can recommend the corresponding canonical entity name. Suggestions never execute automatically and never change filters automatically.

Script alone is intentionally insufficient to infer `language=hi`: Devanagari may represent Hindi, Marathi, Nepali, Sanskrit or another language.

## Controlled semantic article reranking

The existing local Ollama/Qdrant article-version index is reused only for a benchmark experiment:

1. production lexical search retrieves a candidate pool;
2. the local embedding model embeds the benchmark query;
3. Qdrant retrieves semantic article-version matches;
4. semantic hits are accepted only when the hit is the current article version at the lexical search snapshot;
5. only articles already present in the lexical candidate pool can be reordered;
6. reciprocal-rank fusion combines lexical and semantic rank;
7. the benchmark returns only the requested top K.

This experiment is article-only. Mixed event/claim/entity benchmark sets are rejected for hybrid evaluation.

No semantically-only article can enter the result set, and production `/api/v1/search` never enables the hybrid mode.

## Search Quality controls

`SearchBenchmarkRunCommand.search_mode` supports:

- `lexical` — production multilingual PostgreSQL baseline;
- `hybrid_article_rerank` — local semantic reranking experiment.

The Search Quality UI now exposes experiment availability, model/collection context, recent run modes and a direct lexical-vs-hybrid delta view for MRR/NDCG/Recall and p95 latency.

Comparisons are allowed only when both runs carry the exact same benchmark fingerprint. The fingerprint covers query definitions, filters and relevance judgments. If the labelled benchmark changed between runs, deltas are withheld and both modes must be re-evaluated.

No reranking mode is promoted automatically.

## Database migration

Alembic head:

`0029_multilingual_reranking_experiments`

Concurrent indexes added:

- `ix_article_versions_search_english_fts`
- `ix_article_claims_search_english_fts`
- `ix_events_search_english_fts`

The existing language-neutral indexes remain intact.

## Operational requirements for hybrid experiments

Hybrid benchmark evaluation is available only when:

- `NEWSINTEL_AI_PROVIDER=local`;
- `NEWSINTEL_SEMANTIC_SEARCH_ENABLED=true`;
- Ollama is reachable at the configured local model URL;
- Qdrant is reachable;
- current article versions have been semantically indexed by the historical-enrichment worker.

If any of those requirements is unavailable, production lexical search continues normally and the experiment returns an explicit unavailable/error state.

## Guardrails

- Query assistance is suggestion-only.
- Script detection does not claim language identity.
- Hindi/Devanagari retrieval continues through language-neutral PostgreSQL FTS.
- Semantic reranking is benchmark-only.
- Semantic reranking cannot inject results outside the lexical candidate pool.
- Historical article versions cannot contribute semantic rank to a current-version benchmark result.
- Lexical-vs-hybrid deltas require an identical labelled benchmark fingerprint.
- A higher NDCG/MRR does not automatically justify deployment; latency, slice performance, judgment coverage and operational cost must also be reviewed.

## Validation

Release validation includes:

- multilingual query/script unit tests;
- English-morphology SQL/index contract tests;
- RRF guardrail tests;
- suggestion-only UI/API contract tests;
- controlled semantic-mode contract tests;
- complete unit regression suite (369/369 passing in the release sandbox with a temporary external-only `structlog` stand-in);
- rendered Search and Search Quality JavaScript syntax checks;
- Alembic single-head/offline SQL validation;
- OpenAPI route validation;
- offline lockfile and release-integrity checks.

The sandbox used for release validation does not contain the frozen `structlog`/`asyncpg` runtime dependencies. Temporary external-only test shims may be used for unit collection, but no shim is included in the release package and real PostgreSQL lifespan tests are not claimed when `asyncpg` is unavailable.
