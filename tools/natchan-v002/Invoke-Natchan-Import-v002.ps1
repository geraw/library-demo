[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$ArchivePath,
    [string]$ManifestPath,
    [switch]$LibraryV011,
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
    $OutputPath = Join-Path $repoRoot ('library\ess-experiment\out\natchan-evidence-v002-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.json')
}
$arguments = @((Join-Path $PSScriptRoot 'evidence.py'), '--archive', $ArchivePath, '--output', $OutputPath)
if ($LibraryV011) { $arguments += '--library-v011' }
if ($ManifestPath) { $arguments += @('--manifest', $ManifestPath) }
& $Python @arguments
if ($LASTEXITCODE -eq 2) { throw 'Evidence import is incomplete. Inspect issues in the saved NATCHAN_EVIDENCE report.' }
if ($LASTEXITCODE -ne 0) { throw 'Evidence import failed.' }
