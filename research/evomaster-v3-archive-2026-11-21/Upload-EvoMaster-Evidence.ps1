[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ArchivePath,

    [Parameter(Mandatory = $true)]
    [string]$RepositoryPath,

    [ValidateRange(10, 95)]
    [int]$PartSizeMiB = 90
)

$ErrorActionPreference = 'Stop'
$branch = 'codex/restler-evomaster-archive-2026-11-21'
$relativeEvidencePath = 'research/evomaster-v3-archive-2026-11-21/evidence'
$expectedArchiveSha256 = '4e29fde3f73e62f81b8859ca11693d436a68dec424f2f6e1e11ec17797b0f1c2'

$archive = (Resolve-Path -LiteralPath $ArchivePath).Path
$repo = (Resolve-Path -LiteralPath $RepositoryPath).Path
if (-not (Test-Path -LiteralPath (Join-Path $repo '.git'))) {
    throw "RepositoryPath is not the repository root: $repo"
}

$archiveInfo = Get-Item -LiteralPath $archive
$archiveSha256 = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($archiveSha256 -ne $expectedArchiveSha256) {
    throw "Archive SHA-256 mismatch. Expected $expectedArchiveSha256; found $archiveSha256."
}

$requiredBytes = [int64]($archiveInfo.Length * 2 + 512MB)
$volume = [System.IO.DriveInfo]::new([System.IO.Path]::GetPathRoot($repo))
if ($volume.AvailableFreeSpace -lt $requiredBytes) {
    throw "Insufficient free space. Need about $([math]::Round($requiredBytes / 1GB, 2)) GB; available $([math]::Round($volume.AvailableFreeSpace / 1GB, 2)) GB."
}

& git -C $repo fetch origin $branch
if ($LASTEXITCODE -ne 0) { throw 'Could not fetch the archive branch.' }

$localBranch = & git -C $repo branch --list $branch
if ($LASTEXITCODE -ne 0) { throw 'Could not inspect local branches.' }
if ($localBranch) {
    & git -C $repo switch $branch
} else {
    & git -C $repo switch --track -c $branch "origin/$branch"
}
if ($LASTEXITCODE -ne 0) { throw 'Could not switch to the archive branch.' }

& git -C $repo pull --ff-only origin $branch
if ($LASTEXITCODE -ne 0) { throw 'Could not fast-forward the archive branch.' }

$evidenceDirectory = Join-Path $repo $relativeEvidencePath
if (Test-Path -LiteralPath $evidenceDirectory) {
    throw "Evidence directory already exists; no files were overwritten: $evidenceDirectory"
}
New-Item -ItemType Directory -Path $evidenceDirectory | Out-Null

$partBytes = [int64]$PartSizeMiB * 1MB
$buffer = New-Object byte[] (1MB)
$parts = [System.Collections.Generic.List[object]]::new()
$inputStream = [System.IO.File]::OpenRead($archive)
try {
    $partNumber = 1
    while ($inputStream.Position -lt $inputStream.Length) {
        $partName = 'EvoMaster-all-evidence-20261120.zip.part{0:D3}' -f $partNumber
        $partPath = Join-Path $evidenceDirectory $partName
        $outputStream = [System.IO.File]::Open(
            $partPath,
            [System.IO.FileMode]::CreateNew,
            [System.IO.FileAccess]::Write,
            [System.IO.FileShare]::None
        )
        try {
            $remaining = [math]::Min($partBytes, $inputStream.Length - $inputStream.Position)
            $partLength = [int64]0
            while ($remaining -gt 0) {
                $requested = [int][math]::Min($buffer.Length, $remaining)
                $read = $inputStream.Read($buffer, 0, $requested)
                if ($read -le 0) { throw 'Unexpected end of archive while splitting.' }
                $outputStream.Write($buffer, 0, $read)
                $remaining -= $read
                $partLength += $read
            }
            $outputStream.Flush()
        } finally {
            $outputStream.Dispose()
        }

        $parts.Add([pscustomobject]@{
            file = $partName
            size_bytes = $partLength
            sha256 = (Get-FileHash -LiteralPath $partPath -Algorithm SHA256).Hash.ToLowerInvariant()
        })
        $partNumber++
    }
} finally {
    $inputStream.Dispose()
}

$manifest = [ordered]@{
    archive = [System.IO.Path]::GetFileName($archive)
    archive_size_bytes = $archiveInfo.Length
    archive_sha256 = $archiveSha256
    part_size_limit_bytes = $partBytes
    part_count = $parts.Count
    parts = @($parts)
}
$manifestPath = Join-Path $evidenceDirectory 'parts-manifest.json'
[System.IO.File]::WriteAllText(
    $manifestPath,
    ($manifest | ConvertTo-Json -Depth 5),
    [System.Text.UTF8Encoding]::new($false)
)

& git -C $repo add -- $relativeEvidencePath
if ($LASTEXITCODE -ne 0) { throw 'Git add failed.' }
& git -C $repo commit --only -m 'Add complete EvoMaster campaign evidence archive' -- $relativeEvidencePath
if ($LASTEXITCODE -ne 0) { throw 'Git commit failed. Other local changes were left untouched.' }
& git -C $repo push origin $branch
if ($LASTEXITCODE -ne 0) { throw 'Git push failed. The commit remains local; retry the push after resolving the remote issue.' }

Write-Host "Uploaded $($parts.Count) archive parts to branch $branch."
Write-Host "Evidence directory: $relativeEvidencePath"
Write-Host "Archive SHA-256: $($manifest.archive_sha256)"
