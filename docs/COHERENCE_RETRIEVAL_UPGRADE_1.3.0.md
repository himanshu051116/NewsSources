# Coherence & Retrieval 1.3.0

**Release:** 1.3.0  
**Alembic head:** `0020_coherence_retrieval`

Version 1.3.0 is a coherence release. It does not add another isolated intelligence subsystem; it strengthens the handoffs between event assignment, historical retrieval and the analyst UI.

## Event identity

- Replaces the misleading `event-matching-lexical-v1` policy with `event-matching-structured-lexical-v2`.
- Keeps the legacy `semantic_similarity` API field for compatibility but records an explicit `structured_lexical_similarity` feature. No embedding-derived semantic claim is made.
- Adds Unicode-aware tokenization so Indic combining marks do not fragment tokens.
- Adds English/Hindi event-type vocabularies and real event-type compatibility instead of the previous fixed `0.5` feature.
- Adds action overlap as part of structured lexical similarity.
- Rebalances event scoring so event-type compatibility has a material contribution.
- Uses `last_material_change_at` rather than `first_detected_at` for recent active-event candidate retrieval and expands the bounded candidate window to 45 days.

This is still deterministic matching. A future embedding/cross-encoder stage should be benchmarked before being introduced.

## Full-corpus historical retrieval

- Removes the automatic enrichment scan of only the latest ~800 article versions.
- Adds PostgreSQL full-text retrieval across the complete `article_versions` corpus, followed by the existing explainable lexical/entity reranker.
- Removes the prior-claim pattern that loaded the latest ~1,000 claims and filtered claim-family keys in Python.
- Queries matching `claim_family_key` values directly in PostgreSQL and batches verification lookup.
- Aligns manual internal historical research with the same full-corpus PostgreSQL FTS approach.
- Historical query construction and salient-term extraction are Unicode-aware.

Migration `0020_coherence_retrieval` adds:

- `ix_article_versions_fts_simple` — GIN index over the complete title/body text vector.
- `ix_article_claims_family_created` — expression index over `extraction_features ->> 'claim_family_key'` plus creation time.

## Article Intelligence UI

A normal story now opens `/articles/{article_id}/intelligence` instead of sending users to several raw JSON endpoints.

The workspace combines:

- headline and extracted body;
- canonical intelligence state;
- historical depth/linkage and change pattern;
- top historical matches;
- chronological prior-reporting timeline;
- claims and their latest verification state for analyst-authorized users;
- evidence-readiness dimensions for analyst-authorized users;
- direct original-source and event links.

Viewer accounts can still use the workspace; analyst-only claim/quality sections degrade cleanly rather than failing the entire page.

## Live state

The backend now exposes:

- `GET /api/v1/articles/{article_id}/intelligence-state`
- `GET /api/v1/articles/{article_id}/intelligence-stream`

The second endpoint is a bounded Server-Sent Events stream. The article workspace refreshes its intelligence view when extraction/history/review state changes, while browsers reconnect automatically after the bounded stream closes.

Canonical presentation states are:

- `discovered`
- `extracted`
- `enriching`
- `ready`
- `ready_with_warnings`
- `review_required`

These are a presentation projection over the durable extraction, historical-enrichment and review tables; they do not replace the detailed backend state machines.

## News vs source administration

- Adds viewer-accessible `/news` for reading extracted news.
- Keeps `/news-sources` as an operational source-management surface.
- The home workspace only displays Sources/Access Admin tiles when the authenticated role permits them.
- News cards link to Article Intelligence and the original publisher rather than raw API JSON.

## Query efficiency

The article feed no longer performs latest-version/history lookups one article at a time. It bulk-loads versions, historical contexts and enrichment jobs for the bounded feed result set, eliminating the most obvious article-list N+1 query pattern.

## Guardrails

- Historical linkage scores remain contextual coverage/relevance scores, not truth probabilities.
- Structured lexical event matching is not represented as embedding-level semantic understanding.
- Full-corpus FTS narrows candidate retrieval; explainable relevance signals remain visible in historical context.
- SSE connections are bounded and carry state only; they do not run evidence retrieval inline.
