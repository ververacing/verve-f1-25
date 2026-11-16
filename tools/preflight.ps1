<#
Pre-flight before the first batch of a session (after RESUME, or after Tyler has played).

Usage:
    powershell -File tools/preflight.ps1

Checks, in order, and exits 1 on the first hard failure:
- build: `swofty doctor` must report build id -Build (everything is pinned to it); a patch means stop and tell the
  supervisor.
- journals: 0 open Swofty journals (state\journal\*.json), since an open one means a modded game folder.
- drift: doctor must show `baseline no drift`, or only benign drift lines: `swofty is not part of the game` (the
  post-run state) and exactly `swofty/cache/exe-sha256.tsv is not part of the game` (Swofty's own cache file).
- game lock and test profiles: runs tools/cleanup_test_profiles.ps1, which clears a stale `swofty-game.lock.d` when no
  F1_25 or swofty process is running and deletes leftover test-* profiles. Fails if any test-* profile is still left.
- settings: warns if UDP is off, lists how `hardware_settings_config.xml` changed since the last pre-flight, then keeps
  this copy as the next reference (%LOCALAPPDATA%\verve-f1-25\settings-snapshots). Changes are reported, never undone.
#>
param(
    [string] $Swofty = "$env:LOCALAPPDATA\Programs\SwoftyLauncher\bin\swofty.exe",
    [string] $Build = '26566308'   # F1 25 1.0.145.2472 (Steam), since 2026-11-16 (docs/harness.md "F1 25 1.0.145"); was 25251167
)
$ErrorActionPreference = 'Stop'
$doc = & $Swofty doctor
$doc
$bid = ($doc | Where-Object { $_ -match '^build id\s+(\S+)' } | ForEach-Object { $Matches[1] })
if ($bid -ne $Build) { "PREFLIGHT FAIL: build $bid, pinned $Build. Stop and tell the supervisor."; exit 1 }
# benign drift (post_run_check's rule): the post-run line, and exactly Swofty's own cache file
$realDrift = @($doc | Where-Object { $_ -match '^drift\s+' -and $_ -notmatch '^drift\s+swofty is not part of the game\s*$' -and
    $_ -notmatch '^drift\s+swofty/cache/exe-sha256\.tsv is not part of the game\s*$' })
if ($realDrift.Count -or -not ($doc | Where-Object { $_ -match 'baseline\s+no drift|^drift\s+' })) {
    "PREFLIGHT FAIL: game folder drift. Run ``swofty restore`` and check again."; exit 1
}
$open = @($doc | Where-Object { $_ -match 'journal\s+\S+\s+is open' }) + @(Get-ChildItem (Join-Path $env:LOCALAPPDATA 'Swofty\state\journal') -File -Force -ErrorAction SilentlyContinue)
if ($open.Count) { "PREFLIGHT FAIL: $($open.Count) open Swofty journal(s): the game folder may be modded. Run tools/post_run_check.ps1."; exit 1 }
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'cleanup_test_profiles.ps1') -Swofty $Swofty
if ($LASTEXITCODE -ne 0) { "PREFLIGHT FAIL: test-* profiles are left over (above). Every run deletes its own; find out why before testing."; exit 1 }
# runs whose save check had to wait (F1 25 or the launcher was running as they ended): finish them now
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'deferred_saves_check.ps1')
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
