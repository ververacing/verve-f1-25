<#
Run one B-0015 race (#100 v4): per-driver ai_driver_config.blocking.max_blocking_distance crossover, 45 vs 5.
One call per race, so control comes back between races (docs/process.md).

Usage:
    powershell -File tools/b0015_run.ps1 -Race <n> -Batch runs/<date>-B-0015 [-WindowOverride 06:00]

ODD races = order a (verve.b0015a: G1 = 45, G2 = 5). EVEN races = order b (verve.b0015b: swapped). Profile verve-test on
harness\sessions\gp_menu_full_skip.plan (Amendment-4 setup of #71). After the race, race_feel writes <race>\race_feel\.
Refusals and exit codes as tools/b0016_run.ps1. Score with tools/b0015_check.py after the last race only.
#>
param(
    [Parameter(Mandatory)] [int] $Race,
    [Parameter(Mandatory)] [string] $Batch,
    [int] $RaceMinutes = 17,
    [string] $WindowOverride = '',   # 'HH:mm' PT, end of a one-off window granted by Tyler (docs/process.md)
    [string] $ExpProfile = 'verve-test',
    [switch] $SidestepDryRun
)
$ErrorActionPreference = 'Stop'
$tz = [TimeZoneInfo]::FindSystemTimeZoneById('Pacific Standard Time')
$now = [TimeZoneInfo]::ConvertTime((Get-Date), $tz)
$wrapups = @($now.Date.AddHours(5).AddMinutes(45), $now.Date.AddHours(16).AddMinutes(45), $now.Date.AddDays(1).AddHours(5).AddMinutes(45))
$inWindow = $now.Hour -lt 6 -or ($now.Hour -ge 9 -and $now.Hour -lt 17)
if ($WindowOverride) {
    $end = $now.Date + [TimeSpan]::Parse($WindowOverride)
    if ($end -le $now) { $end = $end.AddDays(1) }
    if ($now -lt $end) {
        $inWindow = $true
        # the override replaces every wrap-up before its own end (the windows join)
        $wrapups = @($end.AddMinutes(-15)) + @($wrapups | Where-Object { $_ -gt $end.AddMinutes(-15) }) | Sort-Object
    }
}
if (-not $inWindow) { "race ${Race}: it's $($now.ToString('HH:mm')) PT, outside the testing windows; not launching"; exit 8 }
$next = $wrapups | Where-Object { $_ -gt $now } | Select-Object -First 1
$need = if (($Race % 2) -eq 1) { 2 * $RaceMinutes } else { $RaceMinutes }   # complete pairs only
if ($now.AddMinutes($need + 15) -gt $next) { "race ${Race}: it's $($now.ToString('HH:mm')) PT, and $need min of racing wouldn't finish 15 min before the $($next.ToString('HH:mm')) wrap-up; not launching"; exit 8 }
if (Get-Process F1_25 -ErrorAction SilentlyContinue) { "race ${Race}: a game is running that this batch didn't start; not launching"; exit 9 }
if (Get-Process swofty-launcher -ErrorAction SilentlyContinue) { "race ${Race}: the Swofty Launcher is open; not launching"; exit 9 }
$cleanup = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'cleanup_test_profiles.ps1')
if ($LASTEXITCODE -ne 0) { "race ${Race}: test profiles are left over; not launching"; $cleanup | ForEach-Object { "  $_" }; exit 10 }

$addon = if (($Race % 2) -eq 1) { 'verve.b0015a' } else { 'verve.b0015b' }
$arm = "order $(if (($Race % 2) -eq 1) { 'a' } else { 'b' }) ($addon)"
$plan = 'harness\sessions\gp_menu_full_skip.plan'
$out = Join-Path $Batch "race_$Race"
if (Test-Path $out) {
    $aside = Join-Path $Batch 'invalid'
    New-Item -ItemType Directory -Force $aside | Out-Null
    $k = 1
    while (Test-Path (Join-Path $aside "race_${Race}_$k")) { $k++ }
    Move-Item $out (Join-Path $aside "race_${Race}_$k")
    "race ${Race}: earlier attempt moved to invalid\race_${Race}_$k"
}
New-Item -ItemType Directory -Force $out | Out-Null
if ($WindowOverride) { Set-Content (Join-Path $out 'window_override.txt') -Value "one-off window to $WindowOverride PT (docs/process.md override log)" -Encoding utf8 }
Set-Content (Join-Path $out 'arm.txt') -Value $arm -Encoding utf8
"race $Race at $($now.ToString('HH:mm:ss')) PT: arm $arm, $plan"
$shellArgs = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $PSScriptRoot 'sandbox_shell.ps1'), '-Fixture', 'tyler-profile-20261031',
    '-ExpProfile', $ExpProfile, '-Plan', $plan, '-Udp',
    '-Channels', 'default,RaceStarts:info,LAPTIMES:info,CUTSCENE_MANAGER:info,CUTSCENE_PODIUM:info', '-Out', $out)
$shellArgs += @('-Addon', $addon)
if ($SidestepDryRun) { $shellArgs += '-SidestepDryRun' }
powershell @shellArgs |
    ForEach-Object { $_ -replace [regex]::Escape($env:USERPROFILE), '%USERPROFILE%' } | Where-Object { $_ -match 'EXPECT|intro|ABORT|^result:|^saves |SAVES CHANGED|NO RESULT|udp recording' }
$code = $LASTEXITCODE
"guard exit: $code"

# race_feel per race (the primaries come from it): the capture stays in %TEMP%\verve-udp\shell-*; keep a copy in raw\
# (gitignored) and write race_feel.csv / race_feel_summary.json into <race>\race_feel\
$t0 = [TimeZoneInfo]::ConvertTime($now, $tz, [TimeZoneInfo]::Local)
$bin = Get-ChildItem (Join-Path $env:TEMP 'verve-udp') -Directory -Filter 'shell-*' -ErrorAction SilentlyContinue |
    Where-Object { $_.CreationTime -ge $t0.AddSeconds(-5) } | Sort-Object CreationTime -Descending | Select-Object -First 1 |
    ForEach-Object { Join-Path $_.FullName 'udp.bin' }
if ($bin -and (Test-Path $bin)) {
    New-Item -ItemType Directory -Force (Join-Path $out 'raw') | Out-Null
    Copy-Item $bin (Join-Path $out 'raw\udp.bin') -Force
    $ErrorActionPreference = 'Continue'
    & python -I (Join-Path $PSScriptRoot 'race_feel.py') (Join-Path $out 'raw\udp.bin') --out (Join-Path $out 'race_feel') *> (Join-Path $out 'race_feel_stdout.txt')
    "race_feel exit: $LASTEXITCODE"
    $ErrorActionPreference = 'Stop'
} else { 'race_feel: no UDP capture found for this race' }
if ($code -eq 5) { 'SAVES CHANGED: stop the batch and tell Tyler'; exit 5 }
exit $code
