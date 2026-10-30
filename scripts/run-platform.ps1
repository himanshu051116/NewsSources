param(
    [ValidateSet("start", "stop", "status", "restart", "logs")]
    [string] $Command = "start"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------

$workspace = (Resolve-Path (Split-Path -Parent $PSScriptRoot)).Path
$python = Join-Path $workspace ".venv\Scripts\python.exe"
$runDir = Join-Path $workspace ".run"
$logDir = Join-Path $runDir "logs"
$servicesScript = Join-Path $workspace "scripts\services.ps1"
$browserRendererScript = Join-Path $workspace "scripts\browser-renderer.ps1"

# Allow the API, poller and article worker to import the newsintel package.
$env:PYTHONPATH = Join-Path $workspace "backend\src"

# Write Python output to log files immediately instead of buffering it.
$env:PYTHONUNBUFFERED = "1"

if (-not (Test-Path $python)) {
    throw "Python virtual environment was not found at: $python`nRun scripts\bootstrap.ps1 first."
}

if (-not (Test-Path $servicesScript)) {
    throw "Service-management script was not found at: $servicesScript"
}

# ---------------------------------------------------------------------------
# Directory helpers
# ---------------------------------------------------------------------------

function Ensure-RunDirs {
    New-Item -ItemType Directory -Force -Path $runDir | Out-Null
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
}

function Get-NewsEnvValue {
    param(
        [Parameter(Mandatory)]
        [string] $Key
    )

    $processValue = [Environment]::GetEnvironmentVariable($Key, "Process")
    if ($null -ne $processValue) { return $processValue }
    # Match Settings: process environment, then .env.local, then .env.
    foreach ($name in @(".env.local", ".env")) {
        $path = Join-Path $workspace $name
        if (-not (Test-Path $path)) { continue }
        $lines = Get-Content -Path $path -ErrorAction SilentlyContinue
        foreach ($line in $lines) {
            $trimmed = $line.Trim()
            if (-not $trimmed -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) { continue }
            $parts = $trimmed.Split("=", 2)
            if ($parts[0].Trim() -eq $Key) {
                return $parts[1].Trim().Trim('"').Trim("'")
            }
        }
    }
    return $null
}

function Test-NewsEnvTrue {
    param([Parameter(Mandatory)][string] $Key)
    $value = Get-NewsEnvValue -Key $Key
    return $null -ne $value -and $value.ToLowerInvariant() -in @("1", "true", "yes", "on")
}

function Service-PidPath {
    param(
        [Parameter(Mandatory)]
        [string] $Name
    )

    return Join-Path $runDir "$Name.pid"
}

function Get-NewsServicePid {
    param(
        [Parameter(Mandatory)]
        [string] $Name
    )

    $pidPath = Service-PidPath -Name $Name

    if (-not (Test-Path $pidPath)) {
        return $null
    }

    $rawPid = (Get-Content -Path $pidPath -Raw).Trim()
    $pidValue = 0

    if (-not [int]::TryParse($rawPid, [ref] $pidValue)) {
        Write-Warning "${Name}: invalid PID file detected. Removing it."
        Remove-Item -Path $pidPath -Force -ErrorAction SilentlyContinue
        return $null
    }

    $managedProcess = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
    $identityPath = Join-Path $runDir "$Name.identity.json"
    if ($null -eq $managedProcess) { return $pidValue }

    # Windows reuses PIDs. Never treat an unrelated process as one of our
    # services, and never terminate it when an old PID file survives a reboot.
    if (-not $managedProcess.Path -or $managedProcess.Path -ne $python) {
        Write-Warning "${Name}: PID $pidValue belongs to another application; discarding stale tracking."
        Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $identityPath -Force -ErrorAction SilentlyContinue
        return $null
    }
    if (Test-Path -LiteralPath $identityPath) {
        try {
            $identity = Get-Content -LiteralPath $identityPath -Raw | ConvertFrom-Json
            if ([long]$identity.startTimeTicks -ne $managedProcess.StartTime.ToUniversalTime().Ticks) {
                throw "Process creation time does not match."
            }
        } catch {
            Write-Warning "${Name}: process identity no longer matches; discarding stale tracking."
            Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
            Remove-Item -LiteralPath $identityPath -Force -ErrorAction SilentlyContinue
            return $null
        }
    }
    return $pidValue
}

# ---------------------------------------------------------------------------
# Start service
# ---------------------------------------------------------------------------

function Start-NewsService {
    param(
        [Parameter(Mandatory)]
        [string] $Name,

        [Parameter(Mandatory)]
        [string[]] $Arguments
    )

    Ensure-RunDirs

    $pidPath = Service-PidPath -Name $Name
    $existingPid = Get-NewsServicePid -Name $Name

    if ($null -ne $existingPid) {
        $existingProcess = Get-Process `
            -Id $existingPid `
            -ErrorAction SilentlyContinue

        if ($null -ne $existingProcess) {
            Write-Host "${Name}: already running with PID $existingPid"
            return
        }

        Write-Host "${Name}: removing stale PID file."
        Remove-Item -Path $pidPath -Force -ErrorAction SilentlyContinue
    }

    $stdout = Join-Path $logDir "$Name.out.log"
    $stderr = Join-Path $logDir "$Name.err.log"

    # Start with fresh logs for this run.
    Remove-Item -Path $stdout -Force -ErrorAction SilentlyContinue
    Remove-Item -Path $stderr -Force -ErrorAction SilentlyContinue

    Write-Host "Starting ${Name}..."

    $process = Start-Process `
        -FilePath $python `
        -ArgumentList $Arguments `
        -WorkingDirectory $workspace `
        -RedirectStandardOutput $stdout `
        -RedirectStandardError $stderr `
        -WindowStyle Hidden `
        -PassThru

    # Give Python a moment to fail immediately if imports or configuration
    # are invalid.
    Start-Sleep -Milliseconds 800

    $process.Refresh()

    if ($process.HasExited) {
        $errorOutput = ""

        if (Test-Path $stderr) {
            $errorOutput = (
                Get-Content -Path $stderr -Tail 40 -ErrorAction SilentlyContinue
            ) -join [Environment]::NewLine
        }

        throw @"
${Name} stopped immediately with exit code $($process.ExitCode).

Error log:
$errorOutput

Full log:
$stderr
"@
    }

    Set-Content `
        -Path $pidPath `
        -Value $process.Id `
        -Encoding ASCII

    @{ startTimeTicks = $process.StartTime.ToUniversalTime().Ticks } |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runDir "$Name.identity.json") -Encoding ASCII

    Write-Host "${Name}: started with PID $($process.Id)"
    Write-Host "${Name}: standard output log: $stdout"
    Write-Host "${Name}: error log: $stderr"
}

# ---------------------------------------------------------------------------
# Stop service
# ---------------------------------------------------------------------------

function Stop-NewsService {
    param(
        [Parameter(Mandatory)]
        [string] $Name
    )

    $pidPath = Service-PidPath -Name $Name
    $pidValue = Get-NewsServicePid -Name $Name

    if ($null -eq $pidValue) {
        Write-Host "${Name}: stopped"
        return
    }

    $process = Get-Process `
        -Id $pidValue `
        -ErrorAction SilentlyContinue

    if ($null -ne $process) {
        Write-Host "Stopping ${Name} with PID $pidValue..."

        # A Windows venv Python launcher has a child Python process. Stopping
        # only its wrapper leaves the API/worker alive and breaks restart.
        & (Join-Path $env:SystemRoot "System32\taskkill.exe") /PID $pidValue /T /F | Out-Null
        if ($LASTEXITCODE -ne 0 -and (Get-Process -Id $pidValue -ErrorAction SilentlyContinue)) {
            throw "Could not stop ${Name} process tree."
        }

        try {
            Wait-Process `
                -Id $pidValue `
                -Timeout 10 `
                -ErrorAction SilentlyContinue
        }
        catch {
            Write-Warning "${Name}: process did not stop within the waiting period."
        }

        Write-Host "${Name}: stopped"
    }
    else {
        Write-Host "${Name}: stale PID $pidValue removed"
    }

    Remove-Item `
        -Path $pidPath `
        -Force `
        -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath (Join-Path $runDir "$Name.identity.json") -Force -ErrorAction SilentlyContinue
}

# ---------------------------------------------------------------------------
# Show service status
# ---------------------------------------------------------------------------

function Show-NewsService {
    param(
        [Parameter(Mandatory)]
        [string] $Name
    )

    $pidPath = Service-PidPath -Name $Name
    $pidValue = Get-NewsServicePid -Name $Name

    if ($null -eq $pidValue) {
        Write-Host "${Name}: stopped"
        return
    }

    $process = Get-Process `
        -Id $pidValue `
        -ErrorAction SilentlyContinue

    if ($null -ne $process) {
        Write-Host "${Name}: running PID $pidValue"
    }
    else {
        Write-Host "${Name}: stale PID $pidValue"

        Remove-Item `
            -Path $pidPath `
            -Force `
            -ErrorAction SilentlyContinue
    }
}

# ---------------------------------------------------------------------------
# Wait for FastAPI
# ---------------------------------------------------------------------------

function Wait-ForApi {
    param(
        [int] $TimeoutSeconds = 45
    )

    $healthUrl = "$apiBaseUrl/api/v1/health/ready"
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)

    Write-Host "Waiting for the News Intelligence API..."

    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest `
                -Uri $healthUrl `
                -UseBasicParsing `
                -TimeoutSec 3 `
                -ErrorAction Stop

            if ($response.StatusCode -eq 200) {
                Write-Host "API: ready"
                return
            }
        }
        catch {
            Start-Sleep -Seconds 1
        }
    }

    throw "The API did not become ready within $TimeoutSeconds seconds. Check: $logDir\api.err.log"
}

function Show-ApiStatus {
    $statusUrl = "$apiBaseUrl/api/v1/status"

    try {
        $response = Invoke-WebRequest `
            -Uri $statusUrl `
            -UseBasicParsing `
            -TimeoutSec 3 `
            -ErrorAction Stop

        $status = $response.Content | ConvertFrom-Json

        Write-Host ""
        Write-Host "Application status:"
        Write-Host "Database revision: $($status.database_revision)"
        Write-Host "Stored articles: $($status.article_count)"
        Write-Host "Last committed article: $($status.last_committed_article_at)"
        Write-Host "Queue depth: $($status.queue_depth)"
        Write-Host "Oldest pending candidate: $($status.oldest_pending_candidate_at)"
        Write-Host "Pending outbox events: $($status.pending_outbox_events)"
        Write-Host "Historical enrichment pending: $($status.historical_enrichment_pending)"
        Write-Host "Historical enrichment failed: $($status.historical_enrichment_failed)"
        Write-Host "Historical contexts: $($status.historical_context_count)"
        Write-Host "Derived recompute pending: $($status.derived_recompute_pending)"
        Write-Host "Derived stale artifacts: $($status.derived_stale_artifacts)"
    }
    catch {
        Write-Host ""
        Write-Host "Application status: API not reachable yet."
    }
}

function Show-ServiceLogs {
    Ensure-RunDirs

    Write-Host "Tailing service logs from: $logDir"
    Write-Host "Press Ctrl+C to stop tailing."

    $paths = @(
        (Join-Path $logDir "api.out.log"),
        (Join-Path $logDir "api.err.log"),
        (Join-Path $logDir "poller.out.log"),
        (Join-Path $logDir "poller.err.log"),
        (Join-Path $logDir "articles.out.log"),
        (Join-Path $logDir "articles.err.log"),
        (Join-Path $logDir "outbox.out.log"),
        (Join-Path $logDir "outbox.err.log"),
        (Join-Path $logDir "historical.out.log"),
        (Join-Path $logDir "historical.err.log"),
        (Join-Path $logDir "briefings.out.log"),
        (Join-Path $logDir "briefings.err.log"),
        (Join-Path $logDir "recompute.out.log"),
        (Join-Path $logDir "recompute.err.log"),
        (Join-Path $logDir "workspace-monitor.out.log"),
        (Join-Path $logDir "workspace-monitor.err.log")
    ) | Where-Object { Test-Path $_ }

    if (-not $paths) {
        Write-Host "No service logs found yet. Start the platform first."
        return
    }

    Get-Content -Path $paths -Tail 80 -Wait
}

# ---------------------------------------------------------------------------
# Main command
# ---------------------------------------------------------------------------

$apiHost = Get-NewsEnvValue -Key "NEWSINTEL_API_HOST"
if (-not $apiHost -or $apiHost -in @("0.0.0.0", "::")) { $apiHost = "127.0.0.1" }
if ($apiHost.Contains(":") -and -not $apiHost.StartsWith("[")) { $apiHost = "[$apiHost]" }
$apiPort = Get-NewsEnvValue -Key "NEWSINTEL_API_PORT"
if (-not $apiPort) { $apiPort = "8010" }
$apiBaseUrl = "http://${apiHost}:$apiPort"

Push-Location $workspace

try {
    switch ($Command) {
        "start" {
            Ensure-RunDirs

            Write-Host "Starting database and supporting containers..."
            & $servicesScript init

            if (Test-NewsEnvTrue -Key "NEWSINTEL_BROWSER_RENDERER_ENABLED") {
                if (-not (Test-Path $browserRendererScript)) {
                    throw "Browser renderer is enabled but its management script is missing: $browserRendererScript"
                }
                Write-Host "Browser renderer is enabled. Starting isolated renderer sidecar..."
                & $browserRendererScript up
            }

            try {
                Start-NewsService `
                    -Name "api" `
                    -Arguments @(
                        "-m",
                        "newsintel.main"
                    )

                # Give the API its startup window before CPU-heavy workers compete
                # for resources on the local machine.
                Wait-ForApi -TimeoutSeconds 120

                Start-NewsService `
                    -Name "poller" `
                    -Arguments @(
                        "-m",
                        "newsintel.workers.poller"
                    )

                Start-NewsService `
                    -Name "articles" `
                    -Arguments @(
                        "-m",
                        "newsintel.workers.articles"
                    )

                Start-NewsService `
                    -Name "outbox" `
                    -Arguments @(
                        "-m",
                        "newsintel.workers.outbox"
                    )

                Start-NewsService `
                    -Name "historical" `
                    -Arguments @(
                        "-m",
                        "newsintel.workers.historical_enrichment"
                    )

                Start-NewsService `
                    -Name "briefings" `
                    -Arguments @(
                        "-m",
                        "newsintel.workers.briefings"
                    )

                Start-NewsService `
                    -Name "recompute" `
                    -Arguments @(
                        "-m",
                        "newsintel.workers.recompute"
                    )

                Start-NewsService `
                    -Name "workspace-monitor" `
                    -Arguments @(
                        "-m",
                        "newsintel.workers.workspace_monitor"
                    )

                Wait-ForApi -TimeoutSeconds 45

                Write-Host ""
                Write-Host "News Intelligence Platform started successfully."
                Write-Host "News feed: $apiBaseUrl/news"
                Write-Host "Source operations: $apiBaseUrl/news-sources"
                Write-Host "API documentation: $apiBaseUrl/docs"
                Write-Host "Logs: $logDir"
            }
            catch {
                Write-Warning "Startup failed. Stopping partially started services."

                Stop-NewsService -Name "workspace-monitor"
                Stop-NewsService -Name "recompute"
                Stop-NewsService -Name "briefings"
                Stop-NewsService -Name "historical"
                Stop-NewsService -Name "outbox"
                Stop-NewsService -Name "articles"
                Stop-NewsService -Name "poller"
                Stop-NewsService -Name "api"

                throw
            }
        }

        "stop" {
            Stop-NewsService -Name "workspace-monitor"
            Stop-NewsService -Name "recompute"
            Stop-NewsService -Name "briefings"
            Stop-NewsService -Name "historical"
            Stop-NewsService -Name "outbox"
            Stop-NewsService -Name "articles"
            Stop-NewsService -Name "poller"
            Stop-NewsService -Name "api"

            Write-Host ""
            Write-Host "News Intelligence application services stopped."
            Write-Host "Stored publishers and articles were not deleted."
        }

        "restart" {
            & $PSCommandPath stop
            & $PSCommandPath start
        }

        "status" {
            Ensure-RunDirs

            Show-NewsService -Name "api"
            Show-NewsService -Name "poller"
            Show-NewsService -Name "articles"
            Show-NewsService -Name "outbox"
            Show-NewsService -Name "historical"
            Show-NewsService -Name "briefings"
            Show-NewsService -Name "recompute"
            Show-NewsService -Name "workspace-monitor"
            Show-ApiStatus

            Write-Host ""
            Write-Host "Container status:"
            & $servicesScript status
        }

        "logs" {
            Show-ServiceLogs
        }
    }
}
finally {
    Pop-Location
}
