[CmdletBinding()]
param(
    [ValidateSet('Existing','Sample','FullSample','CheckB2')][string]$Mode = 'Existing',
    [string]$EvidencePath,
    [string]$WorkBase,
    [string]$OutputBase,
    [ValidateRange(0,10000)][int]$Limit = 0,
    [ValidateRange(1,10000)][int]$SampleSize = 500,
    [ValidateRange(1,100000)][int]$MaxLength = 2000,
    [int]$Seed = 10001,
    [ValidateRange(1,86400)][int]$SampleTimeout = 300,
    [string]$ProvengoJar,
    [string]$Java = 'java',
    [string]$ResumeRun
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
if (-not $WorkBase) { $WorkBase = Join-Path $repo 'library-v003-work' }
if (-not $OutputBase) { $OutputBase = Join-Path $repo 'library-v003-results' }
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    python -m venv (Join-Path $PSScriptRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
}
& $python -c "import importlib.util as u, importlib.metadata as m; exit(0 if u.find_spec('flask') and m.version('flask') == '3.1.3' else 1)"
if ($LASTEXITCODE -ne 0) {
    & $python -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
}
& $python -m unittest discover -s $PSScriptRoot -p 'test_*.py'
if ($LASTEXITCODE -ne 0) { throw 'Directed regression verification failed.' }
if ($Mode -eq 'Existing') {
    if ($ResumeRun) { throw 'ResumeRun applies to Sample mode only.' }
    if (-not $EvidencePath) { $EvidencePath = Join-Path $repo 'library\clean-scenarios-v001' }
    if (-not (Test-Path -LiteralPath $EvidencePath)) { throw 'EvidencePath not found.' }
    $tag = 'library-v003-existing-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff')
    $work = Join-Path $WorkBase $tag
    $output = Join-Path $OutputBase $tag
    Write-Host 'ENGINE Flask test_client replay; mutations v003'
    Write-Host "RESULT_DIRECTORY $output"
    & $python (Join-Path $PSScriptRoot 'replay.py') --evidence $EvidencePath --work $work --output $output --limit $Limit
} else {
    if (-not $ProvengoJar) {
        $toolConfig = Join-Path $repo 'library\benchmark-v001\tools.local.json'
        if (Test-Path -LiteralPath $toolConfig) {
            $settings = Get-Content -LiteralPath $toolConfig -Raw | ConvertFrom-Json
            $ProvengoJar = $settings.provengo_jar
            if ($settings.java -and $Java -eq 'java') { $Java = $settings.java }
        }
    }
    if (-not $ProvengoJar) { $ProvengoJar = 'C:\Program Files\Provengo\Provengo Cli\Provengo.uber.jar' }
    if (-not (Test-Path -LiteralPath $ProvengoJar -PathType Leaf)) { throw 'Pass -ProvengoJar with the installed Provengo JAR.' }
    if ($Mode -eq 'CheckB2') { $SampleSize = 1 }
    $arguments = @((Join-Path $PSScriptRoot 'sample_campaign.py'), '--jar', $ProvengoJar,
        '--java', $Java, '--count', "$SampleSize", '--max-length', "$MaxLength", '--seed', "$Seed",
        '--timeout', "$SampleTimeout", '--work-base', $WorkBase, '--output-base', $OutputBase)
    if ($Mode -eq 'FullSample' -or $Mode -eq 'CheckB2') { $arguments += @('--model','full') }
    if ($Mode -eq 'CheckB2') {
        $arguments += '--b2-witness'
    }
    if ($ResumeRun) { $arguments += @('--resume', $ResumeRun) }
    Write-Host "ENGINE Provengo sampling ($Mode) + Flask test_client replay; mutations v003"
    & $python @arguments
}
if ($LASTEXITCODE -ne 0) { throw 'v003 stopped. Inspect the printed result/work directory; evidence retained.' }
