param(
    [Parameter(Mandatory=$true)][string]$StudyRepoPath,
    [string]$Python = 'python',
    [string]$OutputDirectory = ''
)
$ErrorActionPreference = 'Stop'
if (-not $OutputDirectory) {
    $repoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
    $OutputDirectory = Join-Path $repoRoot ('library\ess-experiment\out\natchan-coverage-v005-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
}
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Output directory exists. Choose a new directory.' }
New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
$evidence = Join-Path $OutputDirectory 'evidence'
& $Python (Join-Path $PSScriptRoot 'prepare_evidence_v005.py') --repo $StudyRepoPath --destination $evidence
if ($LASTEXITCODE -ne 0) { throw 'Pinned evidence export failed.' }
$result = Join-Path $OutputDirectory 'analysis.json'
& $Python (Join-Path $PSScriptRoot 'analyze_coverage.py') --evidence-root $evidence --output $result
if ($LASTEXITCODE -ne 0) { throw 'Coverage analysis failed; outputs preserved.' }
& $Python (Join-Path $PSScriptRoot 'validate_coverage.py') --report $result --output (Join-Path $OutputDirectory 'validation.json')
if ($LASTEXITCODE -ne 0) { throw 'Coverage validation differs; inspect validation.json.' }
Write-Host "NATCHAN_COVERAGE_V005_COMPLETE $OutputDirectory"
