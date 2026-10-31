<#
Delete the throwaway `test-*` launcher profiles `swofty test run` leaves behind, after every batch.

Usage:
    powershell -File tools/cleanup_test_profiles.ps1

`swofty test run` and `swofty profile delete` both fail on this PC with "cache/overlay/<profile>: being used by
another process", while a plain Remove-Item of that cache folder works. So: clear the profile's overlay cache, then
delete the profile. The active profile is never touched.

It also clears a stale game lock: a killed `swofty test` leaves `%LOCALAPPDATA%\swofty-game.lock.d` behind, and the
next run then fails with "the game was not free". The lock is deleted only when no F1_25 or swofty process is running.
#>
param([string] $Swofty = "$env:LOCALAPPDATA\Programs\SwoftyLauncher\bin\swofty.exe")
$ErrorActionPreference = 'Stop'
$lock = Join-Path $env:LOCALAPPDATA 'swofty-game.lock.d'
if (Test-Path $lock) {
    $busy = @(Get-Process | Where-Object { $_.Name -match '^F1_25|swofty' })
    $owner = Get-Content (Join-Path $lock 'owner') -ErrorAction SilentlyContinue
    if ($busy.Count -eq 0) { Remove-Item -Recurse -Force $lock -Confirm:$false; "cleared stale game lock ($owner)" }
    else { "game lock held by a running process ($owner); left alone" }
}
$list = & $Swofty profile list
$active = ($list | Where-Object { $_ -match '\sactive\s*$' } | ForEach-Object { ($_ -split '\s+')[0] })
foreach ($name in ($list | ForEach-Object { ($_ -split '\s+')[0] } | Where-Object { $_ -like 'test-*' -and $_ -ne $active })) {
    $cache = Join-Path $env:LOCALAPPDATA "Swofty\cache\overlay\$name"
    for ($i = 1; $i -le 5 -and (Test-Path $cache); $i++) {
        try { Remove-Item -Recurse -Force $cache -Confirm:$false -ErrorAction Stop } catch { Start-Sleep -Seconds (2 * $i) }
    }
    & $Swofty profile delete $name --yes | Out-Null
    if ($LASTEXITCODE -eq 0) { "deleted $name" } else { "could not delete $name (exit $LASTEXITCODE)" }
}
"active profile: $active"
