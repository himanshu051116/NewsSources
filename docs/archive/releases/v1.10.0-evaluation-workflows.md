# News Intelligence v1.10.0 — Accuracy Validation Program

This release converts the blind-adjudicated benchmark into a repeatable release-validation program.

## Added
- Content-addressed SHA-256 corpus fingerprint for finalized benchmark cases.
- 95% Wilson confidence intervals for decided-case accuracy.
- Slice-level validation for language, topic and source.
- `insufficient_sample` state so tiny slices are not falsely passed or failed.
- Active-sampling priorities that target underrepresented, uncertain or failing slices.
- `GET /api/v1/verification-benchmark/{benchmark_set}/validation-report`.
- Accuracy workspace panel for corpus version, uncertainty and next annotation priorities.

## Quality methodology
The report preserves separate metrics for decision coverage, decided-case accuracy and unsafe high-confidence errors. A pass applies only to the exact fingerprinted adjudicated corpus. It is not a universal factual-accuracy claim.

## Database
No new migration. The schema head remains `0023_blind_adjudication_diagnostics`.

## Validation
- Full repository suite: 301/301 passing with external validation-only `structlog`/`asyncpg` compatibility shims.
- Native-runnable subset in this sandbox: 266/266 passing.
- New validation-program/release tests: 5/5 passing.
- OpenAPI: 1.10.0, 108 paths.
- Alembic: one head at 0023.
- Full offline migration SQL: 1552 lines.
- Accuracy page JavaScript: `node --check` pass.
- `uv lock --check --offline`: pass.
