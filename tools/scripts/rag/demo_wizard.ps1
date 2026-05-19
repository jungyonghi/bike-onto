# Timestamp: 2026-05-19 11:24:00
<#
.SYNOPSIS
Windows PowerShell wrapper for the OBYBK Ontology-Hybrid RAG interactive demo.

.DESCRIPTION
Runs general_rag_cli.py demo-wizard from the repository root.
The Python CLI pauses and asks for the domain artifact directory, output directory,
and which artifacts to generate unless -Yes is provided.
#>

[CmdletBinding()]
param(
    [string]$DomainDir = "sample_data\rag_visual_inspector",
    [string]$OutputDir = $(Join-Path $env:TEMP "obybk_cli_demo"),
    [string]$RunId = "demo_run",
    [int]$MaxQuestions = 120,
    [switch]$Yes,
    [switch]$Json,
    [switch]$DebugMode,
    [string]$Python = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
Set-Location $RepoRoot

function Resolve-PythonCommand {
    param([string]$RequestedPython)

    if ($RequestedPython) {
        return $RequestedPython
    }

    $Candidates = @(
        (Join-Path $RepoRoot ".venv\Scripts\python.exe"),
        (Join-Path $RepoRoot "venv\Scripts\python.exe"),
        "py",
        "python"
    )

    foreach ($Candidate in $Candidates) {
        if ($Candidate -match "\.exe$" -and (Test-Path $Candidate)) {
            return $Candidate
        }
        if ($Candidate -in @("py", "python")) {
            try {
                & $Candidate --version *> $null
                if ($LASTEXITCODE -eq 0) {
                    return $Candidate
                }
            }
            catch {
                continue
            }
        }
    }

    throw "Python executable was not found. Pass -Python C:\Path\To\python.exe or create .venv/venv."
}

$PythonCommand = Resolve-PythonCommand -RequestedPython $Python
$CliArgs = @(
    "tools\scripts\rag\general_rag_cli.py",
    "demo-wizard",
    "--domain-dir", $DomainDir,
    "--output-dir", $OutputDir,
    "--run-id", $RunId,
    "--max-questions", "$MaxQuestions"
)

if ($Yes) { $CliArgs += "--yes" }
if ($Json) { $CliArgs += "--json" }
if ($DebugMode) { $CliArgs += "--debug" }

Write-Host "OBYBK Ontology-Hybrid RAG PowerShell Demo" -ForegroundColor Cyan
Write-Host "Repository : $RepoRoot"
Write-Host "Python     : $PythonCommand"
Write-Host "Command    : general_rag_cli.py demo-wizard"
Write-Host ""

& $PythonCommand @CliArgs
exit $LASTEXITCODE
