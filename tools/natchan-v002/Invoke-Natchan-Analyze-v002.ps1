[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$ArchivePath,
    [string]$ManifestPath,
    [switch]$LibraryV011,
    [string]$ControlRun,
    [string]$OutputPath,
    [string]$Python
)
$ErrorActionPreference = 'Stop'
if ($LibraryV011 -and $ManifestPath) { throw 'Choose LibraryV011 or ManifestPath.' }
$repoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
if (-not $Python) {
    $localPython = Join-Path $repoRoot '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $localPython) { $Python = $localPython } else { $Python = 'python' }
}
if (-not $OutputPath) {
    $OutputPath = Join-Path $repoRoot ('library\ess-experiment\out\natchan-analysis-v002-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.json')
}
$arguments = @((Join-Path $PSScriptRoot 'analyze.py'), '--archive', $ArchivePath, '--output', $OutputPath)
if ($LibraryV011) { $arguments += '--library-v011' }
if ($ManifestPath) { $arguments += @('--manifest', $ManifestPath) }
if ($ControlRun) { $arguments += @('--control-run', $ControlRun) }
& $Python @arguments
if ($LASTEXITCODE -eq 2) { throw 'Analysis is incomplete. Inspect the saved NATCHAN_ANALYSIS report.' }
if ($LASTEXITCODE -ne 0) { throw 'Analysis failed.' }
