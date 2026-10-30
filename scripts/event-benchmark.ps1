param(
    [string]$Input = "",
    [switch]$Json
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Python environment not found. Run .\scripts\bootstrap.ps1 first."
}

$argsList = @("-m", "newsintel.event_benchmark_audit")
if ($Input) { $argsList += @("--input", $Input) }
if ($Json) { $argsList += "--json" }

& $python @argsList
exit $LASTEXITCODE
