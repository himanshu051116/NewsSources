$ErrorActionPreference = "Stop"

$workspace = Split-Path -Parent $PSScriptRoot
$python = Join-Path $workspace ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "Run scripts/bootstrap.ps1 first."
}

function Invoke-CheckedPython {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]] $Arguments)

    & $python @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed: python $($Arguments -join ' ')"
    }
}

Push-Location $workspace
try {
    Invoke-CheckedPython -m compileall -q backend\src backend\tests
    Invoke-CheckedPython -m ruff check backend\src backend\tests
    Invoke-CheckedPython -m mypy backend\src\newsintel
    Invoke-CheckedPython -m pytest --cov=backend/src/newsintel --cov-branch --cov-report=term-missing --cov-fail-under=60
    Invoke-CheckedPython -m alembic -c backend\alembic.ini heads
}
finally {
    Pop-Location
}
