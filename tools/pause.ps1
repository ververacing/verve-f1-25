<#
PAUSE in one script (supervisor, 2026-11-15, after the 12:19 pause took 5 minutes and a turn of the agent's):
set the pause flag, quit our race through its test agent, wait for our game and shell to exit, stop only that
attempt's recorded PIDs if they won't, then the checks (saves vs the last-known-good, post_run_check, test-*
cleanup, deferred saves check, via tools/safe_to_play.ps1), and tell Tyler with a popup on the PC.

Usage:
    powershell -File tools/pause.ps1                    # pause now (Tyler or the supervisor said "pause")
    powershell -File tools/pause.ps1 -At 14:30          # heads-up: pause at 14:30 PT (state\pause_at.txt); the
                                                        # runners start no race that wouldn't end by then
    powershell -File tools/pause.ps1 -IfDue -NextMinutes 17
                                                        # the runners call this before and after each race: pauses
                                                        # (and exits 0) if the next race wouldn't end by pause-at
    powershell -File tools/pause.ps1 -Clear             # RESUME: delete the pause flag and any pause-at

Prints, writes to state\pause_result.txt and shows in a popup ("Verve: SAFE TO PLAY" or "Verve: WAIT, <reason>"):
exit 0 SAFE TO PLAY, 1 WAIT, 2 not due (-IfDue only).
Rules it keeps: it only ever stops processes recorded as ours (tools/ours.ps1), scoped to the running attempt; it
runs no Swofty step while a game or launcher that isn't ours is up (it says WAIT and defers them to pre-flight).
Test hooks (tools/test_pause.ps1): -Repo, -StateDir, -NoPopup, -SkipChecks, -QuitWaitS, -RunnerWaitS.
#>
param(
    [string] $At = '',
    [switch] $IfDue,
    [int] $NextMinutes = 17,
    [switch] $Clear,
    [string] $Why = 'pause',
    [string] $Repo = (Split-Path $PSScriptRoot -Parent),
    [string] $StateDir = (Join-Path $env:LOCALAPPDATA 'verve-f1-25\state'),
    [switch] $NoPopup,
    [switch] $SkipChecks,
    [int] $QuitWaitS = 60,
    [int] $RunnerWaitS = 150
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'ours.ps1')
. (Join-Path $PSScriptRoot 'steam_records.ps1')
New-Item -ItemType Directory -Force $StateDir | Out-Null
$tz = [TimeZoneInfo]::FindSystemTimeZoneById('Pacific Standard Time')
function PT { [TimeZoneInfo]::ConvertTime((Get-Date), $tz) }
$flag = Join-Path $StateDir 'paused.txt'
$atFile = Join-Path $StateDir 'pause_at.txt'
$resultFile = Join-Path $StateDir 'pause_result.txt'
$t0 = Get-Date
function Say([string] $s) { "$((PT).ToString('HH:mm:ss')) $s" }

if ($Clear) {
    Remove-Item $flag, $atFile -ErrorAction SilentlyContinue
    Say 'pause flag and pause-at cleared (RESUME)'; exit 0
}
if ($At) {
    $when = (PT).Date + [TimeSpan]::Parse($At)
    if ($when -le (PT)) { $when = $when.AddDays(1) }
    Set-Content $atFile $when.ToString('s') -Encoding ascii
    Say "pause-at set: $($when.ToString('yyyy-MM-dd HH:mm')) PT; no race starts that wouldn't end by then"; exit 0
}
if ($IfDue) {
    if (-not (Test-Path $atFile)) { exit 2 }
    $when = [datetime](Get-Content $atFile -TotalCount 1)
    if ((PT).AddMinutes($NextMinutes) -le $when) { Say "pause-at $($when.ToString('HH:mm')): not due (the next $NextMinutes min fit)"; exit 2 }
    $Why = "pause-at $($when.ToString('HH:mm'))"
    Remove-Item $atFile -ErrorAction SilentlyContinue
}

function Finish([string] $verdict, [int] $code) {
    $secs = [int]((Get-Date) - $t0).TotalSeconds
    $line = "$verdict  ($((PT).ToString('HH:mm:ss')) PT, pause took $secs s)"
    Set-Content $resultFile $line -Encoding utf8
    $line
    if (-not $NoPopup) {
        # a detached popup, so this script never waits on Tyler's click (Windows' own WScript.Shell, nothing installed)
        $msg = ('Verve: ' + $verdict) -replace "'", "''"
        Start-Process powershell -WindowStyle Hidden -ArgumentList @('-NoProfile', '-Command',
            "(New-Object -ComObject WScript.Shell).Popup('$msg', 0, 'Verve F1 25', 64) | Out-Null") | Out-Null
    }
    exit $code
}

# 1. the flag first: the runners start nothing while it exists, and test_ours won't start dummies
if (-not (Test-Path $flag)) { Set-Content $flag "PAUSE $((PT).ToString('s')) PT ($Why)" -Encoding ascii }
Say "PAUSE ($Why): flag set"

# 2. our live records (the running race, if any), newest run folder first
$sets = @(Get-ChildItem (Join-Path $Repo 'runs') -Recurse -Filter 'ours.csv' -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -gt (Get-Date).AddDays(-2) } | Sort-Object LastWriteTime -Descending)
$live = $null
foreach ($f in $sets) {
    $recs = @(Import-Csv $f.FullName)
    if (@(Get-OursTree $recs (Get-ProcSnapshot)).Count) { $live = $f; break }
}
if (@(Ours-Foreign).Count -and -not $live) {
    Finish "WAIT, Tyler's game or the launcher is open (not ours); the post-run checks run at the next pre-flight" 1
}

if ($live) {
    $run = $live.Directory.FullName
    Ours-Init $run
    $recs = @(Ours-Records)
    $attempt = ($recs | Where-Object { $_.Role -match 'test shell \(attempt (\d+)\)' } | ForEach-Object { [int]$Matches[1] } | Measure-Object -Maximum).Maximum
    $roles = "^(test shell \(attempt $attempt\)|game \(attempt $attempt)"
    $game = $recs | Where-Object { $_.Role -match "^game \(attempt $attempt" } | Select-Object -Last 1
    $shell = $recs | Where-Object { $_.Role -match "^test shell \(attempt $attempt\)" } | Select-Object -Last 1
    Set-Content (Join-Path $run 'pause_cut.txt') "PAUSE $((PT).ToString('s')) PT ($Why): invalid, rerun in its slot on RESUME" -Encoding utf8
    Say "running race: $(Split-Path $run -Leaf), attempt $attempt (game $($game.Id), shell $($shell.Id))"
    # 3. quit through the test agent: append to its command file (the run folder's transcript names it)
    $sb = Select-String (Join-Path $run 'transcript.txt') -Pattern '^sandbox: (.+?) \(\{' -ErrorAction SilentlyContinue | Select-Object -Last 1
    $alive = { param($r) $r -and @(Get-OursTree @($r) (Get-ProcSnapshot)).Count }
    if ($game -and (& $alive $game) -and $sb -and -not @(Ours-Foreign).Count) {
        $cmds = Join-Path $sb.Matches[0].Groups[1].Value 'agent\commands.jsonl'
        if (Test-Path $cmds) {
            [IO.File]::AppendAllText($cmds, '{"seq":900000,"cmd":"quit"}' + "`n", (New-Object Text.UTF8Encoding $false))
            Say 'quit sent to the test agent'
        }
    }
    # 4. wait for our game and shell; a foreign process ends the wait (then nothing more is stopped or run)
    $end = (Get-Date).AddSeconds($QuitWaitS)
    while ((Get-Date) -lt $end -and ((& $alive $game) -or (& $alive $shell))) {
        if (@(Ours-Foreign).Count) { break }
        Start-Sleep -Milliseconds 500
    }
    if (@(Ours-Foreign).Count) { Finish "WAIT, Tyler's game or the launcher opened during the pause; our race is left as it is and the checks wait for the next pre-flight" 1 }
    if ((& $alive $game) -or (& $alive $shell)) {
        Say "still up after $QuitWaitS s: stopping attempt $attempt only (recorded PIDs)"
        Ours-Stop "PAUSE ($Why)" $roles | Out-Null
    } else { Say 'game and shell exited' }
}

# 5. our runner scripts finish their own post-race steps (they skip UDP parsing and race_feel while paused)
$end = (Get-Date).AddSeconds($RunnerWaitS)
# never wait for our own ancestors: a runner calls this at the end of its race (-IfDue) and is still running then
$snapA = Get-ProcSnapshot; $mine = @{}; $cur = $PID
while ($cur -and -not $mine.ContainsKey($cur)) { $mine[$cur] = $true; $cur = ($snapA | Where-Object { $_.Id -eq $cur } | Select-Object -First 1).ParentId }
$scriptRx ='(b00\d\d_run|sandbox_shell|sandbox_run|run_with_udp|post_run_check|cleanup_test_profiles|deferred_saves_check|storage_sidestep)\.ps1'
do {
    $busy = @(Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe'" -ErrorAction SilentlyContinue |
        Where-Object { -not $mine.ContainsKey([int]$_.ProcessId) -and $_.CommandLine -match $scriptRx -and $_.CommandLine -notmatch 'pause\.ps1' })
    if (-not $busy.Count) { break }
    if (@(Ours-Foreign).Count) { Finish "WAIT, Tyler's game or the launcher opened during the pause; the checks wait for the next pre-flight" 1 }
    Start-Sleep -Seconds 1
} while ((Get-Date) -lt $end)
if ($busy.Count) { Finish "WAIT, cleanup running ($(($busy | ForEach-Object { [regex]::Match($_.CommandLine, $scriptRx).Value }) -join ', ') still up after $RunnerWaitS s)" 1 }

if ($SkipChecks) { Finish 'SAFE TO PLAY (test: checks skipped)' 0 }
# 6. Tyler's saves vs the newest last-known-good snapshot
$lkg = Get-ChildItem (Join-Path $env:LOCALAPPDATA 'verve-f1-25\save-backups') -Directory -Filter '*-lkg-*' -ErrorAction SilentlyContinue | Sort-Object Name | Select-Object -Last 1
if ($lkg) {
    $g = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'saves_guard.ps1') -Action Check -Backup $lkg.FullName -Log (Join-Path $StateDir 'pause_lkg')
    if ($LASTEXITCODE -ne 0) { Finish "WAIT, Tyler's Steam saves differ from the last-known-good ($($lkg.Name)); the supervisor must look first" 1 }
    $app = & (Join-Path $PSScriptRoot 'find_steam_app.ps1')
    # Steam's per-file RECORDS, never the vdf's raw bytes (Steam rewrites it on every game exit; guard_snapshot.ps1)
    $vdf = Join-Path $app 'remotecache.vdf'
    $lkgRec = Join-Path $lkg.FullName 'steam_records.csv'
    if ((Test-Path $vdf) -and (Test-Path $lkgRec)) {
        $diff = @(Compare-SteamRecords (Get-Content $vdf -Raw) (Import-Csv $lkgRec))
        if ($diff.Count) { Finish "WAIT, Steam's records of Tyler's saves differ from the last-known-good ($($lkg.Name): $($diff.Count) record(s)); the supervisor must look first" 1 }
    }
    Say "saves = last-known-good ($($lkg.Name))"
}
# 7. post_run_check, cleanup, deferred saves check, and nothing of ours or foreign up
$v = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'safe_to_play.ps1') -Repo $Repo
$code = $LASTEXITCODE
Finish (("$v" -replace '^WAIT: ', 'WAIT, ').Trim()) $code
