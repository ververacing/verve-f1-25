<#
Finish save checks that a run had to defer (supervisor, 2026-11-14). When F1 25 or the Swofty Launcher (not ours)
was running as a run ended, guard_snapshot refuses, so the run wrote <run>\saves_diff_deferred.txt ("pending") and
kept its before-snapshot outside the repo (%LOCALAPPDATA%\verve-f1-25\snapshots\<id>.json; it names save files).
This takes the after-snapshot at the first moment nothing that isn't ours is running, and compares:
- equal: "checked late: unchanged". The race counts as save-checked (late).
- different: "CHANGED, Tyler played in between", for Tyler to judge. Not treated as our fault; nothing is undone.
It also runs post_run_check for that run. A race's B-0014 validity stays with #71's rules: this is a safety record.

Usage (tools/preflight.ps1 calls it):
    powershell -File tools/deferred_saves_check.ps1 [-Runs runs]    # exit 0; prints one line per deferred run
#>
param([string] $Runs = (Join-Path (Split-Path $PSScriptRoot) 'runs'))
$ErrorActionPreference = 'Stop'
$pending = @(Get-ChildItem $Runs -Recurse -Filter 'saves_diff_deferred.txt' -ErrorAction SilentlyContinue |
    Where-Object { (Get-Content $_.FullName -TotalCount 1) -like 'pending*' })
if (-not $pending.Count) { 'deferred save checks: none pending'; exit 0 }
if (Get-Process F1_25, swofty-launcher -ErrorAction SilentlyContinue) {
    "deferred save checks: $($pending.Count) still pending (F1 25 or the Swofty Launcher is running)"; exit 0
}
$snapDir = Join-Path $env:LOCALAPPDATA 'verve-f1-25\snapshots'
foreach ($f in $pending) {
    $run = $f.Directory.FullName
    $lines = Get-Content $f.FullName
    $id = ($lines | Where-Object { $_ -match '^snapshot (\S+)' } | ForEach-Object { $Matches[1] } | Select-Object -First 1)
    $snap = Join-Path $snapDir "$id.json"
    if (-not $id -or -not (Test-Path $snap)) { "$($f.Directory.Name): before-snapshot $id missing; left pending"; continue }
    $before = @{}
    (Get-Content $snap -Raw | ConvertFrom-Json).PSObject.Properties | ForEach-Object { $before[$_.Name] = $_.Value }
    $after = & (Join-Path $PSScriptRoot 'guard_snapshot.ps1')
    $diff = foreach ($k in @($before.Keys) + @($after.Keys) | Select-Object -Unique) {
        if ($before[$k] -ne $after[$k]) { "{0}: {1} -> {2}" -f $k, $before[$k], $after[$k] }
    }
    $stamp = Get-Date -Format s
    $result = if ($diff) {
        @("checked late $stamp`: CHANGED, Tyler played in between (F1 25 or the launcher was running after the run). For Tyler to judge; not treated as ours; nothing undone.") + @($diff)
    } else { @("checked late $stamp`: unchanged ($($after.Count) entries)") }
    Set-Content $f.FullName -Value (@($result) + @('--- was:') + @($lines)) -Encoding utf8
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'post_run_check.ps1') -Out $run | Out-Null
    "$($f.Directory.Name): $($result[0]) (post-run check exit $LASTEXITCODE)"
}
exit 0
