# Accuracy & Evidence Orchestration Upgrade 0.8.0

**Release:** 0.8.0  
**Date:** 2026-08-13

## Purpose

0.8.0 changes the next quality bottleneck from “can the platform find evidence?” to “can it measure, plan, resolve and audit evidence checking without overstating certainty?” The release adds benchmark hygiene and end-to-end verification metrics, multi-authority evidence orchestration, explicit conflict-resolution history, provenance-preserving external entity identifiers, ownership provenance records, and graph-neighborhood historical research.

## Evidence orchestration

Evidence plans can now be converted into a bounded authority-selection plan. The planner prioritizes required evidence classes, jurisdiction/language fit, historical retrieval yield, previously attempted authorities and domain diversity. Selected authorities still execute through the v0.6/v0.7 domain allow-list, robots and SSRF controls.

An orchestration run persists:

- required evidence classes;
- selected authority IDs and rationale;
- uncovered evidence classes;
- coverage ratio;
- execution counts and status.

The presence of an authority in a plan is not evidence and does not change claim verification.

## Conflict-resolution workflow

Passage stance evaluations can now be aggregated into a separate conflict state:

- `resolved_support`;
- `resolved_contradiction`;
- `temporal_evolution`;
- `unresolved_conflict`;
- `insufficient`.

Lineage duplicate evidence is collapsed before weighting. Primary evidence on both sides forces preservation of a material conflict rather than a winner-by-count rule. Temporal updates can remain event evolution instead of contradiction.

Conflict resolution is stored as a revision history. It does not silently overwrite the underlying claim-verification history.

## Benchmark evaluation v2

Externally adjudicated benchmark cases now support explicit:

- case key;
- split (`train`, `dev`, `test`, or project-specific values);
- topic;
- language;
- jurisdiction;
- adjudicator count and adjudication time.

The benchmark evaluator reports:

- weighted accuracy;
- macro precision, recall and F1;
- per-label precision/recall/F1;
- confusion matrix;
- high-confidence error rate;
- selective accuracy and coverage at confidence thresholds.

A separate corpus audit detects cross-split identity leakage, duplicate cases, weak adjudicator coverage and missing held-out split structure. Calibration and classification-quality metrics remain separate: a model may be well calibrated while still inaccurate, or accurate on a narrow benchmark while poorly calibrated.

## Entity identity provenance

Canonical entities can now attach provenance-preserving external identifiers. Known identifier namespaces receive conservative shape validation; conflicting namespace/identifier links cannot be assigned to two canonical entities. The legacy `canonical_entities.external_ids` JSON field remains as a compatibility cache.

External identifiers improve entity resolution only. They do not validate claims about the linked person, organization or location.

## Ownership provenance

Publisher ownership memberships can now hold multiple timestamped provenance records containing source URL, source type, optional passage text/hash, observation time, validity window and confidence. This makes ownership-based independence caps reproducible across time.

Ownership metadata continues to be used only for corroboration independence. It is not a political-bias or publisher-truth score.

## Historical graph research

Analysts can request a bounded neighborhood around any temporal knowledge node with a depth of 1–4. The traversal respects the requested `as_of` state and returns only stored provenance relations visible at that time. Graph proximity is contextual connectivity, not causal implication.

## Article quality integration

The article quality endpoint now surfaces counts of latest claim conflict states:

- unresolved conflicts;
- temporal-evolution cases;
- resolved support/contradiction cases.

These are review context. The platform continues to report evidence readiness rather than a hidden “truth score.”

## Migration

Alembic head: `0015_accuracy_orchestration`.

The migration adds:

- `evidence_orchestration_runs`;
- `claim_conflict_resolutions`;
- `verification_benchmark_evaluations`;
- `entity_external_identifiers`;
- `ownership_provenance_records`;
- benchmark split/topic/language/jurisdiction/adjudication metadata and indexes.

## New APIs

- `POST /api/v1/claims/{claim_id}/evidence-search/{run_id}/orchestrate`
- `POST /api/v1/claims/{claim_id}/conflict-resolution`
- `GET /api/v1/claims/{claim_id}/conflict-resolution`
- `POST /api/v1/verification-benchmark/{benchmark_set}/assess`
- `GET /api/v1/verification-benchmark/{benchmark_set}`
- `GET /api/v1/verification-benchmark/{benchmark_set}/audit`
- `POST /api/v1/entities/{entity_id}/external-identifiers`
- `GET /api/v1/entities/{entity_id}/external-identifiers`
- `POST /api/v1/ownership-memberships/{membership_id}/provenance`
- `GET /api/v1/ownership-memberships/{membership_id}/provenance`
- `GET /api/v1/historical/events/{event_id}/knowledge-graph/neighborhood`

## Guardrails retained

0.8.0 does not convert publisher reputation into truth, does not treat source count as independent corroboration, does not resolve close primary-source conflicts automatically, does not permit evidence orchestration to bypass authority-domain controls, does not auto-fetch ownership-provenance URLs, and does not claim benchmark quality outside the scope of the adjudicated corpus.
