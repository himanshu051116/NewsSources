# News Intelligence 1.6.1 — Local Setup Fix

This patch release fixes first-run/local Windows setup defects found in v1.6.0.

## Fixed

- Corrected Pydantic dotenv precedence so `.env.local` actually overrides `.env`.
- `bootstrap.ps1` now creates `.env` from `.env.example` when missing.
- `bootstrap.ps1` now creates `.env.local` with a generated 64-character local session secret and development-auth bypass when missing.
- Existing `.env` and `.env.local` files are never overwritten.
- Added clearer Python-version errors for the pip fallback path. Supported versions remain Python 3.12–3.14.
- Simplified default Docker startup to PostgreSQL only.
- Qdrant starts only when `NEWSINTEL_SEMANTIC_SEARCH_ENABLED=true`.
- MinIO starts only when `NEWSINTEL_RAW_ARTIFACT_STORE_BACKEND=s3`.
- `Start-News-Intelligence.vbs` now delegates to the smarter `app-start.ps1` launcher.
- First-run desktop launch can bootstrap the environment automatically if `.venv`/`.env` are missing.
- The launcher can start Docker Desktop if it is installed but not running.
- The desktop launcher now opens `/news`, not the source-operations page.
- Added `SETUP-WINDOWS.md` with a verified minimal Windows setup path.

## First run

Install Docker Desktop and Python 3.12, 3.13, or 3.14 (64-bit), then open PowerShell in the extracted project folder:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\bootstrap.ps1
.\scripts\run-platform.ps1 start
```

Open:

```text
http://127.0.0.1:8010/news
```

Or, after prerequisites are installed, double-click `Start-News-Intelligence.vbs`.

## Validation performed in the build environment

- `.env.local` override regression: PASS
- config unit tests: 8/8 PASS
- `uv lock --check --offline`: PASS
- Python compilation: PASS
- release-integrity scan: PASS

The build environment does not provide Windows PowerShell or Docker Desktop, so the PowerShell/Docker runtime path must still be exercised on the target Windows laptop.
