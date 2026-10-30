$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root
$ExpectedHead = "0033_grounded_news_explainer"
$env:PYTHONPATH = "backend/src"

Write-Host "[1/7] Lockfile consistency"
uv lock --check --offline
Write-Host "[2/7] Python compilation"
python -m compileall -q backend/src backend/tests backend/migrations
Write-Host "[3/7] Unit/integration tests"
pytest -q
Write-Host "[4/7] Alembic single-head check"
$Head = ((& alembic -c backend/alembic.ini heads) -split "\s+")[0]
if ($Head -ne $ExpectedHead) { throw "Expected Alembic head $ExpectedHead but found $Head" }
Write-Host "[5/7] Offline migration SQL"
alembic -c backend/alembic.ini upgrade head --sql | Out-File -Encoding utf8 "$env:TEMP\newsintel-upgrade.sql"
Write-Host "[6/7] Release-tree integrity"
python scripts/release-integrity.py
Write-Host "[7/7] Lint/type checks"
$StrictValidation = $env:NEWSINTEL_STRICT_VALIDATION -eq "1"
python -c "import ruff" 2>$null
if ($LASTEXITCODE -eq 0) { python -m ruff check backend/src backend/tests } elseif ($StrictValidation) { throw "ruff is required in strict release validation" } else { Write-Warning "ruff is not installed" }
$Mypy = Get-Command mypy -ErrorAction SilentlyContinue
if ($Mypy) { mypy backend/src/newsintel } elseif ($StrictValidation) { throw "mypy is required in strict release validation" } else { Write-Warning "mypy is not installed" }
Write-Host "Release validation completed."
