import os
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(os.name != "nt", reason="Windows service launcher")
def test_stale_service_pid_cannot_match_an_unrelated_or_reused_process(tmp_path: Path) -> None:
    launcher = Path(__file__).resolve().parents[3] / "scripts" / "run-platform.ps1"
    harness = tmp_path / "identity-test.ps1"
    harness.write_text(
        r'''
param([string] $Launcher, [string] $RunDirectory)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Launcher, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw "Launcher has PowerShell syntax errors." }
foreach ($name in @("Service-PidPath", "Get-NewsServicePid")) {
    $definition = $ast.Find({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name }, $true)
    . ([scriptblock]::Create($definition.Extent.Text))
}
$runDir = $RunDirectory
$currentProcess = Get-Process -Id $PID
$python = "C:\not-the-service\python.exe"
Set-Content -LiteralPath (Join-Path $runDir "api.pid") -Value $PID
if ($null -ne (Get-NewsServicePid -Name "api")) { throw "Unrelated PID accepted." }
if (Test-Path -LiteralPath (Join-Path $runDir "api.pid")) { throw "Stale PID not cleared." }

$python = $currentProcess.Path
Set-Content -LiteralPath (Join-Path $runDir "api.pid") -Value $PID
@{ startTimeTicks = 1 } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runDir "api.identity.json")
if ($null -ne (Get-NewsServicePid -Name "api")) { throw "Reused PID accepted." }

Set-Content -LiteralPath (Join-Path $runDir "api.pid") -Value $PID
@{ startTimeTicks = $currentProcess.StartTime.ToUniversalTime().Ticks } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runDir "api.identity.json")
if ((Get-NewsServicePid -Name "api") -ne $PID) { throw "Matching process rejected." }
Write-Output "Identity checks passed."
''',
        encoding="utf-8",
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(harness),
         "-Launcher", str(launcher), "-RunDirectory", str(tmp_path)],
        capture_output=True, text=True, timeout=30, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Identity checks passed." in result.stdout
