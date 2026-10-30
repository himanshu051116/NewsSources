# Primary Evidence & Temporal Knowledge Upgrade — 0.5.0

Release 0.5.0 builds on the 0.4.0 Evidence & Historical Intelligence layer. The release
focuses on a stricter question: **what evidence should exist for a claim, what passage does
that evidence actually say, does it refer to the same time window, and how did the platform's
assessment evolve as evidence arrived?**

## Core guardrails

- Evidence readiness remains separate from factual truth.
- A URL/source label does not become primary evidence merely because it is called a court
  order, government record, dataset, filing, or research paper.
- Primary-evidence weighting requires a match against an administrator-configured authority
  profile for the evidence class and source domain.
- Absence of evidence is never contradiction.
- Different values at different `as-of` times are treated as temporal updates until same-time
  evidence establishes a real conflict.
- Historical snapshots never inject later evidence into earlier platform states.
- Outcome silence never implies fulfillment or failure.

## Primary-evidence requirement planner

`primary-evidence-requirement-planner-v1` converts each claim's existing claim type and
extraction features into an evidence plan. Plans contain prioritized evidence classes,
search/query hints, authority hints, counterevidence requirements and completeness criteria.

Examples include court records for legal claims, regulator/exchange filings for company
results, official datasets for statistical claims, election-authority records for official
results, original statements/transcripts for attribution claims, and original scientific
papers/registries for scientific claims.

Plans are persisted in `evidence_search_runs`; completion is therefore a recorded system
state rather than an untraceable boolean supplied only at verification time.

## Evidence authority registry

The new `evidence_authority_profiles` registry records:

- evidence class;
- jurisdiction and language;
- base URL and allowed domains;
- optional search URL template;
- scoped trust metadata.

Evidence passages receive primary-source verification weight only when their source domain
matches an active authority profile for the selected evidence class. Subdomains are allowed;
suffix-spoofed domains are not.

## Passage stance + temporal reasoning

`passage-stance-temporal-v1` combines evidence-passage retrieval with normalized quantity,
polarity and time comparison. It can classify a passage as support, contradiction, dispute,
context, temporal update or insufficient evidence.

The temporal reasoner keeps publication/observation time separate from explicit text time and
resolves useful `as of`, relative-day and date references where enough context exists.

This prevents a common failure mode such as treating “12 affected as of Aug 12” and “27
affected as of Aug 14” as contradictory simply because the quantities differ.

## Durable evidence evaluations

`evidence_passage_evaluations` stores the exact evaluated passage, hash, source, evidence
class, stance, confidence, temporal relation and authority-profile provenance. Successful
passage evaluations can also create ordinary `claim_evidence_links`, preserving compatibility
with the existing verification engine.

Completing an evidence-search run triggers a new immutable claim-verification revision.
Earlier verification records remain unchanged.

## Evidence-readiness quality v2

The article quality profile now includes three additional dimensions:

- primary-evidence coverage;
- completed evidence-search coverage;
- temporal-context resolution.

The overall profile still reports `evidence_readiness_not_factual_truth`. Several repeated
secondary links therefore cannot substitute for a completed counterevidence search and a
validated primary record.

## Claim confidence history

Historical claim confidence is now directly queryable as a sequence of verification
snapshots. Each snapshot retains its methodology, confidence factors and reasoning trace.
Later evidence changes the current assessment by adding a new snapshot; it does not rewrite
what the platform concluded earlier.

## Commitment and outcome tracking

The release adds deterministic discovery of trackable promises, targets, deadlines, projects,
policies, investigations, legal processes and forecasts. These are stored as
`event_commitments` and can receive versioned `commitment_outcomes` such as fulfilled,
partially fulfilled, delayed, failed, cancelled, resolved, on-track or unknown.

Outcome assessment has a relevance guard and does not infer success/failure from silence.

## As-known-then event snapshots

The new event knowledge snapshot API reconstructs historical states using only article
versions, claim verifications and commitment outcomes observed by each timestamp. This makes
it possible to distinguish:

- what the platform knew then;
- what was disputed then;
- what later evidence changed;
- how tracked commitments evolved.

## New API surface

- `POST /api/v1/evidence-authorities`
- `GET /api/v1/evidence-authorities`
- `POST /api/v1/claims/{claim_id}/evidence-plan`
- `POST /api/v1/claims/{claim_id}/evidence/evaluate`
- `POST /api/v1/claims/{claim_id}/evidence-search/{run_id}/complete`
- `GET /api/v1/claims/{claim_id}/evidence-history`
- `GET /api/v1/historical/claims/{claim_id}/confidence-history`
- `POST /api/v1/historical/events/{event_id}/commitments/discover`
- `GET /api/v1/historical/events/{event_id}/commitments`
- `POST /api/v1/historical/commitments/{commitment_id}/evaluate`
- `GET /api/v1/historical/events/{event_id}/knowledge-snapshots`

## Schema

Alembic head advances to `0012_evidence_temporal_knowledge`, adding:

- `evidence_authority_profiles`;
- `evidence_search_runs`;
- `evidence_passage_evaluations`;
- `event_commitments`;
- `commitment_outcomes`.

## Dependency change

`python-dateutil>=2.9,<3` is now a direct dependency because temporal reasoning uses it
explicitly. It was already present transitively in the previous lock; the direct declaration
prevents accidental dependency breakage.

## Remaining work after 0.5.0

- authority-specific retrieval adapters that execute registered search templates safely;
- jurisdiction-specific primary-record connectors (courts, regulators, gazettes, statistics);
- full-corpus evidence-lineage clustering and ownership-aware independence;
- multilingual stance and contradiction benchmarks;
- entity-normalized temporal knowledge graph edges;
- outcome linking to structured official milestones and datasets;
- historical analog retrieval with explicit causal-structure features;
- empirical source reliability by topic, geography, language and time.
