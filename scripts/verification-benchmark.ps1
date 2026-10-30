param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("sample", "review-sheet", "review-import", "adjudicator-sheet", "agreement", "finalize", "export", "import")]
    [string]$Mode,
    [string]$Path = ".\verification-benchmark.jsonl",
    [string]$BenchmarkSet = "local-held-out-v2",
    [string]$Split = "test",
    [int]$Limit = 200,
    [int]$RecentPool = 5000,
    [string]$Seed = "20260824",
    [string]$ReviewerKey = "",
    [ValidateSet("reviewer", "adjudicator")]
    [string]$Role = "reviewer",
    [switch]$Json
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Python environment not found. Run .\scripts\bootstrap.ps1 first."
}

switch ($Mode) {
    "sample" {
        & $python -m newsintel.benchmark_dataset sample --benchmark-set $BenchmarkSet --split $Split --limit $Limit --recent-pool $RecentPool --seed $Seed
    }
    "review-sheet" {
        if (-not $ReviewerKey) { throw "-ReviewerKey is required for review-sheet." }
        & $python -m newsintel.benchmark_dataset review-sheet --benchmark-set $BenchmarkSet --reviewer-key $ReviewerKey --output $Path
    }
    "adjudicator-sheet" {
        if (-not $ReviewerKey) { throw "-ReviewerKey is required for adjudicator-sheet." }
        & $python -m newsintel.benchmark_dataset adjudicator-sheet --benchmark-set $BenchmarkSet --reviewer-key $ReviewerKey --output $Path
    }
    "review-import" {
        if (-not $ReviewerKey) { throw "-ReviewerKey is required for review-import." }
        & $python -m newsintel.benchmark_dataset review-import --benchmark-set $BenchmarkSet --reviewer-key $ReviewerKey --role $Role --input $Path
    }
    "agreement" {
        $args = @("-m", "newsintel.benchmark_dataset", "agreement", "--benchmark-set", $BenchmarkSet)
        if ($Json) { $args += "--json" }
        & $python @args
    }
    "finalize" {
        & $python -m newsintel.benchmark_dataset finalize --benchmark-set $BenchmarkSet
    }
    "export" {
        Write-Warning "Legacy export exposes the model prediction to reviewers. Prefer sample + review-sheet."
        & $python -m newsintel.benchmark_dataset export --output $Path --limit $Limit --recent-pool $RecentPool
    }
    "import" {
        & $python -m newsintel.benchmark_dataset import --input $Path --benchmark-set $BenchmarkSet --split $Split
    }
}
exit $LASTEXITCODE
