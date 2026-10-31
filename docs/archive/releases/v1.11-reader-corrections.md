# News Intelligence — proposed v1.11 UI Correctness & Event-Centric Pass

This patch intentionally keeps the v1.10 backend architecture intact while fixing frontend correctness issues and beginning the move from an article-first interface toward an event-first intelligence workspace.

## Implemented

### Permission-aware navigation
- Navigation is derived from the same role permission matrix used by the backend instead of hard-coded role names.
- Owner now receives all permitted sections.
- Source managers receive analyst/accuracy surfaces they are actually authorized to use.
- Viewers no longer receive analyst-only Research/Accuracy links.
- Mobile navigation no longer truncates the fifth/sixth item; it is horizontally scrollable and includes Home.

### Workspace design-system correction
- Shared `.tile` styling now lives in the authenticated `BASE_CSS` design system.
- Workspace cards are styled consistently rather than depending on public-page CSS.
- Workspace tiles are permission-aware and include the new Events entry point.

### News feed stability
- Background/manual refresh merges the latest page into the current in-browser working set instead of replacing progressively loaded older stories.
- Existing loaded research context is preserved during 30-second refreshes.
- Story cards include a direct Event action.

### Event directory
- Added `GET /api/v1/events` with title search, lifecycle filter, pagination, article counts and distinct publisher counts.
- Added `/events` event-centric dashboard.
- Events are ordered by latest material change.
- Added event metrics and direct dossier links.

### Event dossier upgrade
- Event Intelligence now shows lifecycle, linked-report count, distinct publishers, material-update count and possible conflict/revision signals.
- Analyst users receive the existing detailed event timeline.
- Viewer users receive a safe fallback chronology based on linked article observations.
- Timeline semantics are explicitly explained so chronology is not confused with verification.

### Accessibility
- Shared tab initializer now adds `aria-controls`, `role=tabpanel`, `aria-labelledby`, roving tabindex, Arrow Left/Right and Home/End keyboard navigation.
- Applied to Article Intelligence and Historical Research tabs.

### Source UI wording
- The previous misleading `Edit` action is renamed `Reconfigure`.
- UI now explicitly states that stored endpoints are not edited in place yet.

### Defensive article UI
- Article Intelligence no longer creates a broken event URL when an event link is absent.

## Validation performed in the current sandbox

- `python -m compileall -q backend/src` — PASS.
- 43 dependency-light tests — PASS, covering event matching/assignment, claim extraction, evidence stance, historical enrichment, circular sourcing, conflict resolution, temporal reasoning, extraction fidelity and the new UI navigation behavior.
- Broader dashboard test collection is still blocked in this sandbox because `structlog` and some locked project dependencies are not installed. This is an environment limitation rather than a demonstrated application regression.

## Deliberately not claimed as complete

This patch does **not** make the frontend production-perfect. The highest-value remaining work is:

1. PostgreSQL full-text/global search with cursor pagination.
2. Event dossier aggregate API (claims, evidence, corrections, lineage, source diversity) to avoid N+1 browser requests.
3. Claim investigation workspace with evidence passages, independence and reasoning trace.
4. Correction/version-diff UI and claim-evolution timeline.
5. Source ownership/syndication lineage visualization.
6. Saved investigations, notes, watchlists and alerts.
7. Replace native `prompt()`/`confirm()` admin flows with accessible dialogs.
8. True publisher editing rather than re-discovery/re-add semantics.
9. Event/article keyset pagination for large continuously changing corpora.
10. Event-driven realtime delivery instead of bounded database polling SSE.

The next recommended milestone is an **Event Dossier Aggregate + Global Search** release, not cosmetic redesign.
