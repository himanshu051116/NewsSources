param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string[]]$Url,
    [switch]$Json,
    [switch]$Summary
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Python environment not found. Run .\scripts\bootstrap.ps1 first."
}

$argsList = @("-m", "newsintel.accuracy_audit")
foreach ($item in $Url) {
    $argsList += @("--url", $item)
}
if ($Json) { $argsList += "--json" }
if ($Summary) { $argsList += "--summary" }

& $python @argsList
exit $LASTEXITCODE
