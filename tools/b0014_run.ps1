<#
Run one B-0014 race (#71). One call per race, so control comes back between races (docs/process.md).

Usage:
    powershell -File tools/b0014_run.ps1 -Race <n> -Batch runs/<date>-B-0014

Odd races use verve.b0014a and the plan with a press during the grid rundown (#65); even races verve.b0014b and the plain
plan. Refuses to launch if a game is running that it didn't start, or if a race can't finish 15 minutes before the next
wrap-up (05:45 and 16:45 PT). Exits 8 and 9 for those, 5 if saves changed.
A race takes about 17 min. Check validity afterwards with tools/b0014_check.py.
#>
param(
    [Parameter(Mandatory)] [int] $Race,
    [Parameter(Mandatory)] [string] $Batch,
    [int] $RaceMinutes = 17
)
$ErrorActionPreference = 'Stop'
$tz = [TimeZoneInfo]::FindSystemTimeZoneById('Pacific Standard Time')
$now = [TimeZoneInfo]::ConvertTime((Get-Date), $tz)
$wrapups = @($now.Date.AddHours(5).AddMinutes(45), $now.Date.AddHours(16).AddMinutes(45), $now.Date.AddDays(1).AddHours(5).AddMinutes(45))
$next = $wrapups | Where-Object { $_ -gt $now } | Select-Object -First 1
if ($now.AddMinutes($RaceMinutes + 15) -gt $next) { "race ${Race}: it's $($now.ToString('HH:mm')) PT, and it wouldn't finish 15 min before the $($next.ToString('HH:mm')) wrap-up; not launching"; exit 8 }
if (Get-Process F1_25 -ErrorAction SilentlyContinue) { "race ${Race}: a game is running that this batch didn't start; not launching"; exit 9 }

$odd = ($Race % 2) -eq 1
$addon = if ($odd) { 'verve.b0014a' } else { 'verve.b0014b' }
$plan = if ($odd) { 'harness\sessions\gp_menu_full_press.plan' } else { 'harness\sessions\gp_menu_full.plan' }
$out = Join-Path $Batch "race_$Race"
New-Item -ItemType Directory -Force $out | Out-Null
"race $Race at $($now.ToString('HH:mm:ss')) PT: $addon, $plan"
powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'sandbox_shell.ps1') -Fixture tyler-profile-20261031 -Plan $plan -Addon $addon -Udp `
    -Channels 'default,RaceStarts:info,LAPTIMES:info,CUTSCENE_MANAGER:info,CUTSCENE_PODIUM:info' -Out $out |
    ForEach-Object { $_ -replace [regex]::Escape($env:USERPROFILE), '%USERPROFILE%' } | Where-Object { $_ -match 'EXPECT|intro|ABORT|^result:|^saves |SAVES CHANGED|NO RESULT|udp recording' }
$code = $LASTEXITCODE
"guard exit: $code"
if ($code -eq 5) { 'SAVES CHANGED: stop the batch and tell Tyler'; exit 5 }
exit $code
