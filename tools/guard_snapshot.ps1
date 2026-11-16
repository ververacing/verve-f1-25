<#
The hash guard's snapshot of everything of Tyler's that a test run must never change. sandbox_run.ps1 and
sandbox_shell.ps1 take one before and one after every run; any difference is exit 5 (stop, tell Tyler, never restore).

Usage:
    $snap = & tools/guard_snapshot.ps1 [-SteamApp <Steam>\userdata\<steamid>\3059520]    # an ordered dictionary

Entries:
- `file <name>`: every file in Steam's `remote\` (size, mtime ticks, sha256).
- `steam <name>`: Steam's record of each file in `remotecache.vdf` (size, sha, localtime). Steam rewrites the file on
  every game exit, so its raw bytes aren't compared.
- `launcher <profile>\<path>`: every file in the launcher saves (`%LOCALAPPDATA%\Swofty\saves\<profile>\`) of every
  profile that isn't ours, so Tyler's `tyler` profile and any profile he makes later (size, mtime ticks, sha256).
  Ours are `verve-*` and the `test-*` throwaways. The career vault isn't included: the launcher adds snapshots to it
  around every session by design.
#>
param(
    [string] $SteamApp = '',
    [string] $LauncherSaves = "$env:LOCALAPPDATA\Swofty\saves"
)
$ErrorActionPreference = 'Stop'
# Standing rule (supervisor, 2026-11-14): when F1 25 or the Swofty Launcher is running and it isn't ours (Tyler
# playing, or his launcher open), touch nothing under %LOCALAPPDATA%\Swofty or the game folder. Our own runs never
# have the launcher open, and they call this only before launch or after their game has exited.
if (Get-Process F1_25, swofty-launcher -ErrorAction SilentlyContinue) {
    throw 'SKIPPED: F1 25 or the Swofty Launcher is running (not ours); no snapshot taken, so no run may start'
}
if (-not $SteamApp) { $SteamApp = & (Join-Path $PSScriptRoot 'find_steam_app.ps1') }
$h = [ordered]@{}
foreach ($f in Get-ChildItem (Join-Path $SteamApp 'remote') -File) {
    $h["file $($f.Name)"] = "{0} {1} {2}" -f $f.Length, $f.LastWriteTimeUtc.Ticks, (Get-FileHash $f.FullName -Algorithm SHA256).Hash
}
$rc = Get-Content (Join-Path $SteamApp 'remotecache.vdf') -Raw
foreach ($m in [regex]::Matches($rc, '"([^"]+)"\s*\{([^{}]*)\}')) {
    $fields = foreach ($k in 'size', 'sha', 'localtime') { [regex]::Match($m.Groups[2].Value, "`"$k`"\s*`"([^`"]*)`"").Groups[1].Value }
    if ($fields[1]) { $h["steam $($m.Groups[1].Value)"] = $fields -join ' ' }
}
if (Test-Path $LauncherSaves) {
    foreach ($d in Get-ChildItem $LauncherSaves -Directory | Where-Object { $_.Name -notlike 'test-*' -and $_.Name -notlike 'verve-*' } | Sort-Object Name) {
        foreach ($f in Get-ChildItem $d.FullName -File -Recurse -Force | Sort-Object FullName) {
            $h["launcher $($d.Name)\$($f.FullName.Substring($d.FullName.Length + 1))"] =
                "{0} {1} {2}" -f $f.Length, $f.LastWriteTimeUtc.Ticks, (Get-FileHash $f.FullName -Algorithm SHA256).Hash
        }
    }
}
# Addon data stored for those same profiles (addon-profiles\<addon>\<profile>). On 1.9.x `swofty test` swaps addon
# storage under the ACTIVE profile's name, so a run can reach Tyler's addon data even on an isolated profile.
$addonStore = Join-Path (Split-Path $LauncherSaves) 'addon-profiles'
if (Test-Path $addonStore) {
    foreach ($a in Get-ChildItem $addonStore -Directory | Sort-Object Name) {
        foreach ($d in Get-ChildItem $a.FullName -Directory -Force | Where-Object { $_.Name -notlike '.*' -and $_.Name -notlike 'test-*' -and $_.Name -notlike 'verve-*' } | Sort-Object Name) {
            foreach ($f in Get-ChildItem $d.FullName -File -Recurse -Force | Sort-Object FullName) {
                $h["addon $($a.Name)\$($d.Name)\$($f.FullName.Substring($d.FullName.Length + 1))"] =
                    "{0} {1} {2}" -f $f.Length, $f.LastWriteTimeUtc.Ticks, (Get-FileHash $f.FullName -Algorithm SHA256).Hash
            }
        }
    }
}
# Live addon data (addon-storage\<id>\) while the addon's .current names a profile that isn't ours: that's Tyler's
# live data (addon_storage.rs Holder::Storage). Hashed, never touched.
$live = Join-Path (Split-Path $LauncherSaves) 'addon-storage'
if (Test-Path $live) {
    foreach ($a in Get-ChildItem $live -Directory | Sort-Object Name) {
        $cur = Join-Path $addonStore "$($a.Name)\.current"
        $label = if (Test-Path $cur) { (Get-Content $cur -Raw).Trim() } else { '' }
        if ($label -like 'verve-*' -or $label -like 'test-*') { continue }
        foreach ($f in Get-ChildItem $a.FullName -File -Recurse -Force | Sort-Object FullName) {
            $h["live $($a.Name)\$($f.FullName.Substring($a.FullName.Length + 1))"] =
                "{0} {1} {2}" -f $f.Length, $f.LastWriteTimeUtc.Ticks, (Get-FileHash $f.FullName -Algorithm SHA256).Hash
        }
    }
}
# hardware_settings_config.xml, treated like a save (supervisor, 2026-11-16): Tyler's play shares it (graphics,
# display, UDP). Values only, one entry per attribute (`hw <element path>@<attribute>`), so a rewrite with identical
# values is no difference, and a changed value names its key with the old and new values in the guard's diff.
. (Join-Path $PSScriptRoot 'hw_settings.ps1')
if (Test-Path $HwFile) {
    foreach ($e in (Get-HwValues $HwFile).GetEnumerator()) { $h[$e.Key] = $e.Value }
}
$h
