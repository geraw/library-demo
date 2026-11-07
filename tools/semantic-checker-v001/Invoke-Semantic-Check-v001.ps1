[CmdletBinding(DefaultParameterSetName='Trace')]
param(
    [Parameter(Mandatory=$true,ParameterSetName='Trace')][string]$TracePath,
    [Parameter(Mandatory=$true,ParameterSetName='Trace')]
    [ValidateSet('library-issta-v006','library-v38','garage-v38','pharmacy-v38','netbox-legacy-v38','netbox-a2a-v38','todoist-runtime-v38')]
    [string]$Profile,
    [Parameter(Mandatory=$true,ParameterSetName='Archive')][string]$ArchivePath,
    [string]$OutputPath,
    [Parameter(ParameterSetName='Trace')][switch]$SingleSequence,
    [Parameter(ParameterSetName='Trace')][switch]$InitialEmpty,
    [Parameter(ParameterSetName='Trace')][string]$NativeReport
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw "Repository Python not found: $python" }
if (-not $OutputPath) {
    $OutputPath = Join-Path $repo ('library\ess-experiment\runs\semantic-check-v001-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.json')
}
if ($PSCmdlet.ParameterSetName -eq 'Archive') {
    $arguments = @((Join-Path $PSScriptRoot 'validate_library_archive.py'), '--archive', $ArchivePath, '--output', $OutputPath)
} else {
    $arguments = @((Join-Path $PSScriptRoot 'checker.py'), 'evaluate', '--profile', $Profile, '--trace', $TracePath, '--output', $OutputPath)
    if ($SingleSequence) { $arguments += '--single-sequence' }
    if ($InitialEmpty) { $arguments += '--initial-empty' }
    if ($NativeReport) { $arguments += @('--native-report', $NativeReport) }
}
& $python @arguments
if ($LASTEXITCODE -ne 0) { throw "Evaluation incomplete or failed. Inspect the console and report if written: $OutputPath" }
Write-Host "SEMANTIC_CHECK_REPORT $OutputPath"
