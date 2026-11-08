[CmdletBinding()]
param(
    [ValidateSet('CheckB2','FullSample')][string]$Mode = 'CheckB2',
    [ValidateRange(1,10000)][int]$SampleSize = 500,
    [ValidateRange(1,100000)][int]$MaxLength = 2000,
    [string]$WorkBase = 'D:\Yeshayahu\Temp\ProvengoWork',
    [string]$OutputBase = 'E:\ProvengoRuns',
    [string]$ProvengoJar,
    [ValidateRange(1,86400)][int]$SampleTimeout = 300
)
$ErrorActionPreference = 'Stop'
$tag = 'full-v003-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff')
$batch = Join-Path $OutputBase $tag
New-Item -ItemType Directory -Path $batch | Out-Null
$runError = $null
try {
    $arguments = @{
        Mode = $Mode
        SampleSize = $SampleSize
        MaxLength = $MaxLength
        WorkBase = $WorkBase
        OutputBase = $batch
        SampleTimeout = $SampleTimeout
    }
    if ($ProvengoJar) { $arguments.ProvengoJar = $ProvengoJar }
    & (Join-Path $PSScriptRoot 'Invoke-V003.ps1') @arguments
    if ($LASTEXITCODE -ne 0) { throw "Campaign exited with code $LASTEXITCODE." }
}
catch { $runError = $_; Write-Host "Stopped: $($_.Exception.Message)" }
finally {
    $python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    foreach ($run in @(Get-ChildItem -LiteralPath $batch -Directory)) {
        if (Test-Path -LiteralPath (Join-Path $run.FullName 'summary.json')) {
            & $python (Join-Path $PSScriptRoot 'collect_results.py') $run.FullName
            if ($LASTEXITCODE -ne 0) { throw "ZIP collection failed: $($run.FullName)" }
        }
    }
    Write-Host "RESULT_BATCH $batch"
}
if ($null -ne $runError) { throw $runError }
