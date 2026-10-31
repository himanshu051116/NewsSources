# Adaptive Extraction & Semantic History 1.4.0

**Release:** 1.4.0  
**Alembic head:** `0021_adaptive_extraction_semantic`

Version 1.4.0 improves two bottlenecks that remained after the 1.3 coherence release: extraction of modern JavaScript-framework news pages and genuinely semantic historical retrieval.

## Adaptive publisher extraction

The generic HTML extractor now accepts a persisted publisher extraction profile. Profiles can add low-value/subscription phrases and DOM attribute filters and can prefer a proven extraction method. Method recommendations are learned conservatively from repeated accepted pages; a single page is never enough to change a recommendation.

The extractor also inspects bounded JSON hydration state embedded in server responses, including `application/json` scripts and common Next.js/Nuxt/Apollo state containers. It can recover headline/byline/date/body fields when the visible server-rendered DOM is sparse.

This release intentionally does **not** add a networked headless-browser fetcher. A browser can issue subresource requests that bypass assumptions made by the existing SSRF-aware HTTP fetcher. Browser rendering should be introduced only as a separately sandboxed renderer with its own DNS, redirect, resource, and egress controls.

## Optional local semantic historical retrieval

PostgreSQL full-text search remains the canonical historical retrieval path. When explicitly enabled, 1.4.0 can additionally:

1. create article-version embeddings using a local Ollama embedding model;
2. persist derived vectors in the existing Qdrant service;
3. apply the article's historical cutoff inside vector retrieval;
4. merge semantic matches with PostgreSQL/event/claim history;
5. rerank them with explainable entity and lexical signals;
6. continue normally if the optional semantic service is unavailable.

Qdrant is a derived index and can be rebuilt from PostgreSQL article versions. No paid or remote AI provider fallback is used.

### Local opt-in

Keep semantic retrieval disabled until Ollama and the selected embedding model are installed locally. Then set, for example:

```env
NEWSINTEL_AI_PROVIDER=local
NEWSINTEL_LOCAL_MODEL_BASE_URL=http://localhost:11434
NEWSINTEL_SEMANTIC_SEARCH_ENABLED=true
NEWSINTEL_SEMANTIC_EMBEDDING_MODEL=nomic-embed-text
NEWSINTEL_SEMANTIC_VECTOR_SIZE=768
NEWSINTEL_SEMANTIC_QDRANT_COLLECTION=article_versions_v1
```

If a different embedding model is used, set `NEWSINTEL_SEMANTIC_VECTOR_SIZE` to that model's vector dimension. When changing to a model with a different vector dimension, use a new Qdrant collection name (or deliberately rebuild the old derived collection).

## Infrastructure cleanup

Redis remains available behind the Compose profile `event-bus`, but it is no longer started by the default local service scripts because the current application does not yet use Redis as its workflow bus or cache. Qdrant remains in the default local stack because it now has a concrete optional semantic-history role.

## Persistence

Migration `0021_adaptive_extraction_semantic` adds:

- `publisher_extraction_profiles`;
- `article_versions.semantic_indexed_at`;
- `article_versions.semantic_model`;
- `article_versions.semantic_content_sha256`;
- indexes for profile lookup and pending semantic indexing.

The semantic fields describe a rebuildable derived index; article text and immutable versions remain authoritative in PostgreSQL.

## Guardrails

- semantic similarity is historical-linkage evidence, not factual truth;
- semantic retrieval respects the same historical observation cutoff as other automatic history;
- profile learning cannot bypass robots/access controls or retrieve subscriber-only content;
- extraction recommendations require repeated evidence and remain operator-overridable;
- hydration parsing is bounded by payload/object/depth limits;
- absence of Ollama/Qdrant does not block article ingestion or PostgreSQL historical analysis.

## Deferred intentionally

The following remain future work rather than being hidden behind weak implementations:

- sandboxed headless-browser rendering for pages whose article body truly requires JavaScript execution;
- generalized dependency invalidation for every derived intelligence artifact;
- a real Redis Streams/event-bus topology;
- benchmarked multilingual embedding/event models.
