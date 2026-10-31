<#
Summarise the RaceStarts lines of a `swofty test run` report: one row per start and vehicle, plus per-vehicle and
per-start statistics.

Usage:
    powershell -File tools/racestarts_summary.ps1 -Report runs/<id>/raw/report -Out runs/<id>

Writes <Out>/summary.csv (start, test, vehicle, team_id, reaction_time, race_start_performance),
<Out>/per_vehicle.csv (median, min, max, n) and <Out>/per_start.csv (field mean and median, excluding -Exclude
vehicle ids), and copies each start's RaceStarts and session-trace lines to <Out>/racestarts_<start>.log.
Team ids come from the batch's `session trace ... teams a,b,c,...` line, read as vehicle id i = entry i.
#>
param(
    [Parameter(Mandatory)] [string] $Report,
    [Parameter(Mandatory)] [string] $Out,
    [int[]] $Exclude = @(),
    # isolation check: the gamedb "N overwritten" count each start must show. swofty.core + the always-on
    # teamsimplified.mods give 52 overwritten / 322 created on their own (docs/harness.md), so a vanilla batch is 52
    # and a test addon adds its own edit count. The settings line's addon count is not a check: it counts every
    # installed addon, enabled or not. -1 skips the check.
    [int] $ExpectOverwritten = -1
)
$ErrorActionPreference = 'Stop'
function Median([double[]] $v) { $s = $v | Sort-Object; $n = $s.Count; if ($n -eq 0) { return $null }; if ($n % 2) { $s[($n - 1) / 2] } else { ($s[$n / 2 - 1] + $s[$n / 2]) / 2 } }

$rep = Get-Content (Join-Path $Report 'report.json') -Raw | ConvertFrom-Json
$testByBatch = @{}; foreach ($t in $rep.tests) { $testByBatch[[int]$t.batch] = "$($t.id) ($($t.status))" }
New-Item -ItemType Directory -Force $Out | Out-Null
$rows = New-Object System.Collections.Generic.List[object]
$iso = New-Object System.Collections.Generic.List[object]
foreach ($b in (Get-ChildItem (Join-Path $Report 'batches') -Directory | Sort-Object { [int]$_.Name })) {
    $start = [int]$b.Name
    $log = Join-Path $b.FullName 'loader.log'
    if (-not (Test-Path $log)) { continue }
    $set = Select-String -Path $log -Pattern "\[settings\] .*: profile '([^']+)', (\d+) addon\(s\)" | Select-Object -First 1
    $gdb = Select-String -Path $log -Pattern '\[assets\] gamedb: \d+ overwritten, \d+ created' | Select-Object -First 1
    $n = if ($set) { [int]$set.Matches[0].Groups[2].Value } else { -1 }
    $ow = if ($gdb -and $gdb.Line -match 'gamedb: (\d+) overwritten') { [int]$Matches[1] } else { 0 }
    $iso.Add([pscustomobject]@{ start = $start; profile = $(if ($set) { $set.Matches[0].Groups[1].Value } else { '' }); installed_addons = $n
        overwritten = $ow; gamedb = $(if ($gdb) { ($gdb.Line -replace '^.*gamedb: ', '') } else { 'no gamedb edits' }) })
    if ($ExpectOverwritten -ge 0 -and $ow -ne $ExpectOverwritten) { throw "isolation: start $start overwrote $ow gamedb record(s), expected $ExpectOverwritten" }
    $lines = Select-String -Path $log -Pattern 'RaceStarts:|session trace (StateLoadSession Entering|StateSession Exiting)' | ForEach-Object { $_.Line }
    [IO.File]::WriteAllLines((Join-Path (Resolve-Path $Out) "racestarts_$start.log"), [string[]]$lines, (New-Object System.Text.UTF8Encoding $false))
    $teams = @(); $tl = $lines | Where-Object { $_ -match 'teams ([0-9,]+)\)' } | Select-Object -First 1
    if ($tl -match 'teams ([0-9,]+)\)') { $teams = $Matches[1] -split ',' | ForEach-Object { [int]$_ } }
    $rt = @{}; $perf = @{}
    foreach ($l in $lines) {
        if ($l -match 'Reaction Time for driver with vehicle id (\d+): ([0-9.]+)') { $rt[[int]$Matches[1]] = [double]$Matches[2] }
        elseif ($l -match 'Race Start performance for driver with vehicle id (\d+): ([0-9.]+)') { $perf[[int]$Matches[1]] = [double]$Matches[2] }
    }
    foreach ($v in ($rt.Keys | Sort-Object)) {
        $rows.Add([pscustomobject]@{ start = $start; test = $testByBatch[$start]; vehicle = $v
            team_id = $(if ($v -lt $teams.Count) { $teams[$v] } else { '' }); reaction_time = $rt[$v]; race_start_performance = $perf[$v] })
    }
}
$enc = New-Object System.Text.UTF8Encoding $false
function Save($name, $objs) { [IO.File]::WriteAllLines((Join-Path (Resolve-Path $Out) $name), [string[]]($objs | ConvertTo-Csv -NoTypeInformation), $enc) }
Save 'summary.csv' $rows
$pv = $rows | Group-Object vehicle | ForEach-Object { $r = [double[]]($_.Group | ForEach-Object reaction_time)
    [pscustomobject]@{ vehicle = [int]$_.Name; team_id = $_.Group[0].team_id; n = $r.Count; median = [math]::Round((Median $r), 4)
        min = ($r | Measure-Object -Minimum).Minimum; max = ($r | Measure-Object -Maximum).Maximum } } | Sort-Object vehicle
Save 'per_vehicle.csv' $pv
$ps = $rows | Group-Object start | ForEach-Object { $r = [double[]]($_.Group | Where-Object { $_.vehicle -notin $Exclude } | ForEach-Object reaction_time)
    [pscustomobject]@{ start = [int]$_.Name; test = $_.Group[0].test; n = $r.Count; field_mean = [math]::Round(($r | Measure-Object -Average).Average, 4)
        field_median = [math]::Round((Median $r), 4) } } | Sort-Object start
Save 'per_start.csv' $ps
Save 'isolation.csv' $iso
"rows: $($rows.Count); starts: $(@($ps).Count)"
$iso | Format-Table -AutoSize | Out-String
$pv | Format-Table -AutoSize | Out-String
$ps | Format-Table -AutoSize | Out-String
