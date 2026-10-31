# News Intelligence 1.25.0 — Windows local setup

## Prerequisites

Install **Docker Desktop** and **Python 3.12, 3.13, or 3.14 (64-bit)**. Reboot/reopen PowerShell after installation.

Verify:

```powershell
python --version
docker --version
docker compose version
```

## Recommended first run

Open PowerShell in the extracted project directory and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\bootstrap.ps1
.\scripts\run-platform.ps1 start
```

`bootstrap.ps1` creates `.env` and `.env.local` if missing, without overwriting existing settings. The local override enables a development-only authentication bypass and generates a session secret. It is intended for a private machine, **not** for internet-facing or production use.

The default local stack starts only PostgreSQL. Qdrant starts only when semantic history is enabled. MinIO starts only when S3 artifact storage is selected.

Open:

```text
http://127.0.0.1:8010/news
```

Source operations:

```text
http://127.0.0.1:8010/news-sources
```

## One-click startup after prerequisites

After Docker Desktop and Python are installed, double-click `Start-News-Intelligence.vbs`. On a fresh checkout it now runs the bootstrap automatically when `.venv`/`.env` are missing, starts Docker Desktop if necessary, starts the application, and opens `/news`.

## Diagnostics

```powershell
.\scripts\services.ps1 doctor
.\scripts\run-platform.ps1 status
Get-Content .run\logs\api.err.log -Tail 100
Get-Content .run\logs\articles.err.log -Tail 100
Get-Content .run\logs\poller.err.log -Tail 100
Get-Content .run\logs\workspace-monitor.err.log -Tail 100
```

Database should report revision:

```text
0034_article_revision_history
```

Check service readiness with `Invoke-WebRequest http://127.0.0.1:8010/api/v1/health/ready`. If the reader has no articles, review the publisher configuration and polling logs; installation does not seed a real news archive automatically.

The 1.20 migration adds concurrent English-morphology FTS indexes while preserving the language-neutral simple indexes used for Hindi and other scripts. The 1.21 migration adds auditable search-promotion policies, gate evaluations and human release-decision records. Production search remains lexical by default; semantic reranking is benchmark-only and requires the optional local Ollama/Qdrant semantic stack.

## Clean retry without deleting your database

```powershell
.\scripts\run-platform.ps1 stop
.\scripts\services.ps1 down
.\scripts\run-platform.ps1 start
```

Do not run `docker compose down -v` unless you intentionally want to delete local database/storage volumes.
