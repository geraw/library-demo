[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$RequestPath,
    [Parameter(Mandatory=$true)][string]$OutputPath,
    [string]$Python = 'python'
)
$ErrorActionPreference = 'Stop'
& $Python (Join-Path $PSScriptRoot 'natchan.py') --request $RequestPath --output $OutputPath
$analysisExit = $LASTEXITCODE
if ($analysisExit -ne 0) {
    throw "Natchan failed with exit code $analysisExit. Inspect diagnostics.json if the output directory was created."
}
$resultPath = Join-Path $OutputPath 'result.json'
$result = Get-Content -LiteralPath $resultPath -Raw | ConvertFrom-Json
Write-Host "NATCHAN_PROCESSING_STATUS $($result.status)"
Write-Host "NATCHAN_RESULT $resultPath"

