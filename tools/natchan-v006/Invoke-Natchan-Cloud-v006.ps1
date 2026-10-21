param(
    [Parameter(Mandatory=$true)][string]$StudyRepoPath,
    [string]$Python = 'python',
    [string]$OutputDirectory = ''
)
$ErrorActionPreference = 'Stop'
if (-not $OutputDirectory) {
    $repoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
    $OutputDirectory = Join-Path $repoRoot ('library\ess-experiment\out\natchan-cloud-v006-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
}
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Output directory exists. Choose a new directory.' }
New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
$evidence = Join-Path $OutputDirectory 'evidence'
& $Python (Join-Path $PSScriptRoot 'prepare_cloud_v006.py') --repo $StudyRepoPath --destination $evidence
if ($LASTEXITCODE -ne 0) { throw 'Evidence export failed; ensure the study checkout contains commit e8314ed.' }
& $Python (Join-Path $PSScriptRoot 'analyze_cloud_v006.py') --evidence-root $evidence --output (Join-Path $OutputDirectory 'analysis.json')
if ($LASTEXITCODE -ne 0) { throw 'Analysis failed; outputs preserved.' }
Write-Host "NATCHAN_CLOUD_V006_COMPLETE $OutputDirectory"
