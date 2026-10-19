param(
    [ValidateSet(100,200)][int]$SampleSize = 100,
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
Write-Host 'ISSTA campaign v003: managed proxy 23243, backend 23244; existing port 23242 is untouched.'
& $python (Join-Path $PSScriptRoot 'campaign_v003.py') provengo `
    --repo $repo --size $SampleSize --batch-size $BatchSize --jar $ProvengoJar
if ($LASTEXITCODE -ne 0) { throw 'Campaign stopped. Inspect the newest runs\issta-v003-* directory.' }
