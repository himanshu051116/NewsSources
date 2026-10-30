param(
    [ValidateSet("up", "down", "status", "logs", "build")]
    [string] $Command = "status"
)

$ErrorActionPreference = "Stop"
$workspace = (Resolve-Path (Split-Path -Parent $PSScriptRoot)).Path
Push-Location $workspace

function Get-RendererEnvValue {
    param([Parameter(Mandatory)][string] $Key)
    foreach ($name in @(".env.local", ".env")) {
        if (-not (Test-Path $name)) { continue }
        foreach ($line in (Get-Content -Path $name -ErrorAction SilentlyContinue)) {
            $trimmed = $line.Trim()
            if (-not $trimmed -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) { continue }
            $parts = $trimmed.Split("=", 2)
            if ($parts[0].Trim() -eq $Key) { return $parts[1].Trim().Trim('"').Trim("'") }
        }
    }
    return $null
}

function Assert-RendererConfiguration {
    $token = Get-RendererEnvValue -Key "NEWSINTEL_BROWSER_RENDERER_TOKEN"
    if ($null -eq $token -or $token.Length -lt 32) {
        throw "NEWSINTEL_BROWSER_RENDERER_TOKEN must be set to at least 32 characters in .env.local or .env before starting the browser renderer."
    }
}

try {
    $envArgs = @()
    if (Test-Path ".env") { $envArgs += @("--env-file", ".env") }
    if (Test-Path ".env.local") { $envArgs += @("--env-file", ".env.local") }
    $prefix = @("compose") + $envArgs + @("--profile", "browser-renderer")
    switch ($Command) {
        "up" {
            Assert-RendererConfiguration
            & docker @prefix up -d --build browser-renderer
            if ($LASTEXITCODE -ne 0) { throw "browser-renderer startup failed" }
            Write-Host "Browser renderer started on http://127.0.0.1:8025"
        }
        "down" {
            & docker @prefix stop browser-renderer
            if ($LASTEXITCODE -ne 0) { throw "browser-renderer stop failed" }
        }
        "status" { & docker @prefix ps browser-renderer }
        "logs" { & docker @prefix logs --follow --tail 100 browser-renderer }
        "build" {
            Assert-RendererConfiguration
            & docker @prefix build browser-renderer
            if ($LASTEXITCODE -ne 0) { throw "browser-renderer build failed" }
        }
    }
}
finally {
    Pop-Location
}
