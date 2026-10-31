# News Intelligence 1.25 — Final Validation Record

## Passed in this build environment
- Unit regression suite: **392/392 passed**.
- Python compilation for source, tests, migrations and scripts: **passed**.
- Alembic: exactly one head, `0033_grounded_news_explainer`.
- Full offline migration SQL generation through `0033`: **passed**.
- `uv lock --check --offline`: **passed**.
- FastAPI/OpenAPI generation: **passed**, application version `1.25.0`, **177 paths**.
- Grounded Event Briefing rendered JavaScript: `node --check` **passed**.
- Production Compose YAML structural parsing: **passed** (15 services).
- Focused live-pipeline/historical/final-release tests: **36 passed**.
- Permission regression after claim-level briefing hardening: **passed**.
- Production acceptance evaluator unit tests: **4 passed**.
- `newsintel-acceptance` CLI: synthetic 24-hour PASS report generation **passed**.
- `scripts/production-acceptance.sh`: shell syntax validation **passed**.

## Environment-blocked, not reported as passed
- Real FastAPI lifespan/PostgreSQL integration: sandbox lacks the locked `asyncpg` driver. One non-database integration test passes; the liveness integration test stops before app startup for this missing dependency.
- Docker image build / Docker Compose runtime startup: this sandbox does not provide the Docker CLI/daemon. CI and the production runbook contain the build/start commands for an environment with Docker.
- Ruff and mypy local validation: these executables/packages are not installed in this sandbox. The included CI workflow installs development dependencies and runs them.

## Not possible to truthfully certify from this static build session
- Real 24-hour / 72-hour / 7-day acceptance trials against an approved publisher set.
- Measured live discovery/extraction/historical-enrichment SLOs.
- OIDC/MFA behavior against the user's chosen identity provider.
- Disaster-recovery restore against the user's production infrastructure.
- Publisher-specific content retention/licensing approval.

These are explicit operational acceptance gates in `PRODUCTION-RUNBOOK.md`, not hidden unfinished coding tasks.
