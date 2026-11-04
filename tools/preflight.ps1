<#
Pre-flight before the first batch of a session (after RESUME, or after Tyler has played).

Usage:
    powershell -File tools/preflight.ps1

Checks, in order, and exits 1 on the first hard failure:
- build: `swofty doctor` must report build id -Build (everything is pinned to it); a patch means stop and tell the
  supervisor.
- drift: doctor must show `baseline no drift` or `drift: swofty is not part of the game` (the post-run state).
- game lock: runs tools/cleanup_test_profiles.ps1, which clears a stale `swofty-game.lock.d` when no F1_25 or swofty
  process is running, and deletes leftover test profiles.
- settings: warns if UDP is off, lists how `hardware_settings_config.xml` changed since the last pre-flight, then keeps
  this copy as the next reference (%LOCALAPPDATA%\verve-f1-25\settings-snapshots). Changes are reported, never undone.
#>
param(
    [string] $Swofty = "$env:LOCALAPPDATA\Programs\SwoftyLauncher\bin\swofty.exe",
    [string] $Build = '25251167'
)
$ErrorActionPreference = 'Stop'
$doc = & $Swofty doctor
$doc
$bid = ($doc | Where-Object { $_ -match '^build id\s+(\S+)' } | ForEach-Object { $Matches[1] })
if ($bid -ne $Build) { "PREFLIGHT FAIL: build $bid, pinned $Build. Stop and tell the supervisor."; exit 1 }
if (-not ($doc | Where-Object { $_ -match 'baseline\s+no drift|drift\s+swofty is not part of the game' })) {
    "PREFLIGHT FAIL: game folder drift. Run ``swofty restore`` and check again."; exit 1
}
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'cleanup_test_profiles.ps1') -Swofty $Swofty
$d = Join-Path $env:USERPROFILE 'Documents\My Games\F1 25\hardwaresettings'
$cur = Join-Path $d 'hardware_settings_config.xml'
if (Test-Path $cur) {
    if (-not (Select-String $cur -Pattern '<udp enabled="true"' -Quiet)) { 'settings: WARNING: UDP telemetry is not enabled; UDP captures will be empty' }
    # Tyler's own graphics choices aren't ours to flag, so compare with the last pre-flight, not the pre-UDP backup
    $snapDir = Join-Path $env:LOCALAPPDATA 'verve-f1-25\settings-snapshots'
    New-Item -ItemType Directory -Force $snapDir | Out-Null
    $last = Join-Path $snapDir 'hardware_settings_config.last.xml'
    if (Test-Path $last) {
        $diff = @(Compare-Object (Get-Content $last) (Get-Content $cur))
        if ($diff.Count) { "settings: $($diff.Count) line(s) changed since the last pre-flight:"; $diff | Format-Table -AutoSize -Wrap }
        else { 'settings: unchanged since the last pre-flight' }
    } else { 'settings: no earlier snapshot; this one is the new reference' }
    Copy-Item $cur $last -Force
}
'PREFLIGHT OK'
