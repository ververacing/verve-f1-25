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
$h
