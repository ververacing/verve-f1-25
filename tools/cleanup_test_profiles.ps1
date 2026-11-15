<#
Delete the throwaway `test-*` launcher profiles that `swofty test run` / `test shell` / `test session` leave behind.
Every run script calls this when it ends, and tools/preflight.ps1 fails if any test-* profile is still there after it.

Usage:
    powershell -File tools/cleanup_test_profiles.ps1           # exit 0 = none left, 1 = some couldn't be deleted

Why the extra steps: `swofty profile delete` fails on this PC with "being used by another process" (os error 32) on
`saves\<profile>` (1.9.51) or `cache\overlay\<profile>` (1.8.4), while a plain delete of those folders works. So: clear
the profile's overlay cache, remove its launcher save folder if it holds no files (it's an empty `remote\` in every
leftover seen so far), then delete the profile.

A test profile copied from verve-test (launcher saves on, empty store) gets Tyler's Steam save imported at its first
Play (Swofty's doing; 2026-11-14). Supervisor's ruling A: such a save is deleted ONLY if EVERY file in it is sha256-
identical to the same-named file in Tyler's current Steam remote\ (a pure duplicate), together with that profile's
career-vault\launcher-test-*\ folder; each deletion is logged with names and hashes, never content. Any other save
that holds files is never deleted: the profile is left in place and reported. Other career-vault folders are never
touched.

-Log appends the report to a file (the run folder's cleanup.txt).

Only profiles named test-* are touched, and never the active one. Tyler's profiles, verve profiles and `vanilla` are
outside the pattern.

It also clears a stale game lock: a killed `swofty test` leaves `%LOCALAPPDATA%\swofty-game.lock.d` behind, and the
next run then fails with "the game was not free". The lock is deleted only when no F1_25 or swofty process is running.
#>
param(
    [string] $Swofty = "$env:LOCALAPPDATA\Programs\SwoftyLauncher\bin\swofty.exe",
    [string] $Log = ''
)
$ErrorActionPreference = 'Stop'
# Standing rule (supervisor, 2026-11-14): when F1 25 or the Swofty Launcher is running and it isn't ours (Tyler
# playing, or his launcher open), touch nothing under %LOCALAPPDATA%\Swofty or the game folder. Our own runs never
# have the launcher open, and they call this only before launch or after their game has exited.
if (Get-Process F1_25, swofty-launcher -ErrorAction SilentlyContinue) {
    "SKIPPED: F1 25 or the Swofty Launcher is running (not ours); no profile, lock or vault touched"; exit 1
}
$data = Join-Path $env:LOCALAPPDATA 'Swofty'
$steamRemote = Join-Path (& (Join-Path $PSScriptRoot 'find_steam_app.ps1')) 'remote'
function Out([string] $s) { $s; if ($Log) { Add-Content $Log $s -Encoding utf8 } }
function Remove-Duplicate([string] $name) {
    # ruling A: the test profile's launcher save goes only if every file is a byte-identical twin of Tyler's Steam file
    $save = Join-Path $data "saves\$name"
    $files = @(Get-ChildItem $save -Recurse -File -Force -ErrorAction SilentlyContinue)
    if (-not $files.Count) { return $true }
    $rows = foreach ($f in $files) {
        $twin = Join-Path $steamRemote $f.Name
        $h = (Get-FileHash $f.FullName -Algorithm SHA256).Hash
        $t = if (Test-Path $twin) { (Get-FileHash $twin -Algorithm SHA256).Hash } else { '' }
        [pscustomobject]@{ name = $f.Name; sha256 = $h; same = ($t -and $t -eq $h) }
    }
    if (@($rows | Where-Object { -not $_.same }).Count) {
        Out "kept $name`: its launcher save has $(@($rows | Where-Object { -not $_.same }).Count) file(s) that aren't identical to Tyler's Steam files; look before deleting"
        return $false
    }
    Remove-Item -Recurse -Force $save -Confirm:$false
    foreach ($r in $rows) { Out "deleted duplicate of Tyler's Steam file in $name`: $($r.name) sha256 $($r.sha256)" }
    $vault = Join-Path $data "career-vault\launcher-$name"
    if ((Split-Path $vault -Leaf) -like 'launcher-test-*' -and (Test-Path $vault)) {
        $n = @(Get-ChildItem $vault -Recurse -File -Force).Count
        Remove-Item -Recurse -Force $vault -Confirm:$false
        Out "deleted career-vault\launcher-$name ($n file(s))"
    }
    return $true
}
$lock = Join-Path $env:LOCALAPPDATA 'swofty-game.lock.d'
if (Test-Path $lock) {
    $busy = @(Get-Process | Where-Object { $_.Name -match '^F1_25|swofty' })
    $owner = Get-Content (Join-Path $lock 'owner') -ErrorAction SilentlyContinue
    if ($busy.Count -eq 0) { Remove-Item -Recurse -Force $lock -Confirm:$false; Out "cleared stale game lock ($owner)" }
    else { Out "game lock held by a running process ($owner); left alone" }
}

function Remove-EmptyTree([string] $dir) {
    # deletes $dir only if no file exists anywhere under it; returns $true if it's gone
    if (-not (Test-Path $dir)) { return $true }
    if (@(Get-ChildItem $dir -Recurse -File -Force -ErrorAction SilentlyContinue).Count) { return $false }
    foreach ($d in @(Get-ChildItem $dir -Recurse -Directory -Force) | Sort-Object { $_.FullName.Length } -Descending) {
        [IO.Directory]::Delete($d.FullName)
    }
    [IO.Directory]::Delete($dir)
    $true
}

$list = & $Swofty profile list
$active = ($list | Where-Object { $_ -match '\sactive\s*$' } | ForEach-Object { ($_ -split '\s+')[0] })
$left = @()
foreach ($name in ($list | ForEach-Object { ($_ -split '\s+')[0] } | Where-Object { $_ -like 'test-*' -and $_ -ne $active })) {
    $cache = Join-Path $data "cache\overlay\$name"
    for ($i = 1; $i -le 5 -and (Test-Path $cache); $i++) {
        try { Remove-Item -Recurse -Force $cache -Confirm:$false -ErrorAction Stop } catch { Start-Sleep -Seconds (2 * $i) }
    }
    if (-not (Remove-Duplicate $name)) { $left += $name; continue }
    # its launcher save, and its per-addon folders (addon-profiles\<addon>\<profile>), which lock the same way
    $dirs = @(Join-Path $data "saves\$name") + @(Get-ChildItem (Join-Path $data 'addon-profiles') -Directory -ErrorAction SilentlyContinue |
        ForEach-Object { Join-Path $_.FullName $name } | Where-Object { Test-Path $_ })
    $full = @($dirs | Where-Object { (Test-Path $_) -and @(Get-ChildItem $_ -Recurse -File -Force).Count })
    if ($full.Count) { Out "kept $name`: holds files ($($full -join '; ')); look before deleting"; $left += $name; continue }
    foreach ($dir in $dirs) {
        for ($i = 1; $i -le 3; $i++) { try { if (Remove-EmptyTree $dir) { break } } catch { Start-Sleep -Seconds (2 * $i) } }
    }
    $ErrorActionPreference = 'Continue'   # PS 5.1 turns a native program's stderr into a terminating error under Stop
    $msg = & $Swofty profile delete $name --yes 2>&1 | ForEach-Object { "$_" }
    $code = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    if ($code -eq 0) { Out "deleted $name" } else { Out "could not delete $name (exit $code): $($msg | Select-Object -Last 1)"; $left += $name }
}
Out "active profile: $active"
if ($left.Count) { Out "test profiles left: $($left -join ', ')"; exit 1 }
exit 0
