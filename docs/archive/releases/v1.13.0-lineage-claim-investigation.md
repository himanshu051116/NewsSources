# News Intelligence 1.13.0 — Lineage & Claim Investigation

## Release goal

This release fixes a critical presentation mismatch between the verification engine and the analyst UI. The verifier already deduplicates evidence by lineage and caps independence for likely republishing, shared ownership, and circular sourcing. Earlier UI views could still describe qualifying evidence links as "independent" even when multiple links belonged to the same lineage.

v1.13.0 makes the frontend use the same evidence-independence concepts as the decision layer and adds a dedicated Claim Investigation workspace.

## Major changes

### 1. Lineage-correct Event Dossier

Event claims now distinguish:

- raw evidence links;
- observed/deduplicated lineage keys;
- repeated same-lineage links;
- primary-source links;
- contradiction/dispute links;
- shared-ownership independence reductions;
- circular-sourcing flags;
- near-duplicate/syndication similarity signals.

The dossier deliberately labels event-wide lineage counts as **observed lineages**, not universal independent confirmations. A lineage can still have a reduced independence score.

### 2. Evidence-lineage intelligence panel

The Event Dossier now exposes an Evidence Lineage Intelligence section containing:

- observed lineage count;
- qualifying evidence-link count before lineage deduplication;
- ownership-reduced evidence count;
- circular and near-duplicate signals;
- top stored lineage identities;
- maximum stored independence score per lineage;
- primary/shared-ownership/circularity badges.

These are corroboration diagnostics, not publisher quality ratings.

### 3. Dedicated Claim Investigation workspace

New analyst page:

`/claims/{claim_id}/investigation`

New aggregate endpoint:

`GET /api/v1/claims/{claim_id}/dossier`

The workspace exposes:

- the atomic claim and parent article/event;
- current verification revision;
- raw evidence links and passages;
- evidence-lineage grouping;
- independence score and lineage-reduction signals;
- latest evidence-search run;
- latest conflict-resolution state;
- correction/retraction review flags;
- stored verification history.

Users with `claims:verify` also receive explicit auditable actions to:

- create an evidence plan;
- reassess evidence conflict;
- recompute verification using the current retrieval-complete state.

No action silently rewrites source material.

### 4. Search and Article Intelligence deep links

Claim search results now open Claim Investigation directly. Article claim cards and Event Dossier claim cards also link to the same investigation workspace.

### 5. Near-duplicate evidence visibility

Evidence whose stored `max_prior_lineage_similarity` is at least 0.70 is surfaced as a near-duplicate/syndication signal. This mirrors the threshold where the domain lineage policy begins reducing independence weight.

### 6. Cache/privacy coverage

The application security middleware now includes `/claims` in the private/no-store UI path set.

## Guardrails preserved

- Publisher count is not presented as independent-source count.
- Shared ownership is not treated as evidence of inaccuracy or coordination.
- Content similarity is not treated as proof of copying; it only affects corroboration independence and UI warnings.
- Historical context is not promoted to primary evidence.
- Stored confidence remains a decision-system field, not a universal truth probability.
- Verification continues to abstain when evidence is insufficient.

## Validation performed in this environment

- Complete Python source compilation: PASS.
- Selected dependency-light regression suite: **62 tests passed**.
- The suite includes UI navigation/search/lineage tests, event matching/assignment, claim extraction, evidence passage logic, stance assessment, historical enrichment, circular sourcing, conflict resolution, temporal reasoning, extraction fidelity, lineage similarity, and ownership independence.

The complete runtime suite is still not claimed here because the execution sandbox does not have all frozen runtime dependencies (notably `structlog`) installed and cannot fetch packages externally.

## Recommended next development pass

1. Article revision/correction visualization using existing version-diff and correction APIs.
2. Real ownership-group names/provenance in lineage views rather than only independence-reduction flags.
3. Evidence search orchestration progress, stopping assessments, and authority coverage in Claim Investigation.
4. PostgreSQL full-text indexes/ranking and cursor pagination for global search.
5. Saved investigations, notes, watchlists, alerts, and reproducibility exports.
