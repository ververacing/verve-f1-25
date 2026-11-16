<#
Re-dump the converter's two stock anchors (verve_to_swofty.py) with `swofty db get` (no --addon, so stock), for the
same drivers and datasets as an earlier dump, so the two can be diffed line for line.

Usage:
    powershell -File tools/dump_stock_grid.ps1 -OutDir docs/stock/26566308 [-From docs/stock]

Writes <OutDir>/driver_characteristics_grid.csv (each label's driver_characteristics row) and
<OutDir>/pace_curves_grid.csv (each stats_label/dataset pace evolution curve), in the same layout as the files in
-From, with a header comment naming the launcher version, the game build and the date. Refuses while F1 25 or the
Swofty Launcher is running (docs/process.md).
#>
param(
    [Parameter(Mandatory)] [string] $OutDir,
    [string] $From = 'docs/stock',
    [string] $Swofty = "$env:LOCALAPPDATA\Programs\SwoftyLauncher\bin\swofty.exe",
    [string] $Profile = 'verve-test'
)
$ErrorActionPreference = 'Stop'
if (Get-Process F1_25, swofty-launcher -ErrorAction SilentlyContinue) { 'F1 25 or the Swofty Launcher is running; not dumping'; exit 9 }
$ver = (& $Swofty --version).Trim()
$build = ((& $Swofty --profile $Profile doctor) | Where-Object { $_ -match '^build id\s+(\S+)' } | ForEach-Object { $Matches[1] })
$stamp = "$ver | build $build | stock values (no --addon) | dumped $(Get-Date -Format 'yyyy-MM-dd')"
New-Item -ItemType Directory -Force $OutDir | Out-Null

function Get-Lines([string] $path) {
    $out = & $Swofty --profile $Profile db get $path 2>&1
    if ($LASTEXITCODE -ne 0) { return $null }
    $out
}

# 1. driver rows
$keys = 'aggression', 'control', 'mistakes', 'reaction_speed', 'speed_in', 'speed_out'
$rows = Get-Content (Join-Path $From 'driver_characteristics_grid.csv') | Where-Object { $_ -notmatch '^#' } | ConvertFrom-Csv
$o = @("# $stamp | entrants.drivers.driver[_metadata_=<label>].driver_characteristics", ('label,' + ($keys -join ',')))
$missing = 0
foreach ($r in $rows) {
    $lines = Get-Lines "entrants.drivers.driver[_metadata_=$($r.label)].driver_characteristics"
    $v = foreach ($k in $keys) {
        $m = $lines | Where-Object { $_ -match "^\s+$k\s+(\S+)\s*$" } | Select-Object -First 1
        if ($m -and $m -match "^\s+$k\s+(\S+)\s*$") { $Matches[1] } else { $missing++; 'MISSING' }
    }
    $o += "$($r.label)," + ($v -join ',')
}
$o | Set-Content (Join-Path $OutDir 'driver_characteristics_grid.csv') -Encoding utf8
"driver rows: $($rows.Count), missing values: $missing"

# 2. pace curves
$curves = Get-Content (Join-Path $From 'pace_curves_grid.csv') | Where-Object { $_ -notmatch '^#' } | ConvertFrom-Csv
$p = @("# $stamp | DriverStatisticsHolder[driver=<stats_label>].StatisticsDataSet[_metadata_=<dataset>].Statistic[_metadata_=pace].evolution", '"stats_label","dataset","evolution"')
$cmiss = 0
foreach ($c in $curves) {
    $lines = Get-Lines "driver_statistics.driver_statistics.DriverStatisticsHolder[driver=$($c.stats_label)].StatisticsDataSet[_metadata_=$($c.dataset)].Statistic[_metadata_=pace].evolution"
    $m = $lines | Where-Object { $_ -match '^\s+value:\s+(\S+)' } | Select-Object -First 1
    $val = if ($m -and $m -match '^\s+value:\s+(\S+)') { $Matches[1] } else { $cmiss++; 'MISSING' }
    $p += '"{0}","{1}","{2}"' -f $c.stats_label, $c.dataset, $val
}
$p | Set-Content (Join-Path $OutDir 'pace_curves_grid.csv') -Encoding utf8
"pace curves: $($curves.Count), missing: $cmiss"
"header: $stamp"
