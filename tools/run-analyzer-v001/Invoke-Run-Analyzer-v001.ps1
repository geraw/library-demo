[CmdletBinding(DefaultParameterSetName='Manifest')]
param(
    [Parameter(Mandatory=$true,ParameterSetName='Manifest')][string]$ManifestPath,
    [Parameter(Mandatory=$true,ParameterSetName='LibraryArchive')][string]$LibraryArchivePath,
    [string]$OutputPath
)
$ErrorActionPreference='Stop'
$repo=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$python=Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw "Repository Python not found: $python" }
if (-not $OutputPath) {
    $OutputPath=Join-Path $repo ('library\ess-experiment\runs\run-analysis-v001-'+(Get-Date -Format 'yyyyMMdd-HHmmss-fff')+'.json')
}
$arguments=@((Join-Path $PSScriptRoot 'analyze_runs.py'),'--output',$OutputPath)
if ($PSCmdlet.ParameterSetName -eq 'LibraryArchive') { $arguments+=@('--library-archive',$LibraryArchivePath) }
else { $arguments+=@('--manifest',$ManifestPath) }
& $python @arguments
if ($LASTEXITCODE -ne 0) { throw 'Run analysis failed; inspect console. No generator or SUT was run.' }
