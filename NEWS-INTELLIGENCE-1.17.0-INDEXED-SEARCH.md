# News Intelligence 1.17.0 — Indexed Search Infrastructure

## Purpose

Version 1.17 replaces the correctness-first corpus `ILIKE` search path with a ranked PostgreSQL full-text search service designed for interactive analyst retrieval and durable saved-search monitoring.

The release does **not** change claim verification semantics. Search rank is retrieval relevance, not factual confidence.

## Search architecture

The `/api/v1/search` endpoint now uses a dedicated `IntelligenceSearchService` rather than the already-large article query service.

Retrieval is based on PostgreSQL `websearch_to_tsquery('simple', ...)` and GIN indexes:

- `ix_article_versions_search_weighted_fts` — weighted current article version title/byline/body;
- `ix_events_search_fts` — event titles;
- `ix_article_claims_search_fts` — atomic claim text;
- `ix_events_lifecycle_changed` — event lifecycle/date filtering;
- `ix_articles_language_published` — language/date filtering;
- `ix_articles_publisher_published` — publisher/date filtering.

The existing `ix_article_versions_fts_simple` index remains intact for historical-corpus retrieval. The new weighted article index is additive so the migration does not disrupt the historical search path.

## Multilingual retrieval choice

The indexed corpus uses PostgreSQL's `simple` text-search configuration. This deliberately avoids English-only stemming and stop-word assumptions across mixed-language reporting. It remains lexical retrieval; language-specific analyzers and semantic reranking are separate future improvements.

## Ranking

Article search weights:

- title — `A`;
- byline — `B`;
- body — `C`.

Events and claims use direct lexical relevance. Results are ordered by:

1. full-text rank descending;
2. observed/occurred time descending;
3. result type;
4. stable UUID tie-breaker.

The raw rank is carried in the API result for diagnostics but the user interface does not present it as a truth/confidence score.

## Current-version semantics

Interactive article and claim search is restricted to the latest article version **as of the search snapshot**. Historical versions remain available through Article Evolution and Historical Research rather than being mixed into the current-reporting search results.

## Cursor pagination

Offset pagination is no longer used by `/api/v1/search`.

The endpoint returns an opaque `next_cursor` containing the last rank/time/type/id ordering key plus a fixed ingestion snapshot. The cursor is fingerprint-bound to:

- normalized query;
- result-type filter;
- language filter;
- publisher filter;
- lifecycle filter;
- date range;
- whether claim search was permitted.

A cursor from another query/filter/access scope is rejected with HTTP 400.

Newly-created corpus records after the snapshot do not enter later pages of the same search session. Existing records can still legitimately change through event/article workflows, so this is an ingestion snapshot rather than a database MVCC snapshot held across HTTP requests.

Exact result-type counts are calculated on the first page. Cursor pages do not repeat the expensive count query.

## Search filters

The Search workspace now supports:

- result type — all/events/articles/claims;
- language;
- publisher name or slug;
- event lifecycle;
- from date;
- to date.

Claim search remains permission-gated. A user without `claims:view` cannot force claim retrieval by editing the URL.

## Saved-search and monitoring compatibility

Saved searches now persist the active search filters. Re-running a saved search restores those filters.

The scheduled workspace monitor evaluates the same indexed query/filter contract. Alert links preserve all saved filters. The first monitor run remains a baseline and therefore creates no false "new result" alert.

## Migration safety

Schema head:

```text
0026_search_infrastructure
```

The new indexes are created with `CREATE INDEX CONCURRENTLY` inside Alembic autocommit blocks. This avoids replacing the existing historical FTS index and reduces write disruption on populated corpora.

## Backwards compatibility

The old `limit_per_type` search API parameter is temporarily retained as deprecated. `ArticleQueryService.search_intelligence()` is retained as a compatibility wrapper but delegates to the new indexed search service.

## Validation performed

- Python source compilation;
- focused v1.17 search tests;
- cursor query-binding and round-trip tests;
- filter/date validation tests;
- wildcard escaping tests;
- UI/API contract tests;
- rendered Search JavaScript syntax validation with Node;
- rendered investigation/workspace JavaScript syntax validation with Node;
- Alembic single-head validation;
- offline SQL generation for `0025 -> 0026`;
- existing navigation/search/workspace/doctor regression tests.

The complete environment-dependent suite is not claimed in the analysis sandbox when frozen runtime dependencies such as `structlog` are unavailable.

## Deferred after 1.17

The most useful next retrieval improvements are:

1. dedicated entity search/profile surfaces;
2. query analytics and slow-search telemetry;
3. optional semantic reranking after lexical candidate retrieval;
4. typo/fuzzy assistance without weakening deterministic ranking;
5. per-language analyzers once benchmark data justifies them;
6. search benchmark datasets measuring Recall@K, MRR/NDCG and latency.
