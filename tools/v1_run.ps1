<#
Run one V-1 LAUNCH (docs/verve_v1_prereg.md): generate that launch's test add-on, install it, run the four-race plan
with it switched on, remove it. One call per launch, so control comes back between launches (docs/process.md).

Usage:
    powershell -File tools/v1_run.ps1 -Launch <n> -Batch runs/<date>-V-1 -Seed <int> [-Plan <plan>] [-Amp 3] [-NoUncapped]
    powershell -File tools/v1_run.ps1 -Make d1 -Launch <n> -Batch runs/<date>-D1 -Seed <int> [-Plan <plan>]
    powershell -File tools/v1_run.ps1 -Make d4 -Launch <n> -Batch runs/<date>-D4 -Seed <int> [-Plan <plan>]
    (-IsRetry is set only by v1_run itself, on its one rerun after a failed session check; see 10.)

-Make v1 (the default) is V-1. -Make d1 is D1 (docs/verve_d1_d2_prereg.md): step 2 calls tools/d1_make.py instead, the
add-on is gen\verve.d1-L<LL> with the id verve.d1-l<LL>, and every other step is the same. -Make d4 is D4
(docs/verve_d4_prereg.md), the same with tools/d4_make.py, gen\verve.d4-L<LL> and verve.d4-l<LL>. -Amp and -NoUncapped
are ignored for d1 and d4 (they write no maps; a note says so). Below, verve.v1-* reads verve.d1-* / verve.d4-* for them.

Steps, all logged in <Batch>\launch_<n>\:
1. Refusals as tools/b0016_run.ps1: a PAUSE or a due pause-at (exit 12), a game or launcher running that it didn't
   start (exit 9), test-* profiles left over (exit 10), a missing plan (exit 13).
2. `python -I tools/v1_make.py --seed --launch --out <launch>\gen [--amp] [--no-uncapped]` (v1_make.txt), and the add-on
   id read from gen\verve.v1-L<LL>\swofty.json, which must be v1_make's addon_id, verve.v1-l<LL> (exit 15 otherwise).
3. Any verve.v1-l* add-on left installed by an earlier launch (an entry in verve-test.json) is removed first.
4. The SHA-256 of tyler.json and verve-test.json before the install, after it, and after the removal (profile_hashes.txt).
   `swofty addons install` adds the id to every profile as a DISABLED entry (docs/process.md); it is never enabled in
   any profile file. Refused (exit 15) if tyler already lists the id enabled: that add-on would never be removed.
5. `tools/reinstall_addon.ps1 -Folder <gen>\verve.v1-L<LL>` (install.txt; a failure is exit 15, nothing launched).
6. tools/sandbox_shell.ps1 -Udp on the plan with `-Addon <id>`: the add-on is switched on only in the shell's copy of
   verve-test, for this run. The guard (saves), the hardware-settings record and the post-run check live there.
7. `tools/reinstall_addon.ps1 -Id <id> -Uninstall` (uninstall.txt), only with F1 25, the launcher and swofty all closed;
   otherwise uninstall_deferred.txt says what to run later. tyler.json's hash must return to its before-install value:
   if not, TYLER PROFILE CHANGED (exit 14). Its list only ever held a disabled entry for the id, so nothing of Tyler's
   is enabled or disabled either way.
8. launcher.txt (as b0016_run), v1addon.txt (addons.json and the loader.log lines naming the add-on), and the capture
   copied to <launch>\raw\udp.bin (gitignored). The per-race split is udp_races.txt (written by sandbox_shell).
   boot.txt: the boot's skip-relaunches (the shell's `intro skipped` lines) beside the session check, per launch
   (supervisor, 2026-11-17: does difficulty 99 only follow a skip-relaunch?).
9. The build check (check_applied).
10. The session check (supervisor's ruling, 2026-11-17; the plan's `@sessioncheck 100 17 0` at race 1's lights out,
   <launch>\session_check.txt): if it says `invalid:` (a confirmed wrong value), the launch is marked
   <launch>\invalid.txt ("invalid: difficulty N (session check)"). `unverified:` (checker exit 2/3/4) only prints and
   writes "session check UNVERIFIED: <reason>" to boot.txt: no mark, no rerun (aionly_check still validates). After the uninstall, the tyler.json hash check and the build check above
   have run for that attempt (and only if none of them stops the batch), v1_run reruns the same launch ONCE with
   -IsRetry (same -Launch/-Batch/-Seed/-Plan/-Amp/-NoUncapped); the rerun moves this attempt to invalid\ and its exit
   is v1_run's exit. If the rerun's session check fails too: exit 19.

Exit codes as b0016_run.ps1: the guard's exit (0 plan done, 6 plan stopped, 7 URGENT, 11 deferred), 5 saves changed,
9 / 10 / 12 / 13 refusals, plus 14 tyler.json not restored, 15 generate or install failed (nothing launched), 16 the
build check failed (check_applied: the game didn't hold this launch's ops; stop the batch) and 19 the session check
failed twice for this launch (STOP: tell the supervisor). gamedb_expected.txt is that launch's expected overwrite count
for v1_check.
Rerunning a launch moves the earlier attempt to <Batch>\invalid\.
#>
param(
    [Parameter(Mandatory)] [int] $Launch,
    [Parameter(Mandatory)] [string] $Batch,
    [Parameter(Mandatory)] [int] $Seed,
    [string] $Plan = 'harness\sessions\v1_austria_4races.plan',
    [double] $Amp = 3,
    [switch] $NoUncapped,
    [int] $LaunchMinutes = 80,   # for pause-at: the menu (~9 min) + 4 races at the plan's @udpfinish cap, worst case
    [string] $ExpProfile = 'verve-test',
    [string] $Python = 'python',
    [int] $SkippedIntroS = 40,
    [switch] $IsRetry,   # set by v1_run's own rerun after a failed session check (step 10): a second failure is exit 19
    [ValidateSet('v1', 'd1', 'd4')] [string] $Make = 'v1'   # which generator: v1_make.py (V-1), d1_make.py (D1) or d4_make.py (D4)
)
$ErrorActionPreference = 'Stop'
$tz = [TimeZoneInfo]::FindSystemTimeZoneById('Pacific Standard Time')
$now = [TimeZoneInfo]::ConvertTime((Get-Date), $tz)
$tag = "launch ${Launch}"
# PAUSE (tools/pause.ps1): no launch while paused; a pause-at that this launch wouldn't finish before pauses now
$pauseFlag = Join-Path $env:LOCALAPPDATA 'verve-f1-25\state\paused.txt'
if (Test-Path $pauseFlag) { "${tag}: paused ($((Get-Content $pauseFlag -TotalCount 1))); not launching"; exit 12 }
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'pause.ps1') -IfDue -NextMinutes ($LaunchMinutes + 5)
if ($LASTEXITCODE -ne 2) { "${tag}: pause-at reached; paused instead of launching"; exit 12 }
if (Get-Process F1_25 -ErrorAction SilentlyContinue) { "${tag}: a game is running that this batch didn't start; not launching"; exit 9 }
if (Get-Process swofty-launcher -ErrorAction SilentlyContinue) { "${tag}: the Swofty Launcher is open; not launching"; exit 9 }
$cleanup = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'cleanup_test_profiles.ps1')
if ($LASTEXITCODE -ne 0) { "${tag}: test profiles are left over; not launching"; $cleanup | ForEach-Object { "  $_" }; exit 10 }
if (-not (Test-Path $Plan)) { "${tag}: no plan $Plan; not launching"; exit 13 }

$out = Join-Path $Batch "launch_$Launch"
if (Test-Path $out) {
    $aside = Join-Path $Batch 'invalid'
    New-Item -ItemType Directory -Force $aside | Out-Null
    $k = 1
    while (Test-Path (Join-Path $aside "launch_${Launch}_$k")) { $k++ }
    Move-Item $out (Join-Path $aside "launch_${Launch}_$k")
    "${tag}: earlier attempt moved to invalid\launch_${Launch}_$k"
}
New-Item -ItemType Directory -Force $out | Out-Null
$out = (Resolve-Path $out).Path
function Scrub([string] $s) { $s -replace [regex]::Escape($env:USERPROFILE), '%USERPROFILE%' }
function Busy { @(Get-Process F1_25, swofty, swofty-launcher -ErrorAction SilentlyContinue).Count -gt 0 }
# tools/reinstall_addon.ps1 with its output (stderr too) in <launch>\<log>; returns its exit code
function AddonCall([string[]] $a, [string] $log) {
    $ErrorActionPreference = 'Continue'   # local to this function: a stderr line from the child must not throw
    $o = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'reinstall_addon.ps1') @a *>&1 | ForEach-Object { Scrub "$_" }
    $c = $LASTEXITCODE
    Add-Content (Join-Path $out $log) -Encoding utf8 -Value (@("== $(Get-Date -Format s) reinstall_addon.ps1 $($a -join ' ') (exit $c)") + @($o))
    return $c
}

# 2. the launch's add-on and assignment
$gen = Join-Path $out 'gen'
$ll = '{0:D2}' -f $Launch
$mk = @('-I', (Join-Path $PSScriptRoot "${Make}_make.py"), '--seed', "$Seed", '--launch', "$Launch", '--out', $gen)
if ($Make -eq 'v1') {
    $mk += @('--amp', "$Amp")
    if ($NoUncapped) { $mk += '--no-uncapped' }
} elseif (-not $IsRetry -and ($PSBoundParameters.ContainsKey('Amp') -or $NoUncapped)) { "${tag}: note: -Amp/-NoUncapped are ignored for -Make $Make ($($Make.ToUpper()) writes no maps)" }
$ErrorActionPreference = 'Continue'
& $Python @mk *> (Join-Path $out "${Make}_make.txt")
$mkCode = $LASTEXITCODE
$ErrorActionPreference = 'Stop'
$folder = Join-Path $gen "verve.$Make-L$ll"
if ($mkCode -ne 0 -or -not (Test-Path (Join-Path $folder 'swofty.json'))) { "${tag}: ${Make}_make failed (exit $mkCode, ${Make}_make.txt); nothing installed or launched"; exit 15 }
$id = (Get-Content (Join-Path $folder 'swofty.json') -Raw | ConvertFrom-Json).id
if ($id -ne "verve.$Make-l$ll") { "${tag}: the generated add-on id is '$id', not verve.$Make-l$ll; nothing installed or launched"; exit 15 }
$retryNote = if ($IsRetry) { ' (rerun after a failed session check)' } else { '' }
$armText = if ($Make -ne 'v1') { "$($Make.ToUpper()) seed $Seed launch $Launch, add-on $id, $Plan$retryNote" } else { "V-1 seed $Seed launch $Launch, add-on $id (amp $Amp$(if ($NoUncapped) { ', no-uncapped' })), $Plan$retryNote" }
Set-Content (Join-Path $out 'arm.txt') -Encoding utf8 -Value $armText
"${tag} at $($now.ToString('HH:mm:ss')) PT: seed $Seed, add-on $id, $Plan$retryNote"

# 3./4. profile hashes, leftovers, install
$profDir = Join-Path $env:LOCALAPPDATA 'Swofty\profiles'
$tylerFile = Join-Path $profDir 'tyler.json'
$expFile = Join-Path $profDir "$ExpProfile.json"
$hashLog = Join-Path $out 'profile_hashes.txt'
# not 'H': PowerShell's built-in alias h (Get-History) wins over a function of that name (16 Nov readback)
function Sha256Of([string] $f) { if (Test-Path $f) { (Get-FileHash $f -Algorithm SHA256).Hash } else { 'MISSING' } }
function IdState([string] $f, [string] $want) {
    # 'absent', 'disabled' or 'ENABLED': the state of one id in a profile's list (nothing else is read out)
    if (-not (Test-Path $f)) { return 'no profile' }
    $e = @((Get-Content $f -Raw | ConvertFrom-Json).addons | Where-Object { $_.id -eq $want })
    if (-not $e.Count) { return 'absent' }
    if (@($e | Where-Object { $_.enabled }).Count) { return 'ENABLED' }
    return 'disabled'
}
function HashLine([string] $when) {
    $l = "{0,-16} tyler {1}  {2} {3}  ({4} in tyler: {5}; in {2}: {6})" -f $when, (Sha256Of $tylerFile), $ExpProfile, (Sha256Of $expFile), $id, (IdState $tylerFile $id), (IdState $expFile $id)
    Add-Content $hashLog $l -Encoding utf8
    "profiles: $l"
}
if ((IdState $tylerFile $id) -eq 'ENABLED') { "${tag}: tyler lists $id ENABLED; never removed from Tyler's setup, so not installing"; exit 15 }
# a verve.v1-l*, verve.d1-l* or verve.d4-l* add-on that an earlier launch left installed (its uninstall deferred or
# failed): ours, remove it first (any kind, whatever -Make this launch uses)
$left = @()
if (Test-Path $expFile) {
    $left = @((Get-Content $expFile -Raw | ConvertFrom-Json).addons | ForEach-Object { $_.id } | Where-Object { $_ -match '^verve\.(v1|d1|d4)-l\d+$' })
}
foreach ($lid in $left) {
    if ((IdState $tylerFile $lid) -eq 'ENABLED') { "${tag}: leftover $lid is ENABLED in tyler; not touching it; not launching"; exit 15 }
    "${tag}: leftover $lid from an earlier launch; removing it (exit $(AddonCall @('-Id', $lid, '-Uninstall') 'leftover_uninstall.txt'))"
}
HashLine 'before install'
$tylerBefore = Sha256Of $tylerFile
$insCode = AddonCall @('-Folder', $folder) 'install.txt'
HashLine 'after install'
$expState = IdState $expFile $id
$tylerState = IdState $tylerFile $id
# expected: a disabled entry in every profile (docs/process.md). Enabled anywhere means it would run outside this launch
if ($expState -eq 'absent') { "${tag}: note: the install added no $id entry to $ExpProfile (-Addon switches it on regardless)" }
if ($insCode -ne 0 -or $expState -eq 'ENABLED' -or $tylerState -eq 'ENABLED') {
    "${tag}: install of $id failed or left it enabled (exit $insCode; $ExpProfile $expState, tyler $tylerState; install.txt); removing it, nothing launched"
    "uninstall exit: $(AddonCall @('-Id', $id, '-Uninstall') 'uninstall.txt')"
    HashLine 'after uninstall'
    if ((Sha256Of $tylerFile) -ne $tylerBefore) { 'TYLER PROFILE CHANGED: tyler.json does not hash as before the install (profile_hashes.txt); stop and tell the supervisor'; exit 14 }
    exit 15
}

# 6. the run (the launcher updates itself: record its version every launch)
$launcherExe = Join-Path $env:LOCALAPPDATA 'Programs\SwoftyLauncher\bin\swofty-launcher.exe'
$launcherBefore = if (Test-Path $launcherExe) { (Get-Item $launcherExe).VersionInfo.ProductVersion } else { 'MISSING' }
$shellArgs = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $PSScriptRoot 'sandbox_shell.ps1'), '-Fixture', 'tyler-profile-20261031',
    '-ExpProfile', $ExpProfile, '-Plan', $Plan, '-Udp', '-Addon', $id,
    '-Channels', 'default,RaceStarts:info,LAPTIMES:info,CUTSCENE_MANAGER:info,CUTSCENE_PODIUM:info', '-Out', $out)
if ($SkippedIntroS -ne 40) { $shellArgs += @('-SkippedIntroS', "$SkippedIntroS") }   # only when changed (the shell's default is 40)
powershell @shellArgs |
    ForEach-Object { Scrub $_ } | Where-Object { $_ -match 'EXPECT|intro|ABORT|^result:|^saves |SAVES CHANGED|NO RESULT|udp recording|udpfinish: race \d+ exit|^restart \d+: (race started|garage)|RESTART FAILED|^sessioncheck: exit|SESSION CHECK' }
$code = $LASTEXITCODE
"guard exit: $code"

# 10. the session check at race 1's lights out (session_check.txt, first line the verdict): mark a failed one now, so
# the mark stands whatever happens below; the rerun waits until the uninstall, hash and build checks have run
$scFile = Join-Path $out 'session_check.txt'
$scFailed = $false; $scWhy = ''
$scLine = if (Test-Path $scFile) { [string](Get-Content $scFile -TotalCount 1) } else { 'none (no session_check.txt: the plan never reached @sessioncheck)' }
"session check: $scLine"
$scNote = ''
if ($scLine -match '^(invalid: .+?)(?: \(uid \d+\))?$') { $scFailed = $true; $scWhy = "$($Matches[1]) (session check)" }
# unverified (checker exit 2/3/4): noted only, no mark and no rerun (supervisor, review of #167); aionly_check still
# validates each race's difficulty, track and weather
elseif ($scLine -match '^unverified: (.*)$') { $scNote = "session check UNVERIFIED: $($Matches[1])"; $scNote }
if ($scFailed) { Set-Content (Join-Path $out 'invalid.txt') -Encoding utf8 -Value $scWhy; "${tag}: $scWhy; marked invalid (invalid.txt)" }
# boot: how many skip-relaunches this launch's boot took (the shell's `intro skipped` lines), beside the session check
$tr = Join-Path $out 'transcript.txt'
$bootLines = @(if (Test-Path $tr) { Get-Content $tr | Where-Object { $_ -match '^(attempt \d+ started|intro (skipped|played))' } })
$boot = if (Test-Path $tr) { "boot: skip-relaunches $(@($bootLines | Where-Object { $_ -match '^intro skipped' }).Count)" } else { 'boot: unknown (no transcript.txt)' }
Set-Content (Join-Path $out 'boot.txt') -Encoding utf8 -Value (@($boot) + @($bootLines | ForEach-Object { "  $(Scrub $_)" }) + @("session check: $scLine") + @($scNote | Where-Object { $_ }))
$boot

# 7. remove the add-on (never while a game or Swofty process is up: no Swofty steps then, incident 2026-11-15)
$tylerRestored = $true
if (Busy) {
    $who = (@(Get-Process F1_25, swofty, swofty-launcher -ErrorAction SilentlyContinue) | ForEach-Object { "$($_.ProcessName) $($_.Id)" }) -join ', '
    Set-Content (Join-Path $out 'uninstall_deferred.txt') -Encoding utf8 -Value @("pending $(Get-Date -Format s)", "reason: running as the launch ended: $who",
        "next: with F1 25, the launcher and swofty closed: powershell -File tools/reinstall_addon.ps1 -Id $id -Uninstall, then compare tyler.json's hash with profile_hashes.txt ('before install')",
        'the next tools/v1_run.ps1 launch also removes it first (leftover verve.v1-l*, verve.d1-l* or verve.d4-l* in verve-test)')
    "ADD-ON LEFT INSTALLED: $id (a disabled entry in every profile); a game or Swofty process is running ($who); see uninstall_deferred.txt"
} else {
    "uninstall exit: $(AddonCall @('-Id', $id, '-Uninstall') 'uninstall.txt')"
    HashLine 'after uninstall'
    $tylerAfter = Sha256Of $tylerFile
    if ($tylerAfter -eq $tylerBefore) { Add-Content $hashLog 'tyler.json: restored (hash as before the install)' -Encoding utf8; 'tyler.json: hash as before the install' }
    else {
        $tylerRestored = $false
        Add-Content $hashLog "tyler.json: NOT RESTORED ($tylerBefore -> $tylerAfter)" -Encoding utf8
        "TYLER PROFILE CHANGED: tyler.json hashed $tylerBefore before the install and $tylerAfter after the removal (profile_hashes.txt); stop and tell the supervisor"
    }
}

# 8. per-launch logging: the add-on as the run had it, the launcher version, the capture
$lines = @()
$aj = Join-Path $out 'addons.json'
$lines += if (Test-Path $aj) { "addons.json: $((Get-Content $aj -Raw) -replace '\s+', ' ')" } else { 'addons.json: MISSING' }
$lines += if ((Test-Path $aj) -and ((Get-Content $aj -Raw) -match [regex]::Escape($id))) { "addons.json names ${id}: yes" } else { "addons.json names ${id}: NO (the run may not have had the add-on)" }
$llog = Join-Path $out 'raw\loader.log'
if (Test-Path $llog) {
    $l1 = @(Get-Content $llog | Where-Object { $_ -match "verve\.$Make" })
    $lines += "loader.log $id lines: $($l1.Count)"
    $lines += $l1 | ForEach-Object { Scrub $_ }
} else { $lines += 'loader.log: MISSING' }
$lines | Set-Content (Join-Path $out "${Make}addon.txt") -Encoding utf8
"${Make}addon.txt: $($lines[1])"

$inGame = if (Test-Path $llog) { $m = Select-String $llog -Pattern 'state: Swofty Launcher (\S+),' | Select-Object -First 1; if ($m) { $m.Matches[0].Groups[1].Value } else { 'not found' } } else { 'no loader.log' }
$lv = @("launcher before launch: $launcherBefore", "launcher in game (loader.log): $inGame")
if ($inGame -match '^\d' -and $inGame -ne $launcherBefore) { $lv += 'NOTE: the two differ (an update during the launch?)' }
$prev = Join-Path $Batch "launch_$($Launch - 1)\launcher.txt"
if (Test-Path $prev) {
    $pv = ((Get-Content $prev | Where-Object { $_ -match '^launcher in game' }) -split ': ', 2)[1]
    if ($pv -and $pv -ne $inGame) { $lv += "LAUNCHER CHANGED: launch $($Launch - 1) ran on $pv, this launch on $inGame" }
}
$lv | Set-Content (Join-Path $out 'launcher.txt') -Encoding utf8
$lv | ForEach-Object { "launcher.txt: $_" }

# the capture stays in %TEMP%\verve-udp\shell-*; keep a copy in raw\ (gitignored)
$t0 = [TimeZoneInfo]::ConvertTime($now, $tz, [TimeZoneInfo]::Local)
$bin = Get-ChildItem (Join-Path $env:TEMP 'verve-udp') -Directory -Filter 'shell-*' -ErrorAction SilentlyContinue |
    Where-Object { $_.CreationTime -ge $t0.AddSeconds(-5) } | Sort-Object CreationTime -Descending | Select-Object -First 1 |
    ForEach-Object { Join-Path $_.FullName 'udp.bin' }
if ($bin -and (Test-Path $bin)) {
    New-Item -ItemType Directory -Force (Join-Path $out 'raw') | Out-Null
    Copy-Item $bin (Join-Path $out 'raw\udp.bin') -Force
    "udp capture: raw\udp.bin ($((Get-Item (Join-Path $out 'raw\udp.bin')).Length) bytes)"
} else { 'udp capture: none found for this launch' }
# weather (#118, --locked; validity needs weather.txt LOCKED, as b0016_run -LockedWeather wrote it). weather_check reads
# every race session in the capture, so for a 4-race launch LOCKED means all four races stayed dry (launch 1 of V-1 was
# checked by hand the same way: LOCKED)
$rawBin = Join-Path $out 'raw\udp.bin'
if (Test-Path $rawBin) {
    & $Python -I (Join-Path $PSScriptRoot 'weather_check.py') $rawBin --out $out --locked | ForEach-Object { "weather_check: $_" }
} else { Set-Content (Join-Path $out 'weather.txt') 'weather: no capture' -Encoding utf8; 'weather_check: no capture' }
$ur = Join-Path $out 'udp_races.txt'
if (Test-Path $ur) { Get-Content $ur | ForEach-Object { "udp_races: $_" } } else { 'udp_races: none (no @udpfinish ran)' }

# 9. the build check per launch (V-1 readback, 16 Nov): the game must hold every op this launch's add-on wrote. Which
# equal-to-stock writes the build drops varies (2 of 4 at seed 1 launch 1), so each launch gets its own expected
# gamedb count (gamedb_expected.txt, read by v1_check). Offline: every path is in the 26566308 key cache, no swofty
# (D1's 76 race_start paths once check_applied -PrefillOnly docs/stock/d1_paths.txt has filled it; D4's 38 racecraft
# curves once docs/stock/d4_paths.txt has: those are key-checked only, a curve's value isn't logged).
$buildOk = $true
if (Test-Path $llog) {
    $keyCache = Join-Path (Split-Path $PSScriptRoot -Parent) 'docs\stock\v1_key_cache_26566308.csv'
    $ca = @(& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'check_applied.ps1') -Loader $llog -Folder $folder -Baseline 56 -KeyCache $keyCache 2>&1 | ForEach-Object { "$_" })
    $caCode = $LASTEXITCODE
    $ca | Set-Content (Join-Path $out 'check_applied.txt') -Encoding utf8
    $ca | ForEach-Object { "check_applied: $_" }
    $em = $ca | Select-String 'expected \d+ \+ \d+ = (\d+)' | Select-Object -First 1
    if ($em) { Set-Content (Join-Path $out 'gamedb_expected.txt') $em.Matches[0].Groups[1].Value -Encoding ascii }
    if ($caCode -ne 0) { $buildOk = $false; "BUILD CHECK FAILED (check_applied exit $caCode): the game did not hold this launch's ops; stop the batch and tell the supervisor" }
} else { $buildOk = $false; 'BUILD CHECK: no loader.log; stop the batch and tell the supervisor' }
if ((Test-Path (Join-Path $out 'pause_cut.txt')) -or (Test-Path $pauseFlag)) { "${tag}: paused during the launch; its races are invalid and rerun on RESUME" }

if ($code -eq 5) { 'SAVES CHANGED: stop the batch and tell Tyler'; exit 5 }
if ($code -eq 7) { exit 7 }
if (-not $tylerRestored) { exit 14 }
if (-not $buildOk) { exit 16 }
# 10. a failed session check: rerun this launch ONCE (it moves this attempt to invalid\); failing twice is a stop
if ($scFailed) {
    if ($IsRetry) { "STOP: the session check failed twice for launch $Launch; tell the supervisor"; exit 19 }
    "${tag}: rerunning the launch once ($scWhy)"
    $re = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $PSCommandPath, '-Launch', "$Launch", '-Batch', $Batch, '-Seed', "$Seed",
        '-Plan', $Plan, '-Amp', "$Amp", '-LaunchMinutes', "$LaunchMinutes", '-ExpProfile', $ExpProfile, '-Python', $Python,
        '-SkippedIntroS', "$SkippedIntroS", '-IsRetry', '-Make', $Make)
    if ($NoUncapped) { $re += '-NoUncapped' }
    & powershell @re
    exit $LASTEXITCODE
}
# a pause-at the next launch wouldn't make: pause now, at the end of this one (no turn of the agent needed)
if (-not (Test-Path $pauseFlag)) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'pause.ps1') -IfDue -NextMinutes ($LaunchMinutes + 5)
    if ($LASTEXITCODE -ne 2) { 'pause-at reached after this launch: paused' }
}
exit $code
