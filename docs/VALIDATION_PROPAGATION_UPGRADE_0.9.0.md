# Validation & Propagation Upgrade 0.9.0

## Purpose

Version 0.9.0 turns the v0.8 evidence-orchestration and benchmark foundations into a more disciplined validation workflow. It adds explicit evidence-search stopping decisions, correction/retraction propagation without silent verdict mutation, release quality gates, constrained entity-registry linking, and reproducible ownership-history ingestion.

The release keeps the platform's core rule: **evidence quality and uncertainty must remain inspectable.** A correction, registry match, ownership relationship, or benchmark score is never allowed to become an opaque truth signal.

## Evidence-search stopping

Evidence orchestration can now be assessed after each search run with one of five states:

- `continue` — material evidence requirements are still uncovered;
- `stop_sufficient` — required evidence classes, independence and primary-record requirements are satisfied;
- `stop_exhausted` — configured avenues have been searched with no material new yield;
- `stop_budget` — the bounded search budget has been reached;
- `escalate_conflict` — strong primary evidence remains materially inconsistent and requires review rather than more blind searching.

Stopping assessments are persisted. Their completeness score describes **search coverage**, not truth confidence.

## Correction and retraction propagation

The platform can detect and register correction candidates from article-version diffs. A registered correction creates durable propagation state and claim review flags.

- updates are recorded without automatically changing claim verdicts;
- clarifications request review when relevant;
- factual corrections mark affected conclusions stale/review-required;
- retractions create critical review flags and invalidate dependence on the retracted article as evidence;
- temporal-knowledge correction nodes preserve when the correction became known.

No propagation path silently rewrites a historical verification. A reviewer must explicitly resolve the review flag or run a new verification revision.

Article evidence-readiness responses now expose unresolved review-required and critical-retraction counts as context.

## Verification release quality gate

A held-out benchmark quality gate evaluates the `test` split using the existing benchmark-v2 metrics and corpus audit. It can fail a release for:

- identity leakage across benchmark splits;
- event/claim-family (`group_key`) leakage;
- same-source-document leakage;
- too few held-out cases;
- insufficient label diversity/sample size;
- low macro F1;
- excessive high-confidence error rate.

Selective accuracy/coverage issues can be surfaced as warnings. A high headline accuracy cannot override benchmark leakage.

## Benchmark corpus audit v2

Benchmark cases now support:

- `group_key` for event/claim-family grouping;
- `source_document_key` for source-document grouping;
- train/dev/test split metadata;
- topic, language and jurisdiction scope;
- adjudicator counts and adjudication time.

The audit detects paraphrases or related cases crossing splits even when their exact case IDs differ.

## Constrained entity-registry linking

Administrators can configure structured JSON entity registries. Registry searches reuse the v0.6 constrained-fetch security boundary:

- exactly one `{query}` placeholder is required;
- search and registry hosts must remain in the approved domain scope;
- every redirect hop is bounded by the fetch allow-list;
- URL-embedded API keys/tokens/secrets are rejected;
- external identifiers are persisted only when a match is unambiguous.

Registry linkage improves identity consistency. It does **not** validate factual claims involving that entity.

## Ownership-history ingestion

Version 0.9.0 adds bounded bulk ingestion of publisher ownership memberships and their provenance. Ingestion is idempotent for matching memberships/evidence and retains:

- source URL/type;
- evidence passage hash;
- validity window;
- observation timestamp;
- confidence/provenance metadata.

Ownership continues to affect only corroboration-independence estimation. It is not a political-bias or publisher-truthfulness label.

## New persistence

Alembic revision `0016_validation_propagation` adds:

- `evidence_search_stopping_assessments`;
- `article_correction_events`;
- `claim_review_flags`;
- `verification_quality_gate_runs`;
- `entity_registry_profiles`;
- `entity_registry_link_runs`;
- `ownership_ingest_runs`;
- benchmark `group_key` and `source_document_key` fields and supporting indexes.

The migration is additive and retains all v0.8 evidence, graph, ownership, entity and benchmark history.

## API additions

The release adds endpoints for:

- evidence-search stopping assessment/history;
- correction-candidate detection and correction registration/history;
- explicit claim-review-flag resolution;
- benchmark quality-gate execution/history;
- entity-registry administration and bounded linking;
- ownership-history bulk ingestion.

## Release validation

Release validation should execute:

1. `uv lock --check --offline`;
2. Python compilation;
3. repository tests;
4. exact single-head Alembic check for `0016_validation_propagation`;
5. full offline PostgreSQL migration SQL generation;
6. lint/type checks when the tools are installed;
7. a real locked-dependency PostgreSQL/PostGIS deployment test before production.

The supplied `scripts/validate-release.sh` and `scripts/validate-release.ps1` automate the locally available checks.
