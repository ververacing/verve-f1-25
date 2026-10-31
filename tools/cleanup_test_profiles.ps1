<#
Delete the throwaway `test-*` launcher profiles `swofty test run` leaves behind, after every batch.

Usage:
    powershell -File tools/cleanup_test_profiles.ps1

`swofty test run` and `swofty profile delete` both fail on this PC with "cache/overlay/<profile>: being used by
another process", while a plain Remove-Item of that cache folder works. So: clear the profile's overlay cache, then
delete the profile. The active profile is never touched.
#>
param([string] $Swofty = "$env:LOCALAPPDATA\Programs\SwoftyLauncher\bin\swofty.exe")
$ErrorActionPreference = 'Stop'
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
