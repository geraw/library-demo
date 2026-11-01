[CmdletBinding()]
param(
    [ValidateSet('all','evomaster','restler','provengo-sample10','provengo-java')]
    [string]$Configuration = 'all',
    [ValidateRange(1,86400)][int]$Seconds = 60,
    [int]$Seed = 1,
    [ValidateRange(1024,65535)][int]$Port = 23443,
    [ValidateSet('all','none','B1','B2','B3','B4','B5','B6')][string]$Mutation = 'all',
    [ValidateRange(1,10000)][int]$MaxLength = 500,
    [ValidateRange(1,7200)][int]$CaseTimeout = 120,
    [ValidateRange(1,86400)][int]$JavaTimeout = 7200,
    [ValidateRange(0,542)][int]$JavaLimit = 0,
    [string]$ConfigPath,
    [string]$ReuseRun,
    [string]$Cases,
    [switch]$KeepDatabases,
    [switch]$PrepareOnly
)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$python = Join-Path $root '.venv-benchmark-v001\Scripts\python.exe'
if (-not (Test-Path $python)) { throw 'Run Setup-Library-Benchmark-v001.ps1 first.' }
if (-not $ConfigPath) { $ConfigPath = Join-Path $root 'tools.local.json' }
if (-not (Test-Path $ConfigPath)) { throw 'Tool configuration missing. Run Setup first.' }
$tools = if ($Configuration -eq 'all') { 'evomaster,restler,provengo-sample10,provengo-java' } else { $Configuration }
$arms = if ($Mutation -eq 'all') { 'none,B1,B2,B3,B4,B5,B6' } else { $Mutation }
$arguments = @((Join-Path $root 'campaign_v001.py'), '--config', $ConfigPath,
    '--tools', $tools, '--arms', $arms, '--seconds', [string]$Seconds,
    '--seed', [string]$Seed, '--port', [string]$Port, '--max-length', [string]$MaxLength,
    '--case-timeout', [string]$CaseTimeout, '--java-timeout', [string]$JavaTimeout,
    '--java-limit', [string]$JavaLimit)
if ($Cases) { $arguments += @('--cases', $Cases) }
if ($KeepDatabases) { $arguments += '--keep-databases' }
if ($ReuseRun) { $arguments += @('--reuse-run', $ReuseRun) }
if ($PrepareOnly) { $arguments += '--prepare-only' }
& $python @arguments
if ($LASTEXITCODE -ne 0) { throw 'Campaign incomplete. The printed REVIEW_ZIP preserves diagnostics and completed cells.' }
Write-Host 'LIBRARY_BENCHMARK_V001_COMMAND_COMPLETE'
