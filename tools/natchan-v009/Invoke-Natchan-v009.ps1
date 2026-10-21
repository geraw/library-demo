param(
    [Parameter(Mandatory=$true)][string]$InputPath,
    [string]$OutputPath,
    [switch]$Historical
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { $python = 'python' }
if (-not $OutputPath) {
    $OutputPath = Join-Path $repo ('natchan-v009-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.json')
}
$script = if ($Historical) { 'historical.py' } else { 'analyzer.py' }
& $python (Join-Path $PSScriptRoot $script) --input $InputPath --output $OutputPath
if ($LASTEXITCODE -ne 0) { throw 'Natchan v009 failed. Inspect the diagnostic above.' }
Write-Host "NATCHAN_REPORT $OutputPath"
