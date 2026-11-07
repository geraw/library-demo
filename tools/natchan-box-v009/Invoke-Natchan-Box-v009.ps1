param(
    [Parameter(Mandatory = $true)][string]$Request,
    [Parameter(Mandatory = $true)][string]$Output,
    [string]$Python = 'python'
)
$ErrorActionPreference = 'Stop'
& $Python (Join-Path $PSScriptRoot 'natchan.py') analyze --request $Request --output $Output
$analyzerExit = $LASTEXITCODE
if ($analyzerExit -ne 0) {
    throw "Natchan v009 development analysis failed (exit $analyzerExit). Inspect diagnostics or stderr."
}
