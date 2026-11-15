<#
Sidestep for the Swofty 1.9.51 addon-storage bug (docs/upstream/swofty_addon_storage_lock.md): addon_storage.rs
finish() renames an existing addon-profiles\<id>\<label> to .saved-old, then remove_tree(.saved-old) fails with
os error 32, and the wrapper (or `swofty restore`) aborts. With no target folder there's no rename and no aside, so
moving EMPTY targets out of the way first lets it through. Swofty re-creates them empty.

Supervisor's standing authorisation (2026-11-14): EMPTY folders only, including empty ones under tyler's name.
Anything that holds a file stays where it is, and the run stops (exit 1). Data is never moved.

Usage (run right before a swofty launch or restore, with no swofty or F1 25 process running):
    powershell -File tools/storage_sidestep.ps1 -ExpProfile verve-test [-Addon a,b] -Log <file>
    powershell -File tools/storage_sidestep.ps1 -Ids dromodf.skip-cutscenes,teamsimplified.mods -Log <file>

For each addon (the profile's enabled addons plus -Addon, or -Ids): delete an empty .saved-old, and move
addon-profiles\<id>\<.current label> and addon-profiles\<id>\<active profile> to
Documents\verve-f1-25-recovery\<stamp>\<id>\<label> when they hold 0 files. -DryRun logs those moves without
making them (the checks that refuse still apply). A .saving / .saving.ready / .incoming* /
.outgoing entry means Swofty is mid-swap: refuse. Exit 0 = done (or nothing to do), 1 = refused.
#>
param(
    [string] $ExpProfile = '',
    [string[]] $Addon = @(),
    [string[]] $Ids = @(),
    [string] $Log = '',
    [string] $Recovery = (Join-Path $env:USERPROFILE 'Documents\verve-f1-25-recovery'),
    [switch] $DryRun   # log what it WOULD delete or move, change nothing; the refuse checks stay live
)
$ErrorActionPreference = 'Stop'
# Standing rule (supervisor, 2026-11-14): when F1 25 or the Swofty Launcher is running and it isn't ours (Tyler
# playing, or his launcher open), touch nothing under %LOCALAPPDATA%\Swofty or the game folder. Our own runs never
# have the launcher open, and they call this only before launch or after their game has exited.
if (Get-Process F1_25, swofty-launcher -ErrorAction SilentlyContinue) {
    "REFUSE: F1 25 or the Swofty Launcher is running (not ours); nothing checked or moved"; exit 1
}
$data = Join-Path $env:LOCALAPPDATA 'Swofty'
$store = Join-Path $data 'addon-profiles'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
function L([string] $s) {
    $s = $s.Replace($env:USERPROFILE, '%USERPROFILE%')
    $s
    if ($Log) { Add-Content $Log $s -Encoding utf8 }
}
function Split([string[]] $x) { @($x | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ }) }

if (Get-Process | Where-Object { $_.Name -match '^F1_25|swofty' }) { L 'REFUSE: a swofty or F1 25 process is running'; exit 1 }
$active = (Get-Content (Join-Path $data 'config.json') -Raw | ConvertFrom-Json).active_profile
$list = Split $Ids
if ($ExpProfile) {
    $prof = Get-Content (Join-Path $data "profiles\$ExpProfile.json") -Raw | ConvertFrom-Json
    $list += @($prof.addons | Where-Object { $_.enabled } | ForEach-Object { $_.id })
}
$list = @($list + (Split $Addon) | Select-Object -Unique)
L "storage sidestep ${stamp}: active profile $active; addons $($list -join ', ')"

# check everything first, move nothing until all of it is known to be empty
$moves = @(); $deletes = @(); $refuse = @()
foreach ($id in $list) {
    $base = Join-Path $store $id
    if (-not (Test-Path $base)) { continue }
    foreach ($e in Get-ChildItem $base -Force | Where-Object { $_.Name -match '^\.(saving|incoming|outgoing)' }) { $refuse += "$id\$($e.Name) exists (Swofty mid-swap)" }
    $old = Join-Path $base '.saved-old'
    if (Test-Path $old) {
        if (@(Get-ChildItem $old -Recurse -Force).Count) { $refuse += "$id\.saved-old holds items" } else { $deletes += $old }
    }
    $labels = @($active)
    $cur = Join-Path $base '.current'
    if (Test-Path $cur) { $labels += (Get-Content $cur -Raw).Trim() }
    foreach ($label in $labels | Where-Object { $_ } | Select-Object -Unique) {
        $t = Join-Path $base $label
        if (-not (Test-Path $t)) { continue }
        $n = @(Get-ChildItem $t -Recurse -File -Force).Count
        if ($n) { $refuse += "$id\$label holds $n file(s)" } else { $moves += [pscustomobject]@{ id = $id; label = $label; path = $t } }
    }
}
if ($refuse) { $refuse | ForEach-Object { L "REFUSE: $_" }; L 'nothing moved'; exit 1 }
if ($DryRun) {
    foreach ($d in $deletes) { L "DRY RUN: would delete empty $(Split-Path (Split-Path $d) -Leaf)\.saved-old" }
    foreach ($m in $moves) { L "DRY RUN: would move empty $($m.id)\$($m.label)" }
    if (-not ($deletes -or $moves)) { L 'DRY RUN: nothing to move' }
    exit 0
}
foreach ($d in $deletes) { [IO.Directory]::Delete($d); L "deleted empty $(Split-Path (Split-Path $d) -Leaf)\.saved-old" }
foreach ($m in $moves) {
    $dest = Join-Path $Recovery "$stamp\$($m.id)"
    New-Item -ItemType Directory -Force $dest | Out-Null
    Move-Item $m.path (Join-Path $dest $m.label)
    L "moved empty $($m.id)\$($m.label) -> verve-f1-25-recovery\$stamp\$($m.id)\$($m.label)"
}
if (-not ($deletes -or $moves)) { L 'nothing to move' }
exit 0
