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
- settings: lists how `hardware_settings_config.xml` differs from the pre-UDP backup. The only expected difference is
  the `<udp .../>` line; anything else (graphics, etc.) is reported, not changed.
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
$cur = Join-Path $d 'hardware_settings_config.xml'; $bak = Join-Path $d 'hardware_settings_config.pre-udp.xml'
if ((Test-Path $cur) -and (Test-Path $bak)) {
    $diff = @(Compare-Object (Get-Content $bak) (Get-Content $cur) | Where-Object { $_.InputObject -notmatch '<udp ' })
    if ($diff.Count) { "settings: $($diff.Count) line(s) differ from the pre-UDP backup besides <udp>:"; $diff | Format-Table -AutoSize -Wrap }
    else { 'settings: only the <udp> line differs from the pre-UDP backup' }
}
'PREFLIGHT OK'
