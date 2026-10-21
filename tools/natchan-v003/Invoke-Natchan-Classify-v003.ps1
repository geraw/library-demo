[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$InputPath,
    [string]$OutputPath,
    [string]$CatalogPath,
    [string]$Python
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
if (-not $Python) {
    $localPython = Join-Path $repoRoot '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $localPython) { $Python = $localPython } else { $Python = 'python' }
}
if (-not $OutputPath) {
    $OutputPath = Join-Path $repoRoot ('library\ess-experiment\out\natchan-classification-v003-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.json')
}
$arguments = @((Join-Path $PSScriptRoot 'classifier.py'), '--input', $InputPath, '--output', $OutputPath)
if ($CatalogPath) { $arguments += @('--catalogs', $CatalogPath) }
& $Python @arguments
if ($LASTEXITCODE -ne 0) { throw 'Natchan classification failed.' }
