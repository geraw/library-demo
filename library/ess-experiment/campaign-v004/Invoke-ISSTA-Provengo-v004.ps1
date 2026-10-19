param(
    [ValidateSet(10,100,200)][int]$SampleSize = 10,
    [ValidateSet("business","investigator")][string]$Profile = "business",
    [switch]$IncludeMutant,
    [string]$ProvengoJar = '',
    [ValidateRange(1,5)][int]$BatchSize = 5
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw "Virtual environment missing: $python" }
if (-not $ProvengoJar) {
    $install = 'C:\Program Files\Provengo\Provengo Cli'
    $jars = @(Get-ChildItem -LiteralPath $install -Filter 'Provengo.uber.jar' -File -Recurse)
    if ($jars.Count -ne 1) { throw 'Pass -ProvengoJar with the exact JAR path.' }
    $ProvengoJar = $jars[0].FullName
}
if (-not (Test-Path $ProvengoJar)) { throw 'Provengo JAR does not exist.' }
Get-Command java -ErrorAction Stop | Out-Null
Write-Host 'ISSTA campaign v004: managed proxy 23243, backend 23244; existing port 23242 is untouched.'
$campaignArgs = @((Join-Path $PSScriptRoot 'campaign_v004.py'), 'provengo',
    '--repo', $repo, '--size', $SampleSize, '--profile', $Profile,
    '--batch-size', $BatchSize, '--jar', $ProvengoJar)
if ($IncludeMutant) { $campaignArgs += '--include-mutant' }
& $python @campaignArgs
if ($LASTEXITCODE -ne 0) { throw 'Campaign stopped. Inspect the newest runs\issta-*-v004-* directory.' }
