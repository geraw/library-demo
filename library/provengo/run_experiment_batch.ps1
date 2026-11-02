param(
    [string[]]$Pools,
    [int[]]$Sizes,
    [string]$RankingFunctionName,
    [string]$Label,
    [int]$Reps = 3,
    [string]$OutDir = "products/priority-experiment/genetic-runs",
    [string]$LogFile = "products/priority-experiment/genetic-runs/run_log.csv"
)

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
if (-not (Test-Path $LogFile)) {
    "pool,k,label,rankingFunction,rep,outFile,elapsedSeconds,timestamp" | Out-File -FilePath $LogFile -Encoding utf8
}

foreach ($pool in $Pools) {
    foreach ($k in $Sizes) {
        for ($rep = 1; $rep -le $Reps; $rep++) {
            $outFile = "$OutDir/${pool}_k${k}_${Label}_rep${rep}.json"
            $sw = [System.Diagnostics.Stopwatch]::StartNew()
            provengo ensemble -a genetic --ranking-function=$RankingFunctionName --size=$k --num-of-generations=50 `
                -s "products/priority-experiment/$pool.json" -o $outFile . 2>&1 | Out-Null
            $elapsed = $sw.Elapsed.TotalSeconds
            $line = "$pool,$k,$Label,$RankingFunctionName,$rep,$outFile,$elapsed,$(Get-Date -Format o)"
            $line | Out-File -FilePath $LogFile -Encoding utf8 -Append
            Write-Host $line
        }
    }
}
