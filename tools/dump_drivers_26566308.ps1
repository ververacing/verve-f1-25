<#
Dump the stock driver data for every 2025- and 2026-grid driver on the current game build (read-only `swofty db get`,
no --addon, so stock), plus the f1_2025 / f1_2026 driver_parameter_maps. Written for build 26566308.
Slow: one swofty process per value, about 1.4 s each and about 100 calls per driver (84 of them ai_driver_config), so
the full 25-row run takes about an hour serially. Run it between game sessions. For the six bundle keys only, use
tools/dump_bundle_26566308.ps1 (7 calls per driver).

Usage:
    powershell -File tools/dump_drivers_26566308.ps1 [-OutDir docs/stock] [-Drivers max_verstappen,lando_norris]

Writes:
    <OutDir>/drivers_26566308.csv                one row per driver (+ default_driver as a reference row): seasons
        (crosswalk and entrant lists), row label/index, stats label/holder, the six driver_characteristics,
        seasonal_info, ratings (experience/racecraft/awareness/pace/focus) per dataset at season x=0 with the full
        curves, each dataset's game_setup_modes/seasons tags, and all 84 ai_driver_config keys.
    <OutDir>/driver_parameter_maps_26566308.txt  driver_parameter_maps of the f1_2025 and f1_2026 vehicle packages.

Only `db get` is called, always with --profile (default verve-test). Refuses to start, and stops (writing what it has,
exit 9), if F1 25, the Swofty Launcher or swofty-ui is running (checked every 20 calls).
Labels: data/crosswalk_f1.csv (f1_25_label, stats_label, grid); ai_driver_config keys: docs/ai_driver_config_keys.csv.
#>
param(
    [string] $OutDir = 'docs/stock',
    [string] $Drivers = '',
    [string] $Crosswalk = 'data/crosswalk_f1.csv',
    [string] $Catalogue = 'docs/ai_driver_config_keys.csv',
    [string] $Swofty = "$env:LOCALAPPDATA\Programs\SwoftyLauncher\bin\swofty.exe",
    [string] $Profile = 'verve-test'
)
$ErrorActionPreference = 'Continue'
function Test-Busy { [bool](Get-Process F1_25, swofty-launcher, swofty-ui -ErrorAction SilentlyContinue) }
if (Test-Busy) { 'F1 25, the Swofty Launcher or swofty-ui is running; not dumping'; exit 9 }
$enc = New-Object System.Text.UTF8Encoding $false
New-Item -ItemType Directory -Force $OutDir | Out-Null
$script:calls = 0
$script:onAbort = $null

function Get-Lines([string] $path) {
    $script:calls++
    if ($script:calls % 20 -eq 0 -and (Test-Busy)) {
        if ($script:onAbort) { & $script:onAbort }
        'STOPPED: F1 25 or the launcher started mid-dump; partial output written'; exit 9
    }
    $out = & $Swofty --profile $Profile db get $path 2>$null
    if ($LASTEXITCODE -ne 0) { return $null }
    @($out)
}
# one level as an ordered key -> value map (containers and missing values map to '')
function Get-Map([string] $path) {
    $lines = Get-Lines $path
    if (-not $lines) { return $null }
    $m = [ordered]@{ '__resolved' = $lines[0].Trim() }
    foreach ($l in $lines | Select-Object -Skip 1) {
        if ($l -notmatch '^  \S') { continue }
        $parts = $l.Trim() -split '\s{2,}', 2
        if ($parts.Count -eq 1 -and $parts[0] -match '\s') { continue }   # a table's description line
        $m[$parts[0]] = if ($parts.Count -eq 2) { $parts[1] } else { '' }
    }
    $m
}
function Get-Leaf([string] $path) {
    $lines = Get-Lines $path
    if (-not $lines) { return 'MISSING' }
    (($lines | Where-Object { $_ -match '^\s+value:' }) -replace '^\s+value:\s*', '') -join ' '
}
# y at season x=0: the first curve point with x=0 (several stock curves have two x=0 points; the curve column keeps both)
function Get-X0([string] $curve) {
    if (-not $curve -or $curve -notmatch '^@v2@') { return '' }
    $pts = ($curve -replace '^@v2@', '') -split ',' | Where-Object { $_ -notmatch '^(minx|maxx|miny|maxy):' }
    foreach ($p in $pts) { $xy = $p -split ':'; if ([double]$xy[0] -eq 0) { return $xy[1] } }
    ''
}

# recursive walker (same output layout as tools/dump_stock.ps1)
function Walk([string] $p, [int] $depth, [System.Text.StringBuilder] $sb) {
    $lines = Get-Lines $p
    if (-not $lines) { [void]$sb.AppendLine(('  ' * $depth) + "!! $p : not in the game database"); return }
    $base = $lines[0].Trim()
    if ($base -match '\(0x[0-9a-f]{16}, type \d+\)') { foreach ($l in $lines | Select-Object -Skip 1) { [void]$sb.AppendLine(('  ' * $depth) + $l.Trim()) }; return }
    foreach ($l in $lines | Select-Object -Skip 1) {
        if ($l -notmatch '^  \S') { continue }
        $parts = $l.Trim() -split '\s{2,}', 2
        if ($parts.Count -eq 1 -and $parts[0] -match '\s') { continue }
        $k = $parts[0]; $v = if ($parts.Count -eq 2) { $parts[1] } else { '' }
        $pad = '  ' * $depth
        if ($v -match '^table, \d+ rows$') {
            [void]$sb.AppendLine("$pad$k  [$v]")
            $rows = Get-Map "$base.$k"
            foreach ($rk in @($rows.Keys | Where-Object { $_ -ne '__resolved' })) {
                [void]$sb.AppendLine("$pad  $rk  ($($rows[$rk]))"); Walk "$base.$rk" ($depth + 2) $sb
            }
        } elseif ($v -eq '') { [void]$sb.AppendLine("$pad$k"); Walk "$base.$k" ($depth + 1) $sb }
        else { [void]$sb.AppendLine("$pad$k  $v") }
    }
}

$ver = (& $Swofty --version).Trim()
$build = ((& $Swofty --profile $Profile doctor) | Where-Object { $_ -match '^build id\s+(\S+)' } | ForEach-Object { $Matches[1] })
$stamp = "$ver | F1 25 build $build | stock values (no --addon) | profile $Profile | dumped $(Get-Date -Format 'yyyy-MM-dd')"
"header: $stamp"

# --- 1. driver_parameter_maps: f1_2025 and f1_2026 vehicle packages ---
$pk = Get-Map 'entrants.vehicles.vehicle_packages.vehicle_package'
$sb = New-Object System.Text.StringBuilder
[void]$sb.AppendLine("# $stamp")
$pkgs = foreach ($want in 'f1_2025', 'f1_2026') { $pk.Keys | Where-Object { $pk[$_] -eq $want } | ForEach-Object { [pscustomobject]@{ idx = $_; label = $want } } }
[void]$sb.AppendLine("# vehicle packages: " + (($pkgs | ForEach-Object { "$($_.idx) = $($_.label)" }) -join ', ') + " ($($pk.Count - 1) packages in all)")
foreach ($p in $pkgs) {
    $root = "entrants.vehicles.vehicle_packages.$($p.idx).ai_vehicle_package_config.driver_parameter_maps"
    [void]$sb.AppendLine("# === $($p.label): $root")
    Walk $root 0 $sb
}
[IO.File]::WriteAllText((Join-Path $OutDir 'driver_parameter_maps_26566308.txt'), $sb.ToString(), $enc)
"parameter maps: $($pkgs.Count) packages"

# --- 2. which drivers are on the f1_2025 / f1_2026 grids and career lists (entrant -> entrant_reference -> driver) ---
$lists = 'f1_2025', 'f1_2026', 'f1_career_2025', 'f1_career_2025_driver_pool', 'f1_career_2025_reserve_drivers',
         'f1_career_2026', 'f1_career_2026_driver_pool', 'f1_career_2026_reserve_drivers'
$member = @{}   # driver label -> list of entrant-list labels
$refCache = @{}
foreach ($ln in $lists) {
    $ents = Get-Map "entrants.entrant_lists.entrant_list[_metadata_=$ln].entrant"
    if (-not $ents) { "entrant list $ln : no entrant table"; continue }
    $base = $ents['__resolved'] -replace '\.entrant$', ''   # rows live beside the table: entrant_list_N.entrant_K
    foreach ($ek in @($ents.Keys | Where-Object { $_ -ne '__resolved' })) {
        $e = Get-Map "$base.$ek"
        $drv = $e['driver']
        if (-not $drv -and $e['entrant_reference']) {
            $r = $e['entrant_reference']
            if (-not $refCache.ContainsKey($r)) { $refCache[$r] = (Get-Map "entrants.entrant_lists.entrants.entrant[_metadata_=$r]")['driver'] }
            $drv = $refCache[$r]
        }
        if ($drv) { if (-not $member[$drv]) { $member[$drv] = New-Object System.Collections.ArrayList }; [void]$member[$drv].Add($ln) }
    }
}
"entrant lists scanned: $($lists.Count), drivers found: $($member.Count)"

# seasonal_infos (per-driver, per-season overrides of car number etc.)
$si = @{}
$sit = Get-Map 'entrants.drivers.seasonal_infos.seasonal_info'
foreach ($k in @($sit.Keys | Where-Object { $_ -ne '__resolved' })) {
    $m = Get-Map "entrants.drivers.seasonal_infos.$k"
    $txt = "$k modes=$($m['game_setup_modes']) seasons=$($m['seasons']) number=$($m['preferred_car_number']) use_1=$($m['is_using_number_1_in_first_season'])"
    if ($si[$m['_metadata_']]) { $si[$m['_metadata_']] += "; $txt" } else { $si[$m['_metadata_']] = $txt }
}

# --- 3. per-driver rows ---
$cw = Import-Csv $Crosswalk | Where-Object { $_.f1_25_label }
$labels = if ($Drivers) { @($Drivers -split ',' | ForEach-Object { $_.Trim() }) } else { @($cw.f1_25_label) + 'default_driver' }
$keys = Import-Csv $Catalogue
$stats = 'experience', 'racecraft', 'awareness', 'pace', 'focus'
$chars = 'aggression', 'control', 'mistakes', 'reaction_speed', 'speed_in', 'speed_out', 'preferred_tracks'
$baseRowKeys = $null
$out = New-Object System.Collections.ArrayList
$writeCsv = {
    $lines = @("# $stamp", '# one row per 2025/2026-grid driver (default_driver = reference row); ratings are y at season x=0 (first x=0 point) of DriverStatisticsHolder[driver=<stats_label>].StatisticsDataSet[_metadata_=<dataset>].Statistic[_metadata_=<stat>].evolution; ai.* = entrants.drivers.driver[_metadata_=<row_label>].ai_driver_config.<group>.<leaf>')
    $lines += @($out | ConvertTo-Csv -NoTypeInformation)
    [IO.File]::WriteAllLines((Join-Path $OutDir 'drivers_26566308.csv'), $lines, $enc)
}
$script:onAbort = $writeCsv
foreach ($lab in $labels) {
    if (Test-Busy) { & $writeCsv; 'STOPPED: F1 25 or the launcher is running; partial output written'; exit 9 }
    $c = $cw | Where-Object { $_.f1_25_label -eq $lab } | Select-Object -First 1
    $statsLabel = if ($c) { $c.stats_label } else { $lab }
    $r = [ordered]@{
        seasons_crosswalk = if ($c) { $c.grid } else { 'reference' }
        seasons_db = ((@($member[$lab]) | Where-Object { $_ -in 'f1_2025', 'f1_2026' }) -replace '^f1_', '') -join '|'
        entrant_lists = (@($member[$lab]) -join '|')
        row_label = $lab; row_index = ''; stats_label = $statsLabel; holder_index = ''; holder_metadata = ''
    }
    $row = Get-Map "entrants.drivers.driver[_metadata_=$lab]"
    if ($row) {
        $r.row_index = $row['__resolved'] -replace '^entrants\.drivers\.', ''
        if (-not $baseRowKeys) { $baseRowKeys = @($row.Keys) }
        $r.row_extra_keys = (@($row.Keys | Where-Object { $_ -notin $baseRowKeys }) -join '|')
        $r.row_missing_keys = (@($baseRowKeys | Where-Object { $_ -notin $row.Keys }) -join '|')
        $dc = Get-Map "$($row['__resolved']).driver_characteristics"
        foreach ($k in $chars) { $r[$k] = if ($dc.Contains($k)) { $dc[$k] } else { 'MISSING' } }
        $r.dc_extra_keys = (@($dc.Keys | Where-Object { $_ -ne '__resolved' -and $_ -notin $chars }) -join '|')
    } else { $r.row_index = 'MISSING'; $r.row_extra_keys = ''; $r.row_missing_keys = ''; foreach ($k in $chars) { $r[$k] = 'MISSING' }; $r.dc_extra_keys = '' }
    $r.seasonal_info = if ($si[$lab]) { $si[$lab] } else { '' }
    $h = Get-Map "driver_statistics.driver_statistics.DriverStatisticsHolder[driver=$statsLabel]"
    $dsl = $null
    if ($h) {
        $r.holder_index = $h['__resolved'] -replace '^driver_statistics\.driver_statistics\.', ''
        $r.holder_metadata = $h['_metadata_']
        $dsl = Get-Map "$($h['__resolved']).StatisticsDataSet"
    }
    $r.datasets = if ($dsl) { (@($dsl.Keys | Where-Object { $_ -ne '__resolved' } | ForEach-Object { $dsl[$_] }) -join '|') } else { 'NO_HOLDER' }
    foreach ($ds in 'default', '2026') {
        $r["${ds}_game_setup_modes"] = ''; $r["${ds}_seasons"] = ''; $r["${ds}_statistics"] = ''
        foreach ($s in $stats) { $r["${ds}_${s}_x0"] = '' }
        foreach ($s in $stats) { $r["${ds}_${s}_curve"] = '' }
        $dsk = if ($dsl) { $dsl.Keys | Where-Object { $_ -ne '__resolved' -and $dsl[$_] -eq $ds } | Select-Object -First 1 }
        if (-not $dsk) { continue }
        $dpath = "$($h['__resolved']).$dsk"
        $dm = Get-Map $dpath
        $r["${ds}_game_setup_modes"] = $dm['game_setup_modes']; $r["${ds}_seasons"] = $dm['seasons']
        $st = Get-Map "$dpath.Statistic"
        $names = @($st.Keys | Where-Object { $_ -ne '__resolved' } | ForEach-Object { $st[$_] })
        $r["${ds}_statistics"] = $names -join '|'
        foreach ($sk in @($st.Keys | Where-Object { $_ -ne '__resolved' })) {
            $sm = Get-Map "$dpath.$sk"
            $s = $sm['_metadata_']
            if ($s -in $stats) { $r["${ds}_${s}_curve"] = $sm['evolution']; $r["${ds}_${s}_x0"] = Get-X0 $sm['evolution'] }
        }
    }
    foreach ($k in $keys) {
        $r["ai.$($k.group).$($k.leaf)"] = if ($row) { Get-Leaf "entrants.drivers.driver[_metadata_=$lab].ai_driver_config.$($k.group).$($k.leaf)" } else { 'MISSING' }
    }
    [void]$out.Add([pscustomobject]$r)
    & $writeCsv
    "$lab done ($script:calls calls so far)"
}
"drivers: $($out.Count), calls: $script:calls"
