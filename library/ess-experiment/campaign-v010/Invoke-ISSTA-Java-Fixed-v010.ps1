param(
    [Parameter(Mandatory=$true)][string]$ReferenceCampaignPath,
    [string]$ProvengoJar,
    [string]$Java = 'java',
    [int]$CaseTimeoutSeconds = 120,
    [int]$ArmTimeoutSeconds = 7200
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw "Repository Python not found: $python" }
Get-Command $Java -ErrorAction Stop | Out-Null
$arguments = @((Join-Path $PSScriptRoot 'java_suite_v010.py'), '--reference-campaign', $ReferenceCampaignPath,
    '--java', $Java, '--case-timeout', $CaseTimeoutSeconds, '--arm-timeout', $ArmTimeoutSeconds)
if ($ProvengoJar) { $arguments += @('--jar', $ProvengoJar) }
& $python @arguments
if ($LASTEXITCODE -ne 0) { throw 'v010 incomplete. Inspect V010_REVIEW_ZIP and native logs.' }
