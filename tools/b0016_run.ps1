<#
Run one B-0016 race (#101): stock vs swofty.lap1-ai. One call per race, so control comes back between races
(docs/process.md).

Usage:
    powershell -File tools/b0016_run.ps1 -Race <n> -Batch runs/<date>-B-0016 [-WindowOverride 06:00]

ODD races = arm A = stock (verve-test as is). EVEN races = arm B = verve-test + swofty.lap1-ai (--addon; no settings).
Both on harness\sessions\gp_menu_full_skip.plan (Amendment-4 setup of #71). After the race, <race>\lap1ai.txt records
lap1-ai's version (addons.json) and every [lap1-ai] loader.log line, as #101's per-race logging asks.

Same refusals as tools/b0014_run.ps1: outside the testing windows (or a -WindowOverride), a game running that it didn't
start, a race (an A race with its B partner) that can't finish 15 min before the next wrap-up, or test-* profiles left
over. Exits 8, 9, 10 for those, 5 if saves changed. Rerunning a race moves the earlier attempt to <Batch>\invalid\.
#>
param(
    [Parameter(Mandatory)] [int] $Race,
    [Parameter(Mandatory)] [string] $Batch,
    [int] $RaceMinutes = 17,
    [string] $WindowOverride = '',   # 'HH:mm' PT, end of a one-off window granted by Tyler (docs/process.md)
    [string] $ExpProfile = 'verve-test',
    [switch] $SidestepDryRun,
    [string] $Plan = 'harness\sessions\gp_menu_full_skip.plan',   # #118: the dry-locked plan for B-0016b / B-0018
    [switch] $StockOnly,       # B-0018 (#120): every race is stock (arm A), no addon
    [switch] $LockedWeather    # #118: weather.txt from weather_check --locked (the checkers then require LOCKED)
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
# PAUSE (tools/pause.ps1): no launch while paused; a pause-at that this race wouldn't finish before pauses now
$pauseFlag = Join-Path $env:LOCALAPPDATA 'verve-f1-25\state\paused.txt'
if (Test-Path $pauseFlag) { "race ${Race}: paused ($((Get-Content $pauseFlag -TotalCount 1))); not launching"; exit 12 }
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'pause.ps1') -IfDue -NextMinutes ($RaceMinutes + 5)
if ($LASTEXITCODE -ne 2) { "race ${Race}: pause-at reached; paused instead of launching"; exit 12 }
if (Get-Process F1_25 -ErrorAction SilentlyContinue) { "race ${Race}: a game is running that this batch didn't start; not launching"; exit 9 }
if (Get-Process swofty-launcher -ErrorAction SilentlyContinue) { "race ${Race}: the Swofty Launcher is open; not launching"; exit 9 }
$cleanup = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'cleanup_test_profiles.ps1')
if ($LASTEXITCODE -ne 0) { "race ${Race}: test profiles are left over; not launching"; $cleanup | ForEach-Object { "  $_" }; exit 10 }

$armB = (($Race % 2) -eq 0) -and -not $StockOnly
$arm = if ($armB) { 'B (swofty.lap1-ai)' } else { 'A (stock)' }
if (-not (Test-Path $Plan)) { "race ${Race}: no plan $Plan; not launching"; exit 13 }
$plan = $Plan
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
# the launcher updates itself (2026-11-16: B-0015 and B-0016 each straddled updates): record its version every race
$launcherExe = Join-Path $env:LOCALAPPDATA 'Programs\SwoftyLauncher\bin\swofty-launcher.exe'
$launcherBefore = if (Test-Path $launcherExe) { (Get-Item $launcherExe).VersionInfo.ProductVersion } else { 'MISSING' }
"race $Race at $($now.ToString('HH:mm:ss')) PT: arm $arm, $plan"
$shellArgs = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $PSScriptRoot 'sandbox_shell.ps1'), '-Fixture', 'tyler-profile-20261031',
    '-ExpProfile', $ExpProfile, '-Plan', $plan, '-Udp',
    '-Channels', 'default,RaceStarts:info,LAPTIMES:info,CUTSCENE_MANAGER:info,CUTSCENE_PODIUM:info', '-Out', $out)
if ($armB) { $shellArgs += @('-Addon', 'swofty.lap1-ai') }   # only when set: an empty -Addon through -File fails
if ($SidestepDryRun) { $shellArgs += '-SidestepDryRun' }
powershell @shellArgs |
    ForEach-Object { $_ -replace [regex]::Escape($env:USERPROFILE), '%USERPROFILE%' } | Where-Object { $_ -match 'EXPECT|intro|ABORT|^result:|^saves |SAVES CHANGED|NO RESULT|udp recording' }
$code = $LASTEXITCODE
"guard exit: $code"

# #101 per-race logging: lap1-ai's version and its loader.log lines
$lines = @()
$aj = Join-Path $out 'addons.json'
$lines += if (Test-Path $aj) { "addons.json: $((Get-Content $aj -Raw) -replace '\s+', ' ')" } else { 'addons.json: MISSING' }
$man = "$env:LOCALAPPDATA\Swofty\addons\swofty.lap1-ai\swofty.json"
# no reads under Swofty while a game or Swofty process is up (incident 2026-11-15): the version is read later instead
$busy = @(Get-Process F1_25, swofty, swofty-launcher -ErrorAction SilentlyContinue).Count -gt 0
$lines += if ($busy) { 'installed swofty.lap1-ai version: not read (a game or Swofty process is running; read it at the next pre-flight)' } elseif (Test-Path $man) { "installed swofty.lap1-ai version: $((Get-Content $man -Raw | ConvertFrom-Json).version)" } else { 'installed swofty.lap1-ai: MISSING' }
$ll = Join-Path $out 'raw\loader.log'
if (Test-Path $ll) {
    $l1 = @(Get-Content $ll | Where-Object { $_ -match 'lap1-ai|lap1_ai' })
    $lines += "loader.log lap1-ai lines: $($l1.Count)"
    $lines += $l1 | ForEach-Object { $_ -replace [regex]::Escape($env:USERPROFILE), '%USERPROFILE%' }
} else { $lines += 'loader.log: MISSING' }
$lines | Set-Content (Join-Path $out 'lap1ai.txt') -Encoding utf8
"lap1ai.txt: $($lines[2])"

# launcher.txt: the launcher's file version before launch, and the version the game's main menu reported
# ("[main-menu] state: Swofty Launcher X" in loader.log). A change from the previous race's launcher.txt prints
# LAUNCHER CHANGED, to be flagged in the batch's issue (supervisor, 2026-11-16).
$inGame = if (Test-Path $ll) { $m = Select-String $ll -Pattern 'state: Swofty Launcher (\S+),' | Select-Object -First 1; if ($m) { $m.Matches[0].Groups[1].Value } else { 'not found' } } else { 'no loader.log' }
$lv = @("launcher before launch: $launcherBefore", "launcher in game (loader.log): $inGame")
if ($inGame -match '^\d' -and $inGame -ne $launcherBefore) { $lv += "NOTE: the two differ (an update during the race?)" }
$prev = Join-Path $Batch "race_$($Race - 1)\launcher.txt"
if (Test-Path $prev) {
    $pv = ((Get-Content $prev | Where-Object { $_ -match '^launcher in game' }) -split ': ', 2)[1]
    if ($pv -and $pv -ne $inGame) { $lv += "LAUNCHER CHANGED: race $($Race - 1) ran on $pv, this race on $inGame" }
}
$lv | Set-Content (Join-Path $out 'launcher.txt') -Encoding utf8
$lv | ForEach-Object { "launcher.txt: $_" }

# race_feel per race (the primaries come from it): the capture stays in %TEMP%\verve-udp\shell-*; keep a copy in raw\
# (gitignored) and write race_feel.csv / race_feel_summary.json into <race>\race_feel\
$t0 = [TimeZoneInfo]::ConvertTime($now, $tz, [TimeZoneInfo]::Local)
$bin = Get-ChildItem (Join-Path $env:TEMP 'verve-udp') -Directory -Filter 'shell-*' -ErrorAction SilentlyContinue |
    Where-Object { $_.CreationTime -ge $t0.AddSeconds(-5) } | Sort-Object CreationTime -Descending | Select-Object -First 1 |
    ForEach-Object { Join-Path $_.FullName 'udp.bin' }
$cut = (Test-Path (Join-Path $out 'pause_cut.txt')) -or (Test-Path $pauseFlag)
if ($cut) { 'race_feel: skipped (paused; this race is invalid and rerun on RESUME)' }
elseif ($bin -and (Test-Path $bin)) {
    New-Item -ItemType Directory -Force (Join-Path $out 'raw') | Out-Null
    Copy-Item $bin (Join-Path $out 'raw\udp.bin') -Force
    $ErrorActionPreference = 'Continue'
    & python -I (Join-Path $PSScriptRoot 'race_feel.py') (Join-Path $out 'raw\udp.bin') --out (Join-Path $out 'race_feel') *> (Join-Path $out 'race_feel_stdout.txt')
    "race_feel exit: $LASTEXITCODE"
    # weather (#100 rule; --locked for the dry-locked plan, #118)
    $wa = @('-I', (Join-Path $PSScriptRoot 'weather_check.py'), (Join-Path $out 'raw\udp.bin'), '--out', $out)
    if ($LockedWeather) { $wa += '--locked' }
    & python @wa | Select-Object -First 1
    $ErrorActionPreference = 'Stop'
} else { 'race_feel: no UDP capture found for this race' }
if ($code -eq 5) { 'SAVES CHANGED: stop the batch and tell Tyler'; exit 5 }
# a pause-at the next race wouldn't make: pause now, at the end of this race (no turn of the agent needed)
if (-not (Test-Path $pauseFlag)) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'pause.ps1') -IfDue -NextMinutes ($RaceMinutes + 5)
    if ($LASTEXITCODE -ne 2) { 'pause-at reached after this race: paused' }
}
exit $code
