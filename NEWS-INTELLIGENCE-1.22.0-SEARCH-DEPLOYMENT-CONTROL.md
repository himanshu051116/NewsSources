# News Intelligence 1.22.0 — Production Search Deployment Control

## Purpose

Version 1.22 turns the v1.21 search promotion decision into a **controlled, auditable deployment workflow** without making promotion automatic. Production search still defaults to PostgreSQL lexical retrieval and semantic exposure defaults to **0%**.

## Rollout states

The production control plane supports four explicit states:

- `off` — lexical search only; target exposure is forced to 0%;
- `shadow` — a deterministic user cohort runs the semantic reranker, but the lexical ranking is still served. In v1.22 this runs synchronously so it intentionally measures semantic-path latency and can add latency to assigned requests; keep exposure small;
- `canary` — a deterministic user cohort receives page-local hybrid article reranking;
- `paused` — lexical search only after an operator or circuit-breaker pause.

`shadow` and `canary` require a human `approve_candidate` decision whose promotion-gate evaluation is `PASS`. If that approval is later superseded by `hold` or `reject`, runtime routing safely falls back to lexical search.

## Scope guardrail

The canary is **article-only** because article-version embeddings are the only semantic representation benchmarked by v1.20/v1.21. Event, claim, entity and mixed-result searches remain lexical.

The reranker only reorders the lexical result page. It cannot inject semantically-only results. The lexical cursor remains canonical so pagination stays stable.

## Deterministic bucketing

Users are assigned with a salted SHA-256 bucket based on the approved platform user ID. The rollout salt is generated once for the deployment record and remains stable across percentage changes, giving consistent cohort membership during a rollout.

No raw user ID is written to search deployment telemetry. A salted subject fingerprint is stored only so result-open telemetry can be tied to the correct exposure.

## Fallback behavior

If the semantic service, Qdrant collection or current-version semantic coverage is unavailable during an assigned canary request, the request returns lexical results and records the semantic failure. Search availability is therefore not coupled to the experimental reranker.

## Circuit breaker

The production deployment has explicit operational thresholds:

- maximum hybrid p95 latency;
- maximum hybrid error rate;
- minimum sample count before a breaker can trip;
- rolling observation window;
- optional automatic pause.

When an active canary **or shadow cohort** exceeds a configured breaker after the minimum sample count, the deployment is transactionally changed to `paused`, exposure is set to `0%`, and an `auto_pause` action records the reason and previous target percentage.

## Emergency rollback

Verification-capable operators have an **Emergency pause** action in Search Quality. It sets exposure to 0% immediately and records a mandatory rationale. Benchmark runs, gate evaluations, approvals and deployment telemetry are preserved.

## Live rollout telemetry

`search_deployment_observations` records privacy-preserving rollout data:

- deterministic bucket;
- assigned variant;
- actually served variant;
- query fingerprint rather than query text;
- result type;
- request duration;
- success/failure;
- fallback reason.

Result opens are recorded separately through `search_deployment_outcomes`. The UI shows lexical and hybrid **open-result rates only as an engagement proxy**. They are not presented as relevance, correctness or factual-truth metrics.

## Audit trail

`search_deployment_actions` stores rollout configuration changes, manual pauses and automatic circuit-breaker pauses with previous/new state, target percentage, rationale, actor and metadata.

## API additions

- `GET /api/v1/search/deployment`
- `PUT /api/v1/search/deployment`
- `POST /api/v1/search/deployment/rollback`
- `POST /api/v1/search/deployment/outcome`

The normal `/api/v1/search` route now passes through a production search facade that stays lexical unless all deployment conditions are satisfied.

## Schema

Alembic advances to the single head:

`0031_search_deployment_control`

New tables:

- `search_deployments`
- `search_deployment_observations`
- `search_deployment_outcomes`
- `search_deployment_actions`

Production schema-readiness checks require the new tables and indexes.

## Validation completed

- Python source/tests/migrations compile successfully.
- Unit regression suite: 384 passing in the release environment used for this build, with a temporary external `structlog` stand-in because that package is unavailable in the sandbox. No stand-in is shipped.
- Rendered Search and Search Quality JavaScript pass `node --check`.
- FastAPI OpenAPI generation succeeds at version 1.22.0 with the new deployment endpoints registered.
- Alembic reports one head at `0031_search_deployment_control`.
- Offline SQL generation for `0030 -> 0031` succeeds.

The real database-lifespan integration test remains environment-limited when `asyncpg` is unavailable in the sandbox; this release does not claim that blocked test passed.

## Deferred intentionally

v1.22 does **not**:

- auto-promote a PASS benchmark;
- expose semantic reranking to events, claims, entities or mixed search;
- use result-open telemetry as relevance truth;
- use cross-user random bucketing that changes between requests;
- remove lexical fallback;
- deploy a semantic-only recall path.

The next meaningful milestone is a measured canary-analysis layer: statistically safer live comparisons, cohort/sample-balance checks, multi-window rollback criteria and an explicit graduation gate from small canary to broader exposure.
