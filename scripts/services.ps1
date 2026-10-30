param(
    [ValidateSet("init", "up", "down", "restart", "status", "logs", "migrate", "doctor")]
    [string] $Command = "status"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$workspace = Split-Path -Parent $PSScriptRoot
$docker = $null
$standardDocker = Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\docker.exe"

if (Test-Path $standardDocker) {
    $docker = $standardDocker
} else {
    $dockerCommand = Get-Command docker -CommandType Application -ErrorAction SilentlyContinue
    if ($dockerCommand) {
        $docker = $dockerCommand.Source
    }
}

if (-not $docker) {
    throw "Docker CLI was not found. Install/start Docker Desktop, then reopen PowerShell."
}

$dockerDir = Split-Path -Parent $docker
if ($dockerDir -and ($env:Path -notlike "*$dockerDir*")) {
    $env:Path = "$dockerDir;$env:Path"
}

$python = Join-Path $workspace ".venv\Scripts\python.exe"
$alembic = Join-Path $workspace ".venv\Scripts\alembic.exe"

function Assert-LastCommandSucceeded {
    param([string] $Label)
    if ($LASTEXITCODE -ne 0) { throw "Command failed: $Label" }
}

function Invoke-Compose {
    param([string[]] $ComposeArguments)
    & $docker compose @ComposeArguments
    Assert-LastCommandSucceeded "docker compose $($ComposeArguments -join ' ')"
}

function Get-NewsEnvValue {
    param([Parameter(Mandatory)][string] $Key)
    $processValue = [Environment]::GetEnvironmentVariable($Key, "Process")
    if ($null -ne $processValue) { return $processValue }
    foreach ($name in @(".env.local", ".env")) {
        $path = Join-Path $workspace $name
        if (-not (Test-Path $path)) { continue }
        foreach ($line in Get-Content -Path $path -ErrorAction SilentlyContinue) {
            $trimmed = $line.Trim()
            if (-not $trimmed -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) { continue }
            $parts = $trimmed.Split("=", 2)
            if ($parts[0].Trim() -eq $Key) { return $parts[1].Trim().Trim('"').Trim("'") }
        }
    }
    return $null
}

function Test-NewsEnvTrue {
    param([Parameter(Mandatory)][string] $Key)
    $value = Get-NewsEnvValue -Key $Key
    return $null -ne $value -and $value.ToLowerInvariant() -in @("1", "true", "yes", "on")
}

function Get-RequiredComposeServices {
    $services = [System.Collections.Generic.List[string]]::new()
    $services.Add("postgres")

    if (Test-NewsEnvTrue -Key "NEWSINTEL_SEMANTIC_SEARCH_ENABLED") {
        $services.Add("qdrant")
    }

    $artifactBackend = Get-NewsEnvValue -Key "NEWSINTEL_RAW_ARTIFACT_STORE_BACKEND"
    if ($artifactBackend -and $artifactBackend.ToLowerInvariant() -eq "s3") {
        $services.Add("minio")
    }

    return $services.ToArray()
}

function Assert-LocalConfigExists {
    if (-not (Test-Path (Join-Path $workspace ".env"))) {
        throw "Missing .env. Run scripts\bootstrap.ps1 first; it now creates .env automatically."
    }
}

function Invoke-Migrate {
    Assert-LocalConfigExists
    if (-not (Test-Path $alembic)) { throw "Alembic was not found. Run scripts/bootstrap.ps1 first." }
    & $alembic -c backend\alembic.ini upgrade head
    Assert-LastCommandSucceeded "alembic upgrade head"
}

function Invoke-Doctor {
    Assert-LocalConfigExists
    if (-not (Test-Path $python)) { throw "Python venv was not found. Run scripts/bootstrap.ps1 first." }
    & $python -m newsintel.doctor
    Assert-LastCommandSucceeded "python -m newsintel.doctor"
}

Push-Location $workspace
try {
    switch ($Command) {
        "init" {
            Assert-LocalConfigExists
            $required = Get-RequiredComposeServices
            Write-Host "Starting required local containers: $($required -join ', ')"
            Invoke-Compose (@("up", "--detach", "--wait", "--wait-timeout", "90") + $required)
            Invoke-Migrate
            Invoke-Doctor
            Invoke-Compose @("ps")
        }
        "up" {
            Assert-LocalConfigExists
            $required = Get-RequiredComposeServices
            Invoke-Compose (@("up", "--detach") + $required)
        }
        "down" { Invoke-Compose @("down") }
        "restart" {
            Assert-LocalConfigExists
            $required = Get-RequiredComposeServices
            Invoke-Compose (@("restart") + $required)
        }
        "status" { Invoke-Compose @("ps") }
        "logs" { Invoke-Compose @("logs", "--follow", "--tail", "100") }
        "migrate" { Invoke-Migrate }
        "doctor" { Invoke-Doctor }
    }
} finally {
    Pop-Location
}
