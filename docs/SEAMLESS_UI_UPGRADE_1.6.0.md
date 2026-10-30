# Seamless Intelligence UI 1.6.0

**Release:** 1.6.0  
**Alembic head:** `0022_browser_recompute` (no schema migration required)

Version 1.6.0 is a UI/coherence release. It does not add a new intelligence scoring subsystem. It makes the capabilities already present in the backend usable as one product.

## Shared design system

The News, Article Intelligence, Event Intelligence, Historical Research, Sources, Workspace and Access screens now share one responsive visual system with common navigation, panels, typography, buttons, pills, loading skeletons, empty/error states, focus styles, dark-mode support and mobile navigation.

## News feed

`/news` now supports headline/status search, quick story-pattern filters, language filtering, sorting, progressive loading of older stories, human-readable extraction/history states and automatic refresh. Heuristic linkage/extraction values are no longer presented as prominent truth-like percentages.

The article API gained an additive `offset` query parameter to support progressive loading without changing existing callers.

## Article Intelligence

The workspace now uses progressive sections instead of one all-or-nothing request. Core article/history content is viewer-safe. Analyst-only claims and quality panels degrade gracefully when permission is absent instead of causing the whole page to fail.

The page includes:

- Overview / Claims / History / Evidence / Source tabs;
- explicit review/warning banners;
- expandable claim cards with evidence links;
- evidence-readiness labels and dimensions;
- strongest historical links and a chronological timeline;
- extracted source text and extraction method provenance;
- live SSE state updates;
- responsive mobile behavior.

## Event Intelligence

Normal users no longer have to open raw event JSON. `/events/{event_id}/intelligence` provides a human event page with lifecycle state and linked reporting timeline.

## Historical Research

The research UI now searches the internal full-text corpus and configured external providers together, exposes partial provider failures without erasing successful results, provides direct Article Intelligence links for internal matches, and keeps archive lookup in a separate tab. The route continues to use safe DOM construction for returned external content.

## Sources

`/news-sources` is now an operations-only screen. News cards were removed from the source-management page. It now emphasizes source health, discovery status, channel counts, fetch progress and source actions, while linking back to `/news` for reading.

## Access and workspace

Workspace and access-management surfaces use the same visual tokens as the intelligence UI. Public sign-in/status pages also inherit the same typography, controls, color system and responsive behavior.

## Accessibility and mobile

The shared shell adds a skip link, visible keyboard focus, `aria-live` status regions, responsive grids, mobile bottom navigation, large touch targets, system color-scheme support and consistent loading/error states.

## No database reset

There is no v1.6 migration. Existing v1.5 databases remain at `0022_browser_recompute` and can be used directly after updating the code/dependencies.
