Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$workspace = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $workspace ".venv"
$envExample = Join-Path $workspace ".env.example"
$envFile = Join-Path $workspace ".env"
$envLocal = Join-Path $workspace ".env.local"

function Ensure-LocalEnvironmentFiles {
    if (-not (Test-Path $envFile)) {
        if (-not (Test-Path $envExample)) {
            throw "Missing .env.example; cannot create local configuration."
        }
        Copy-Item -Path $envExample -Destination $envFile
        Write-Host "Created .env from .env.example"
    } else {
        Write-Host ".env already exists; leaving it unchanged."
    }

    if (-not (Test-Path $envLocal)) {
        $secret = ([guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N"))
        @"
# Generated automatically for local-only development.
# .env.local overrides .env.
NEWSINTEL_DEV_AUTH_BYPASS_ENABLED=true
NEWSINTEL_AUTH_SESSION_SECRET=$secret
"@ | Set-Content -Path $envLocal -Encoding UTF8
        Write-Host "Created .env.local with local developer authentication enabled."
    } else {
        Write-Host ".env.local already exists; leaving it unchanged."
    }
}

function Assert-SystemPythonSupported {
    $pythonCommand = Get-Command python -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $pythonCommand) {
        throw "Python was not found. Install Python 3.12+ (64-bit), reopen PowerShell, then rerun scripts\bootstrap.ps1."
    }
    $versionText = & $pythonCommand.Source -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"
    if ($LASTEXITCODE -ne 0) {
        throw "Python was found but could not be executed."
    }
    $version = [version]$versionText.Trim()
    if ($version -lt [version]"3.12.0" -or $version -ge [version]"3.15.0") {
        throw "Unsupported Python $version. Install Python 3.12, 3.13, or 3.14."
    }
    Write-Host "Python $version detected."
}

Ensure-LocalEnvironmentFiles

$uv = Get-Command uv -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if ($uv) {
    Push-Location $workspace
    try {
        Write-Host "Using uv to create/sync the virtual environment..."
        & $uv.Source sync --extra dev --extra extractors --frozen
        if ($LASTEXITCODE -ne 0) {
            throw "uv sync failed. Check your internet connection and Python availability."
        }
    }
    finally {
        Pop-Location
    }
}
else {
    Assert-SystemPythonSupported
    if (-not (Test-Path $venv)) {
        python -m venv $venv
        if ($LASTEXITCODE -ne 0) {
            throw "python -m venv failed."
        }
    }

    $python = Join-Path $venv "Scripts\python.exe"
    & $python -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        throw "pip upgrade failed. Check your internet connection."
    }
    & $python -m pip install -e "${workspace}[dev,extractors]"
    if ($LASTEXITCODE -ne 0) {
        throw "Project dependency installation failed."
    }
}

$venvPython = Join-Path $venv "Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "Virtual-environment Python was not created at $venvPython"
}

Write-Host ""
Write-Host "Local development environment is ready."
Write-Host "Next command: .\scripts\services.ps1 init"
