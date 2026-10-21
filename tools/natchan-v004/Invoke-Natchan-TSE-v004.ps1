param(
    [Parameter(Mandatory=$true)][string]$StudyRepoPath,
    [string]$Python = 'python',
    [string]$OutputDirectory = ''
)
$ErrorActionPreference = 'Stop'
$scriptRoot = $PSScriptRoot
if (-not $OutputDirectory) {
    $repoRoot = Split-Path (Split-Path $scriptRoot -Parent) -Parent
    $OutputDirectory = Join-Path $repoRoot ('library\ess-experiment\out\natchan-tse-v004-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
}
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Output directory already exists. Choose a new path.' }
New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
$evidence = Join-Path $OutputDirectory 'evidence'
$manifest = Join-Path $scriptRoot 'manifest-tse-v004.json'
& $Python (Join-Path $scriptRoot 'prepare_evidence.py') --repo $StudyRepoPath --manifest $manifest --destination $evidence
if ($LASTEXITCODE -ne 0) { throw 'Evidence export failed. Ensure the study repository contains the pinned commit.' }
$result = Join-Path $OutputDirectory 'analysis.json'
& $Python (Join-Path $scriptRoot 'analyze.py') --manifest $manifest --evidence-root $evidence --output $result
if ($LASTEXITCODE -ne 0) { throw 'Natchan analysis failed; outputs preserved.' }
& $Python (Join-Path $scriptRoot 'validate_parity.py') --report $result --output (Join-Path $OutputDirectory 'parity.json')
if ($LASTEXITCODE -ne 0) { throw 'Parity differs; inspect parity.json. Analysis outputs preserved.' }
Write-Host "NATCHAN_TSE_V004_COMPLETE $OutputDirectory"
