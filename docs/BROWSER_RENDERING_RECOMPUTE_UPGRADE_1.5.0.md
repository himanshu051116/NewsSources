# Browser Recovery & Dependency Recompute 1.5.0

**Release:** 1.5.0  
**Alembic head:** `0022_browser_recompute`

Version 1.5.0 addresses two reliability gaps that remained after adaptive extraction and historical enrichment: genuinely JavaScript-only news pages that contain no useful server-delivered article body, and derived historical contexts that can become stale after upstream corrections or other dependency changes.

## Optional isolated browser recovery

Normal SSRF-aware HTTP extraction, structured metadata, hydration-state recovery and Trafilatura remain the primary extraction path. Browser rendering is a last-resort fallback and is disabled by default.

When explicitly enabled globally and for a publisher extraction profile, the article worker can send a weak extraction to a localhost browser-renderer sidecar. The sidecar:

- requires a strong shared token;
- accepts only public HTTP/HTTPS destinations;
- restricts navigation and subresources to the publisher domain plus explicitly configured asset domains;
- blocks private-network destinations on every request;
- blocks downloads, service workers, WebSockets and non-HTTP schemes;
- aborts images, media and fonts to bound resource use;
- applies navigation, HTML-size, process, memory and concurrency limits;
- returns rendered HTML and request-count/hash provenance to the article worker.

The rendered result replaces the ordinary result only when it is materially better. Renderer failure never converts an otherwise usable extraction into a failed article.

### Local opt-in

Generate a strong token in `.env.local`, for example in PowerShell:

```powershell
$token = ([guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N"))
Add-Content .env.local "NEWSINTEL_BROWSER_RENDERER_ENABLED=true"
Add-Content .env.local "NEWSINTEL_BROWSER_RENDERER_TOKEN=$token"
```

Then start the platform normally. `scripts/run-platform.ps1 start` starts the optional renderer profile when the global flag is enabled. You can also manage it directly:

```powershell
.\scripts\browser-renderer.ps1 up
.\scripts\browser-renderer.ps1 status
.\scripts\browser-renderer.ps1 logs
```

A publisher must additionally opt in through its extraction profile (`browser_render_enabled=true`). Extra CDN/static asset hosts must be listed explicitly in `browser_allowed_domains`.

The browser Docker image is separate from the main Python dependency set. This keeps Playwright/Chromium out of API and worker processes that do not need it.

## Generalized dependency invalidation

Historical context is derived data. Version 1.5.0 records which article versions, claims, events and historical records each historical context depends on.

When an upstream source is invalidated, such as by a correction or retraction, the platform:

1. marks dependent derived artifacts stale;
2. increments a generation counter;
3. writes idempotent generation-scoped recompute jobs;
4. exposes stale/recompute state immediately to Article Intelligence;
5. requeues historical enrichment using the original historical cutoff;
6. marks the derived state fresh only after recomputation succeeds.

The recompute worker supports expired-lease recovery and bounded retry/backoff. Historical verdicts and prior contexts are not silently rewritten; recomputation refreshes the current derived context while immutable article/verification history remains available.

## Persistence

Migration `0022_browser_recompute` adds browser controls to publisher extraction profiles and creates:

- `derived_artifact_dependencies`;
- `derived_artifact_states`;
- `derived_recompute_jobs`.

The migration is additive and upgrades an existing 1.4.0 database in place.

## Deliberate limits

This renderer is not a paywall bypass and does not authorize access to subscriber-only content. Cross-origin assets are denied unless explicitly allow-listed. It is optional because Chromium adds substantial attack surface and resource cost; ordinary extraction remains the preferred path.

The generalized dependency engine currently has a concrete recompute handler for historical contexts. The artifact/source vocabulary is intentionally generic so later event/entity/evidence projections can register dependencies without inventing another one-off reconciliation system.
