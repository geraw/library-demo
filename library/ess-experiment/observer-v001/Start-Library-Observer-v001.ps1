param(
    [Parameter(Mandatory=$true)][string]$SutPath,
    [ValidateSet('none','1,2,3,4,5','1,2,3,5','4')][string]$Bugs = 'none',
    [int]$Port = 23243,
    [string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw "Repository Python not found: $python" }
$sut = (Resolve-Path -LiteralPath $SutPath).Path
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $repo ('library\ess-experiment\runs\observer-v001-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
}
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Choose a new output directory to avoid combining sessions.' }
New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
$outputPath = (Resolve-Path -LiteralPath $OutputDirectory).Path
$oldToken = $env:ISSTA_SERVICE_TOKEN
$oldBugs = $env:ISSTA_BUGS
$env:ISSTA_SERVICE_TOKEN = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
Write-Host "OBSERVER_URL http://127.0.0.1:$Port"
Write-Host "OBSERVER_LOG $outputPath\http.jsonl"
Write-Host 'In another terminal, initialize /__campaign__/case before sending tool requests. Stop with Ctrl+C.'
try {
    & $python (Join-Path $PSScriptRoot '..\campaign-v006\observed_server_v006.py') `
        --sut $sut --bugs $Bugs --port $Port --log (Join-Path $outputPath 'http.jsonl')
    if ($LASTEXITCODE -ne 0) { throw 'Observer stopped with an error. Inspect console and http.jsonl.' }
} finally {
    $env:ISSTA_SERVICE_TOKEN = $oldToken
    $env:ISSTA_BUGS = $oldBugs
}
