# Evidence Graph & Reliability Upgrade 0.6.0

**Release:** 0.6.0  
**Upgrade focus:** constrained primary-evidence execution, corroboration lineage, empirical publisher/topic reliability, and temporal event knowledge graphs.

## Why this release exists

0.5.0 could plan authoritative evidence requirements, evaluate supplied passages, preserve verification revisions and reconstruct event knowledge snapshots. The missing operational layer was a safe way to execute approved authority searches, distinguish repeated reporting from genuinely independent corroboration, learn a publisher's historical performance without turning reputation into a truth shortcut, and query historical knowledge as a time-bounded graph.

0.6.0 fills those gaps without replacing the existing acquisition, claim, evidence or historical tables.

## Executable approved-authority retrieval

The new authority-search adapter accepts only administrator-configured authority profiles. A profile defines an adapter type, an allow-list of authority domains, an evidence class and an optional search URL template. Templates accept only the `{query}` placeholder and cannot embed API-key/token/secret query parameters.

The authority allow-list is passed into the safe HTTP fetcher itself. Every redirect hop is checked before it is fetched, including redirects encountered while retrieving `robots.txt`. A search response may discover candidate evidence URLs only inside the approved authority scope. Retrieved documents are bounded and persisted as retrieval attempts linked to the evidence-search run.

Retrieval deliberately does not mark an evidence-search run complete. Completion remains explicit so a partial authority response cannot masquerade as exhaustive evidence checking.

## Corroboration lineage

Evidence corroboration now records deterministic content-lineage fingerprints. Evidence from the same configured authority or normalized domain is grouped into one lineage for verification aggregation. Near-republished text receives a conservative independence cap. Similarity changes corroboration weight only; it never changes whether a passage supports, disputes or contradicts a claim.

This prevents five syndicated copies of one report from being counted as five independent confirmations.

## Publisher/topic reliability

0.6.0 adds a deterministic news-topic classifier and Bayesian reliability snapshots scoped by publisher, topic and lookback window. The model uses verified historical claims, confidence/maturity weighting, a neutral prior and uncertainty intervals. Small samples remain close to neutral.

`SUPPORTED` contributes positive evidence, `CONTRADICTED` negative evidence, and `DISPUTED` contributes symmetrically. `UNSUPPORTED` and `NOT_CHECKABLE` are excluded rather than counted as publisher failures because absence of evidence is not proof of inaccuracy.

The latest reliability snapshot can appear in an article quality response as historical context, but it has **zero weight** in the evidence-readiness score. Current evidence remains the deciding input.

## Temporal event knowledge graph

The temporal graph materializes event, claim, entity, actor, commitment, verification and evidence nodes plus typed relationships. Evidence and verification revisions carry their own observation times, allowing an `as_of` query to reconstruct only the knowledge that existed at a selected time.

A graph-diff API compares two timestamps and returns added/expired nodes and edges. This supports questions such as “what became known between T1 and T2?” without injecting later evidence into the earlier state.

## Persistence

Migration `0013_evidence_graph_reliability` adds:

- `evidence_retrieval_attempts`;
- `publisher_reliability_snapshots`;
- `temporal_knowledge_nodes`;
- `temporal_knowledge_edges`;
- the authority adapter type field.

The migration chain remains single-headed.

## New API surface

- `POST /api/v1/claims/{claim_id}/evidence-search/{run_id}/execute`
- `POST /api/v1/publishers/{publisher_id}/reliability/recompute`
- `GET /api/v1/publishers/{publisher_id}/reliability`
- `POST /api/v1/historical/events/{event_id}/knowledge-graph/rebuild`
- `GET /api/v1/historical/events/{event_id}/knowledge-graph`
- `GET /api/v1/historical/events/{event_id}/knowledge-graph/diff`

## Security and interpretation guardrails

- authority scope is enforced before each network request and redirect hop;
- registered evidence class/domain matching is still required before primary-source weighting;
- secrets are not allowed inside authority search templates;
- authority retrieval does not imply search completeness;
- syndication similarity affects independence only, not stance;
- publisher reliability is historical context, not a current-claim truth score;
- unsupported claims do not automatically damage publisher reliability;
- temporal graph queries exclude evidence observed after the requested timestamp.

## Remaining work

The next useful release should add specialized authority adapters for important public-record systems, empirical calibration datasets, ownership-aware source lineages, stronger entity resolution across historical records, search/index support for the temporal graph, and deployment validation against a real PostgreSQL/PostGIS environment with the locked dependency set.
