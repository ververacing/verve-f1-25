<#
Delete the throwaway `test-*` launcher profiles that `swofty test run` / `test shell` / `test session` leave behind.
Every run script calls this when it ends, and tools/preflight.ps1 fails if any test-* profile is still there after it.

Usage:
    powershell -File tools/cleanup_test_profiles.ps1           # exit 0 = none left, 1 = some couldn't be deleted

Why the extra steps: `swofty profile delete` fails on this PC with "being used by another process" (os error 32) on
`saves\<profile>` (1.9.51) or `cache\overlay\<profile>` (1.8.4), while a plain delete of those folders works. So: clear
the profile's overlay cache, remove its launcher save folder if it holds no files (it's an empty `remote\` in every
leftover seen so far), then delete the profile. A save folder that holds any file is never deleted: the profile is
left in place and reported, so a person can look first. The career vault is never touched.

Only profiles named test-* are touched, and never the active one. Tyler's profiles, verve profiles and `vanilla` are
outside the pattern.

It also clears a stale game lock: a killed `swofty test` leaves `%LOCALAPPDATA%\swofty-game.lock.d` behind, and the
next run then fails with "the game was not free". The lock is deleted only when no F1_25 or swofty process is running.
#>
param([string] $Swofty = "$env:LOCALAPPDATA\Programs\SwoftyLauncher\bin\swofty.exe")
$ErrorActionPreference = 'Stop'
$data = Join-Path $env:LOCALAPPDATA 'Swofty'
$lock = Join-Path $env:LOCALAPPDATA 'swofty-game.lock.d'
if (Test-Path $lock) {
    $busy = @(Get-Process | Where-Object { $_.Name -match '^F1_25|swofty' })
    $owner = Get-Content (Join-Path $lock 'owner') -ErrorAction SilentlyContinue
    if ($busy.Count -eq 0) { Remove-Item -Recurse -Force $lock -Confirm:$false; "cleared stale game lock ($owner)" }
    else { "game lock held by a running process ($owner); left alone" }
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
    # its launcher save, and its per-addon folders (addon-profiles\<addon>\<profile>), which lock the same way
    $dirs = @(Join-Path $data "saves\$name") + @(Get-ChildItem (Join-Path $data 'addon-profiles') -Directory -ErrorAction SilentlyContinue |
        ForEach-Object { Join-Path $_.FullName $name } | Where-Object { Test-Path $_ })
    $full = @($dirs | Where-Object { (Test-Path $_) -and @(Get-ChildItem $_ -Recurse -File -Force).Count })
    if ($full.Count) { "kept $name`: holds files ($($full -join '; ')); look before deleting"; $left += $name; continue }
    foreach ($dir in $dirs) {
        for ($i = 1; $i -le 3; $i++) { try { if (Remove-EmptyTree $dir) { break } } catch { Start-Sleep -Seconds (2 * $i) } }
    }
    $ErrorActionPreference = 'Continue'   # PS 5.1 turns a native program's stderr into a terminating error under Stop
    $msg = & $Swofty profile delete $name --yes 2>&1 | ForEach-Object { "$_" }
    $code = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    if ($code -eq 0) { "deleted $name" } else { "could not delete $name (exit $code): $($msg | Select-Object -Last 1)"; $left += $name }
}
"active profile: $active"
if ($left.Count) { "test profiles left: $($left -join ', ')"; exit 1 }
exit 0
