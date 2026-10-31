# Historical Context Quality 1.2.0

**Release:** 1.2.0  
**Focus:** ranked, deduplicated and self-reconciling historical enrichment.

Version 1.2.0 upgrades the automatic historical enrichment introduced in 1.1.0. Historical analysis remains asynchronous and time-safe, but prior material is no longer treated as equally relevant merely because it was retrieved by a historical channel.

## Main improvements

- `historical-enrichment-v2` assigns each prior item an explicit historical-link relevance score and rationale.
- Same-event prior versions and exact claim-family history receive stronger linkage evidence than loose lexical matches.
- Internal and external matches include lexical/entity-overlap signals while keeping the score explicitly scoped to historical linkage, not factual truth.
- URL normalization removes common tracking parameters before deduplication.
- Cross-channel duplicates are suppressed before historical depth and confidence are calculated.
- Context confidence measures coverage/linkage quality using top relevance, source diversity, channel diversity and duplicate penalties.
- Claim evolution now distinguishes temporal updates, numeric updates, wording updates and numeric revision candidates.
- Every context contains a structured `what_changed` summary and a high-level pattern such as `material_update`, `continuity_with_prior_reporting`, `mostly_new_reporting`, or `possible_conflict_or_revision`.
- Late-ingested older reports from the same event automatically requeue affected newer contexts for reconciliation without changing the original historical cutoff.
- Enrichment jobs record `refresh_count`, `last_refresh_reason`, and `last_reconciled_at` so automatic historical recomputation is observable.
- The source dashboard surfaces historical depth, context confidence and change pattern directly on article cards.
- Health/readiness checks now verify the v1.2 reconciliation columns in addition to the migration revision.

## Time semantics

Reconciliation never moves an article version's historical cutoff. A later-ingested article can be included only when its publication/observation time is earlier than that cutoff. The platform therefore improves incomplete history without introducing future knowledge into an earlier snapshot.

## Confidence semantics

Historical context confidence answers: **"How strongly and diversely is this article linked to prior material?"** It does not answer whether the current article or prior reporting is true.

## Database

Alembic head: `0019_historical_context_quality`.

The migration adds reconciliation metadata to `article_historical_enrichment_jobs` and is additive over 1.1.0.
