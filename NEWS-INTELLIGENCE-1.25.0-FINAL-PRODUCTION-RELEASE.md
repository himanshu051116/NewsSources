# News Intelligence 1.25.0 — Final Production-Deployable Release

## Scope
This release finalizes the original News Intelligence product as a continuously running, deployable application: live source discovery, fetching, extraction/versioning, event intelligence, automatic historical enrichment, grounded event explanations, investigation workflows and operations tooling.

## Production assets
- hardened Python application Docker image;
- Docker Compose production topology for API and all continuous workers;
- PostgreSQL/PostGIS, Qdrant, MinIO and optional isolated browser renderer;
- Caddy TLS reverse proxy configuration;
- automatic migration service;
- CI workflow with PostGIS integration environment and Docker build;
- production environment template with fail-closed application settings;
- backup/restore and smoke-check scripts;
- production runbook and measurable pilot acceptance gates.

## Final schema
`0033_grounded_news_explainer`

## What "final" means
The codebase is deployable and feature-complete for the intended product workflow. It is not honest to claim that an arbitrary installation is production-proven until its own 7-day approved-source trial, restore drill, security review and SLO measurements pass. Those acceptance gates are documented in `PRODUCTION-RUNBOOK.md`.


## Operational acceptance automation
The final package includes `newsintel-acceptance` and `scripts/production-acceptance.sh`. These record and evaluate the 24-hour, 72-hour and 7-day acceptance stages against API-readiness availability, candidate-level terminal processing success, publication-to-discovery p95, historical completion within 10 minutes, grounded-briefing coverage within 12 minutes, and stale-lease age. Error sampling intervals count against availability, and trials with insufficient traffic are BLOCKED instead of receiving a misleading PASS. Automated SLO checks do not replace the documented human review of extraction fidelity, event grouping, historical relevance, evidence grounding and publisher rights.
