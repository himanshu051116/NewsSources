# News Intelligence 1.15.0 — Analyst Workspace

## Purpose

Version 1.15 turns the intelligence surfaces added in 1.11–1.14 into a persistent working environment. The core design rule is that analyst organization must never change evidence semantics: adding an event to an investigation, saving a search, or acknowledging an alert does not alter article versions, claim verification, correction records, evidence links, or historical context.

## New persistent workspace

The release adds migration `0024_analyst_workspace` and the following canonical tables:

- `investigations`
- `investigation_items`
- `analyst_notes`
- `saved_searches`
- `watchlists`
- `watchlist_items`
- `workspace_alert_acknowledgements`

The expected schema revision for health checks, doctor/readiness checks, release validation, and setup is now `0024_analyst_workspace`.

## Investigations

Analysts can create private investigations with a title, description, priority and active/archived state. An investigation can track existing:

- events;
- articles;
- claims.

Targets are resolved against canonical database rows before they can be stored. Arbitrary UUIDs are therefore rejected instead of becoming dead workspace references.

Each investigation exposes:

- tracked material;
- analyst notes;
- saved searches;
- status and priority;
- an evidence manifest export.

Workspace rows are owner-scoped at the service layer. Requests for another analyst's investigation, note, saved search or watchlist return not-found rather than exposing the resource.

## Analyst notes

Notes are stored separately from source evidence. They can be pinned and are explicitly analyst-authored observations, hypotheses or follow-up questions. They do not become evidence and are not used by verification policy.

## Saved searches

A corpus query can be saved from Intelligence Search and optionally attached to an investigation. The saved record preserves the query and selected result-type filter. Reopening the search restores that filter.

## Watchlists and alerts

Watchlists monitor only explicitly selected event/article/claim targets.

Alerts are derived from real stored state rather than a generic AI importance score:

- human-registered article corrections or retractions affecting watched events/articles;
- unresolved claim review flags created after a claim was watched;
- later claim-verification records on watched claims;
- material-event-change timestamps occurring after an event entered a watchlist.

Acknowledging an alert only writes a workspace acknowledgement record. It does **not** resolve a claim review flag, remove a correction, or rewrite verification state.

If one underlying correction is relevant to multiple watchlists, the alert is deduplicated by correction identity while preserving the union of relevant watchlist IDs.

## Evidence manifest

`GET /api/v1/investigations/{id}/manifest` returns a reproducibility-oriented snapshot of tracked material.

For tracked articles the manifest records the latest stored version identity, version number, retrieval timestamp and content hash.

For tracked claims it records the latest stored verification decision and the current linked evidence records, including source URL, relationship, independence score and stored lineage key.

For tracked events it records lifecycle/assignment state and material-change timestamps.

The manifest also includes investigation notes and saved searches. It is an export of stored state, not a new verification judgment.

## UI integration

New authenticated surfaces:

- `/investigations`
- `/investigations/{id}`
- `/watchlists/{id}`

The main Command Center links to Investigations and, for analyst-capable users, shows counts for active cases, watchlists, saved searches and unacknowledged watch alerts.

Event Dossiers, Article Intelligence and Claim Investigation expose **Add to workspace**. The handoff opens the workspace with the exact event/article/claim target preselected, where the analyst can choose an investigation and/or watchlist.

## Permissions

The workspace requires `claims:view` (the existing analyst permission). Viewers do not receive the Investigations navigation item and workspace APIs remain permission protected.

## Privacy and caching

Authenticated `/investigations` and `/watchlists` UI paths are now included in the application's `private, no-store` cache policy.

## Validation performed in this environment

- complete Python source compilation: PASS;
- Alembic single head: `0024_analyst_workspace`;
- offline Alembic upgrade SQL generation: PASS;
- rendered JavaScript syntax validation for Search, Investigations, Watchlists, Article Intelligence, Event Dossier and Claim Investigation: PASS;
- selected regression suite covering workspace UI plus event matching/assignment, claim extraction, evidence passage selection, stance assessment, historical enrichment, circular sourcing, conflict resolution, temporal reasoning, extraction fidelity, lineage, ownership independence, versioning, correction detection/propagation and dependency propagation: PASS (82 tests at the primary v1.15 checkpoint);
- repository release-integrity check: PASS (`failure_count: 0`, package/project version `1.15.0`, expected schema revision `0024_analyst_workspace`, no forbidden artifacts or populated example secrets).

The full project test suite was attempted, but collection is blocked in this sandbox because the frozen runtime dependency `structlog` is not installed here. The same environment also cannot complete `uv lock --check --offline` because Alembic is not present in the local uv package cache and outbound registry access is disabled. These are environment limitations; the 82 dependency-light regressions, Alembic checks, rendered-JavaScript checks and release-integrity check are reported separately.

## Important limitations

1. Investigations are private to their owner in 1.15. Team sharing and case-level collaboration permissions are intentionally deferred.
2. Watchlist alerts are computed when requested; there is no background notification delivery in this release.
3. Saved searches persist query/filter intent but do not yet run on a schedule.
4. The evidence manifest is JSON and does not yet provide a signed PDF/briefing export.
5. The corpus search backend is still the correctness-first database search foundation; PostgreSQL FTS/cursor ranking remains the next search-scale upgrade.

## Recommended next development

The next highest-value release should focus on **collaboration + scheduled monitoring + export quality**, after the current workspace has been tested against a real PostgreSQL dataset:

- investigation sharing with explicit reader/editor roles;
- recurring saved-search/watchlist evaluation through a durable worker;
- alert delivery policies and rate limiting;
- analyst activity/audit history;
- evidence-manifest Markdown/PDF briefing export;
- full-text indexed global search with cursor pagination;
- richer entity/source additions to investigations after the entity explorer is exposed in the UI.
