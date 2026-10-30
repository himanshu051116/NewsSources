# News Intelligence 1.12.0 — Search, Event Dossier & Command Center

This pass continues the v1.11 frontend-correctness work and moves the application toward an event/claim/evidence-centered analyst workspace without replacing the FastAPI backend.

## Implemented

### Corpus-wide Intelligence Search
- Added `/search` UI and `/api/v1/search` API.
- Searches stored event titles and stored article title/body content, not only the currently loaded browser feed.
- Users with `claims:view` also receive matching atomic claims.
- Result types remain explicit: event, article, claim.
- Search navigation is permission-safe and available to content viewers.
- Query wildcard characters `%`, `_`, and `\\` are escaped before `ILIKE` matching to avoid accidental match-all scans.
- Search snippets center the matching phrase where possible.

### Event Dossier aggregate
- Added analyst endpoint `/api/v1/events/{event_id}/dossier`.
- Counts claims only from the latest version of each linked article so prior article revisions do not inflate current claim totals.
- Aggregates latest verification states, independent evidence links, primary evidence links, and contradiction/dispute links.
- Adds publisher breakdown and claim-level evidence counts.
- Keeps evidence assessments distinct from universal factual truth.

### Event Dossier UI
- Reworked `/events/{event_id}/intelligence` into a richer dossier.
- Added claim verification posture, source diversity, current claims, evidence counts, timeline semantics, material timeline, event signals, and linked reporting.
- Viewers without `claims:view` get a safe fallback instead of a broken claim view.
- Analysts can filter current claims by verification state and jump back to Article Intelligence for detailed evidence inspection.

### Command Center
- Replaced the static `/app` tile-only landing page with a live command center.
- Shows developing events, recent reports, material-update signals, and conflict/revision signals.
- Adds an attention queue for conflict/revision, material-update, and extraction-warning conditions.
- Signals are explicitly described as review indicators, not factual verdicts.
- Keeps direct workspace shortcuts for Search, Events, News, Research and Sources as permissions allow.

### Navigation
- Added Search to the permission-derived primary/mobile navigation introduced in v1.11.

## Validation performed in this environment
- Complete Python source compilation: PASS.
- Dependency-light regression suite: 47 tests PASS.
- New v1.12 UI/search contract tests included.
- Full application collection is still not independently executable in this sandbox because the frozen runtime dependency `structlog` is unavailable here. This is an environment limitation rather than a demonstrated application regression.

## Deliberate limitations / next work

The v1.12 search API is a correctness-first database search foundation using escaped `ILIKE`. It is not yet the final high-scale retrieval engine. The next search phase should add indexed PostgreSQL full-text search, ranking, cursor pagination, entity search and optional semantic reranking.

The dossier currently aggregates stored evidence relationships and publisher coverage. Source-lineage / syndication independence remains a higher-level intelligence problem and should not be inferred from raw publisher counts.

Recommended next development sequence:
1. PostgreSQL indexed full-text search + cursor pagination.
2. Source-lineage / syndication identity and independence UI.
3. Claim Investigation workspace with evidence orchestration and conflict-resolution actions.
4. Article-version/correction evolution UI.
5. Saved investigations, watchlists, notes and alerts.
