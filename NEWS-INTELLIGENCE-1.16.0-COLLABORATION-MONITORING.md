# News Intelligence 1.16.0 — Collaboration & Scheduled Monitoring

## Goal

Version 1.16 turns the private analyst workspace into a controlled team workspace and adds durable, auditable monitoring for saved corpus searches. It does **not** change claim-verification semantics and does not describe search-window changes as factual truth.

## Collaboration

Investigations now support explicit access roles:

- **Owner** — full case control, collaborator management, archive/reopen.
- **Editor** — can add/remove tracked material and create notes/saved searches in the case.
- **Reader** — view-only access.

Collaborators are added by the exact verified email of an already-approved platform account. Sharing a case never grants platform permissions the account does not already possess.

The collaboration layer is owner/member scoped in the service layer, not only hidden in the UI. Investigation lists include owned and shared cases, and mutation operations enforce the minimum required case role.

## Investigation activity trail

Case-level activity is now persisted for important research actions, including creation, membership changes, tracked-item changes, notes and saved-search monitoring changes. Activity records retain actor, action, target, summary, metadata and timestamp.

This is an audit trail of analyst workflow. It is not source evidence.

## Scheduled saved-search monitoring

A saved search owned by an analyst can be scheduled at a minimum cadence of one hour. Supported UI presets include hourly, 3-hourly, 6-hourly, 12-hourly, daily and weekly evaluation.

Monitoring behavior is intentionally conservative:

1. enabling a monitor makes it due immediately;
2. the **first successful run creates a baseline** and generates no "new result" alert;
3. later runs compare the current monitored top-result window with the previous successful run;
4. only result keys entering that window are surfaced as new monitoring signals;
5. the alert explicitly states that this is a top-result-window change, not exhaustive web-change detection or a truth judgment.

The monitor currently evaluates the saved query and its stored `result_type` filter using the existing corpus search service.

## Durable worker and concurrency safety

`newsintel.workers.workspace_monitor` is a dedicated worker process. Due monitors are leased with PostgreSQL row locking (`FOR UPDATE SKIP LOCKED`) and carry a monotonically increasing `lease_version` fencing token.

A worker can commit a run only while its lease owner and lease version remain current. Disabling or superseding a lease therefore prevents a stale worker from committing monitoring state.

Configuration:

- `NEWSINTEL_WORKSPACE_MONITOR_BATCH_SIZE`
- `NEWSINTEL_WORKSPACE_MONITOR_LEASE_SECONDS`
- `NEWSINTEL_WORKSPACE_MONITOR_IDLE_SECONDS`

The Windows one-command platform launcher now starts and stops the monitor worker and includes its logs in the combined log view.

## Monitor run history

Analysts can inspect recent evaluations for each monitored saved search. The UI shows:

- completed/failed status;
- run time;
- result-window size;
- number of results newly entering the window;
- failure text when a run failed.

This makes monitoring operationally observable instead of a silent scheduled job.

## Monitoring alerts are independent of watchlists

A correctness issue found during this release was fixed: generated scheduled-search alerts were previously vulnerable to being skipped if the analyst had no watchlists or no watchlist items. The alert aggregation path now treats persisted monitor alerts and watchlist-derived alerts as independent sources before acknowledgement/deduplication.

## Shared investigation UX

The Investigation UI now shows:

- owner/editor/reader access badge;
- investigation owner;
- collaborators and their roles;
- owner-only collaborator controls;
- view-only messaging for readers;
- activity history;
- note authorship;
- saved-search ownership;
- monitoring controls only for the analyst who owns the saved search.

The global search "Save search" dialog only offers active investigations where the current user has owner/editor access. Reader-only investigations cannot be selected and then fail later at the API boundary.

## Database schema

New Alembic head:

`0025_collaboration_monitoring`

New tables:

- `investigation_members`
- `investigation_activity`
- `workspace_monitors`
- `workspace_monitor_runs`
- `workspace_generated_alerts`

Production health/doctor checks now validate the persistent analyst-workspace and collaboration/monitoring tables and critical indexes in addition to checking the Alembic revision marker.

## API additions

Key endpoints include:

- `GET /api/v1/investigations/{id}/members`
- `POST /api/v1/investigations/{id}/members`
- `PATCH /api/v1/investigations/{id}/members/{member_id}`
- `DELETE /api/v1/investigations/{id}/members/{member_id}`
- `GET /api/v1/investigations/{id}/activity`
- `GET /api/v1/saved-searches/{id}/monitor`
- `PUT /api/v1/saved-searches/{id}/monitor`
- `GET /api/v1/saved-searches/{id}/monitor/runs`

## Validation performed in this environment

- full Python source compilation: **PASS**;
- focused v1.16 collaboration/monitoring + v1.15 workspace contracts: **19 passed**;
- broader dependency-light regression selection across UI, events, claims, evidence, lineage, corrections, versioning and propagation: **90 passed**;
- rendered JavaScript syntax checks for modified analyst surfaces using Node: **PASS**;
- Alembic single head: `0025_collaboration_monitoring`;
- offline SQL generation from `0024_analyst_workspace` to `0025_collaboration_monitoring`: **PASS**;
- FastAPI/OpenAPI wiring: version `1.16.0`, collaboration/monitor routes registered.

The complete environment-dependent test suite is not claimed as passing in this sandbox because the frozen runtime dependency `structlog` is not installed here. Temporary in-memory stubs were used only for selected import/render validation and were never added to the release tree.

## Deliberately deferred

Version 1.16 does not attempt a search-engine rewrite. The next high-value release should upgrade the current correctness-first corpus search to indexed PostgreSQL full-text search, stable ranking and cursor pagination before optional semantic reranking.
