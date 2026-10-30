# Provenance, Entity & Calibration Upgrade 0.7.0

**Release:** 0.7.0  
**Migration head:** `0014_ownership_entities_calibration`

## Purpose

0.7.0 raises the quality ceiling of evidence-backed news checking by making corroboration more realistic, official-record retrieval more structured, historical entities more stable, and verification confidence empirically measurable.

The release preserves a critical separation:

- **evidence stance** asks what a passage says relative to a claim;
- **source independence** asks how much separate corroboration the source contributes;
- **publisher reliability** is historical context only;
- **confidence calibration** measures whether the verification engine's stated confidence matches externally adjudicated outcomes.

None of these dimensions is allowed to substitute for claim-level evidence.

## Specialized official-record adapters

Evidence authorities now support:

- `generic_html_search`;
- `direct_document_template`;
- `generic_json_search` with an explicit allow-list of candidate URL field names;
- `ckan_package_search` for CKAN-style public data catalogs;
- `socrata_catalog_search` for Socrata-style dataset discovery.

All adapters remain behind the v0.6 authority domain allow-list, robots policy, SSRF protections, redirect-hop validation, size limits and administrator configuration. Structured adapters cannot authorize a new host by discovering it in a response.

CSV/TSV public-data responses can now be converted into bounded textual evidence for numeric/statistical comparison. Raw-artifact retention remains a separate concern.

## Ownership-aware and circular-source corroboration

0.7.0 adds time-bounded media ownership groups and publisher memberships. Shared ownership can conservatively reduce an evidence source's independence weight, but it never changes evidence stance or assigns a factual/bias label to a publisher.

Explicit circular sourcing is also detected when an apparent corroborating report directly attributes the relevant assertion back to the originating publisher. Such evidence can remain useful as context while receiving very low independent-corroboration weight.

Article evidence-readiness is now `evidence-readiness-v4`. Independent evidence depth uses the **sum of effective independence weights**, not raw URL count. A new `source_independence_integrity` dimension exposes how much the apparent evidence set survives syndication, same-source, ownership and circular-sourcing caps.

## Canonical entity registry

The release adds:

- canonical entities;
- aliases;
- optional external identifiers;
- country/type constraints;
- ambiguity-aware deterministic matching.

Unambiguous registered entities can be reused in temporal event graphs. Ambiguous aliases are not force-merged. Analysts can explicitly create unmatched entities and add aliases.

## Indexed historical knowledge retrieval

Temporal knowledge nodes now maintain a bounded `search_text` field with a PostgreSQL GIN full-text index. A cross-event search API supports node-type filters and an `as_of` timestamp, so later graph observations are excluded from historical queries.

Existing graph nodes are backfilled with their labels during migration; rebuilding an event graph enriches the index with node payload text.

## Empirical confidence calibration

0.7.0 introduces explicit benchmark cases containing:

- predicted verification label;
- predicted confidence;
- externally adjudicated label;
- adjudication source;
- optional claim linkage and weight.

Calibration snapshots report:

- Brier score;
- expected calibration error (ECE);
- mean stated confidence;
- empirical accuracy;
- confidence-bin statistics.

The calibration service does **not** use the model's own later output as ground truth. External adjudication remains required.

## Production-readiness hardening

`newsintel-doctor` and `/api/v1/health/ready` now verify the v0.7 migration revision and required database relations, including the temporal full-text index. The doctor also reports PostgreSQL version and whether PostGIS is installed.

The expected release schema is:

`0014_ownership_entities_calibration`

## New API surfaces

- `GET/POST /api/v1/ownership-groups`
- `POST /api/v1/ownership-groups/{group_id}/publishers/{publisher_id}`
- `GET /api/v1/publishers/{publisher_id}/ownership`
- `POST /api/v1/entities/resolve`
- `POST /api/v1/entities/{entity_id}/aliases`
- `POST /api/v1/verification-calibration/cases`
- `POST /api/v1/verification-calibration/{benchmark_set}/assess`
- `GET /api/v1/verification-calibration/{benchmark_set}`
- `GET /api/v1/historical/knowledge-graph/search`

## Deliberate non-goals

0.7.0 does not claim that ownership implies editorial coordination, does not infer political bias, does not automatically merge ambiguous entities, does not treat confidence as factual probability without calibration, and does not permit structured authority adapters to escape configured authority domains.
