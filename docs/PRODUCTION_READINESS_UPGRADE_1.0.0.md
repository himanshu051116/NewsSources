# Production Readiness Upgrade 1.0.0

**Release:** 1.0.0  
**Migration head:** `0017_production_readiness`

Version 1.0.0 turns the v0.9 validation/propagation foundations into an auditable production-readiness layer. It does not introduce an opaque truth model. The release concentrates on reproducibility, dependency-aware correction handling, deployment safety, and operational evidence that the configured system is fit to serve traffic.

## Verification reproducibility manifests

Each immutable claim-verification revision can now receive a `verification-manifest-v1` record. The manifest captures the state available at the verification timestamp rather than later evidence:

- claim and article-version content hashes;
- verification label, confidence, methodology and reasoning trace;
- passage-level evidence hashes, stance, temporal relation, independence and primary-source state;
- legacy evidence-link provenance where still applicable;
- evidence-search run state and retrieval completion;
- retrieval body hashes and authority IDs;
- non-secret authority configuration snapshots;
- the latest conflict and search-stopping state that existed by the verification timestamp;
- review flags that already existed at that time;
- the application code version.

A canonical JSON representation is SHA-256 hashed. Rebuilding from the same immutable database state produces the same manifest digest. A bounded backfill endpoint creates manifests for older verification revisions without rerunning or changing those historical verdicts.

## Dependency-aware correction and retraction propagation

Previous releases marked claims directly contained in a corrected/retracted article for review. Version 1.0 additionally traces downstream claims that used the affected article as evidence.

Propagation understands both:

- `claim_evidence_links`; and
- passage-level `evidence_passage_evaluations` whose source URL corresponds to the affected article/version.

Propagation is bounded by configured maximum depth and claim count. Each downstream impact records its path depth, evidence record, severity and rationale. A dependent claim is marked for review; its historical verification label is never changed automatically. Indirect propagation is intentionally less severe because an article-level dependency does not prove that the corrected passage was the exact basis of every downstream claim.

## Production readiness assessment

The new production-readiness gate combines operationally important evidence without pretending that deployment readiness equals factual truth. It checks:

- current database revision against the release schema;
- latest held-out verification quality-gate state for a selected benchmark set;
- reproducibility-manifest coverage over a bounded sample of recent verification revisions;
- open critical correction/retraction review flags;
- general open review flags as warnings;
- availability of at least one active administrator-approved evidence authority when required.

Assessments are persisted and remain auditable over time.

## Stronger deployment configuration validation

Production settings now also reject:

- the repository's default local PostgreSQL credentials; and
- a non-HTTPS public base URL.

Existing production checks for authentication, cookie security, object-store secrets, CORS, raw-artifact storage and JWT/OIDC safety remain in place.

## Readiness and operations

`/api/v1/health/ready` now checks the v1.0 table/index contract instead of the older v0.8 relation set. `newsintel-doctor` uses the same v1.0 contract.

Operational status/Prometheus output now exposes:

- open claim review flags;
- open critical review flags; and
- total verification reproducibility manifests.

Every HTTP response receives a validated/generated `X-Request-ID` and `Server-Timing` application duration. Unsafe or oversized inbound request IDs are replaced instead of reflected.

A bounded `scripts/smoke-load.py` utility measures p50/p95/p99 response latency and error rate against an operator-selected GET endpoint. Its result is an environment measurement only; the repository does not ship fabricated latency claims.

## Release validation

The cross-platform release validators now expect `0017_production_readiness`, run a release-tree integrity check, and support `NEWSINTEL_STRICT_VALIDATION=1`. Strict mode fails if `ruff` or `mypy` is unavailable rather than silently warning.

`release-integrity.py` checks version synchronization, expected schema/migration identity, populated secret-like values in `.env.example`, and accidental cache/bytecode/dependency-shim inclusion.

## New API workflows

```text
GET  /api/v1/corrections/{correction_event_id}/dependency-propagation
POST /api/v1/claims/{claim_id}/verification-manifests
GET  /api/v1/claims/{claim_id}/verification-manifests
POST /api/v1/verification-manifests/backfill
POST /api/v1/system/release-readiness/{benchmark_set}
GET  /api/v1/system/release-readiness/{benchmark_set}
```

## Guardrails retained

- Verification manifests reproduce a decision context; they do not prove that decision correct.
- Corrections/retractions create stale/review state rather than silently mutating prior verdicts.
- Downstream propagation is bounded and conservative.
- Publisher reputation and ownership do not decide current factual truth.
- Evidence-authority scope remains administrator-controlled and redirect constrained.
- A passing production-readiness gate does not claim universal factual accuracy.
