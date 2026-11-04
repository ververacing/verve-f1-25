<#
Run a `swofty test` suite in the save sandbox (career fixture), with the supervisor's safety conditions (#57 follow-up,
2026-10-31 ruling after the corrupt-save incident in docs/harness.md):

1. Before: hash every file in Tyler's Steam `remote\` folder plus `remotecache.vdf`.
2. During: watch the run's live loader.log. The moment it reports no save sandbox (the game would use the player's own
   saves), kill the test and the game. A run whose log never confirms the sandbox within -ConfirmS seconds is killed
   too.
3. After: hash again. Any change to `remote\` or `remotecache.vdf` -> exit 5: stop and tell Tyler.

Usage:
    powershell -File tools/sandbox_run.ps1 -Test harness/tests/<suite>.test.json -Out runs/<id>
    powershell -File tools/sandbox_run.ps1 -Fixture <name> -Commands <file> -Out runs/<id>   # `swofty test shell`
                                                                                                # fed from the file
    powershell -File tools/sandbox_run.ps1 -Session "grand_prix f1_2025 austria team=forceindia driver=stroll session=race laps=5" `
        -Fixture <name> -ExpProfile <isolated profile> -Plan <file> [-Udp] -Out runs/<id>            # direct start

-Session (#64) runs `swofty test session` under the same hash check. It FAILS CLOSED: no fixture or no explicit
profile refuses to start, and if the sandbox-confirmed line isn't seen within -ConfirmS the game is killed.
-Udp records tools/udp_capture.py alongside and parses it into <Out>/udp/. Plan file, one step per line ('#' comments):
    wait screen=<id> [s] | wait event=<name> [s] | pad <button> [ms] | ai_drives_player on|off | status | quit
    @raw <json>            sent to the agent as is (its seq is replaced)
    @sleep <s>             wait without input
    @waitlog <regex> <s>   wait for a loader.log line; the plan stops if it doesn't come
    @control <idle s>      take more steps from <Out>/control.txt as lines are appended, until `@end` or idle
Writes <Out>/transcript.txt, and leaves the game folder restored and the lock free.

Never restores saves: a change is reported, not repaired (restoring behind Steam caused the incident).
#>
param(
    [string] $Test,
    [string] $Fixture,
    [string] $Commands,
    [string] $Session,
    [string] $ExpProfile,
    [string] $Plan,
    [switch] $Udp,
    [string] $Python = 'python',
    [string] $Channels = 'default,RaceStarts:info,AI_VARIATION:info,CANNED_EVENTS:info,LAPTIMES:info',
    [int] $MaxS = 3600,
    [Parameter(Mandatory)] [string] $Out,
    [int] $ConfirmS = 120,
    [int] $IntroTries = 3,
    [string] $Swofty = "$env:LOCALAPPDATA\Programs\SwoftyLauncher\bin\swofty.exe",
    [string] $SteamApp = ''   # <Steam>\userdata\<steamid>\3059520; found by tools/find_steam_app.ps1 when empty
)
$ErrorActionPreference = 'Stop'
if (-not $SteamApp) { $SteamApp = & (Join-Path $PSScriptRoot 'find_steam_app.ps1') }

function Snapshot {
    # every file in remote\ (size, mtime, sha256), plus Steam's record of each file in remotecache.vdf (size, sha,
    # localtime). Steam rewrites remotecache.vdf on every game exit, so its raw bytes aren't compared.
    $h = [ordered]@{}
    foreach ($f in Get-ChildItem (Join-Path $SteamApp 'remote') -File) {
        $h["file $($f.Name)"] = "{0} {1} {2}" -f $f.Length, $f.LastWriteTimeUtc.Ticks, (Get-FileHash $f.FullName -Algorithm SHA256).Hash
    }
    $rc = Get-Content (Join-Path $SteamApp 'remotecache.vdf') -Raw
    foreach ($m in [regex]::Matches($rc, '"([^"]+)"\s*\{([^{}]*)\}')) {
        $body = $m.Groups[2].Value
        $fields = foreach ($k in 'size', 'sha', 'localtime') { [regex]::Match($body, "`"$k`"\s*`"([^`"]*)`"").Groups[1].Value }
        if ($fields[1]) { $h["steam $($m.Groups[1].Value)"] = $fields -join ' ' }
    }
    $h
}

if (Get-Process F1_25 -ErrorAction SilentlyContinue) { throw 'F1 25 is running; start sandbox runs with the game closed.' }
New-Item -ItemType Directory -Force $Out | Out-Null
$before = Snapshot
"saves before: $($before.Count) entries (remote\ + remotecache.vdf)"

$sessions = "$env:LOCALAPPDATA\Swofty\sessions"
$raw = Join-Path (Resolve-Path $Out).Path 'raw'
# The live loader.log is in the game folder. sessions\<id>\loader.log is a copy made when the game ends, so it can't
# confirm anything during a run (seen on 1.8.4: its creation time is the game's exit).
$gameDir = & $Swofty doctor | Where-Object { $_ -match '^game dir\s+(.+)$' } | ForEach-Object { $Matches[1].Trim() } | Select-Object -First 1
$liveLog = if ($gameDir) { Join-Path $gameDir 'swofty\loader.log' } else { $null }
function FreshLiveLog([datetime] $since) {
    if ($liveLog -and (Test-Path $liveLog) -and (Get-Item $liveLog).LastWriteTime -ge $since.AddSeconds(-5)) { return $liveLog }
    return $null
}

if ($Session) {
    # direct start: fail closed before anything launches
    if (-not $Fixture) { throw '-Session needs -Fixture: a new Grand Prix overwrites the profile save''s Grand Prix' }
    if (-not $ExpProfile) { throw '-Session needs -ExpProfile: never run an experiment on the active profile' }
    if ($Session -notmatch '^(grand_prix|time_trial)\s') { throw "-Session must start with grand_prix or time_trial: $Session" }
    $OutFull = (Resolve-Path $Out).Path
    $transcript = Join-Path $OutFull 'transcript.txt'
    function Log([string] $s) { Write-Host $s; Add-Content $transcript $s -Encoding utf8 }
    function ReadShared([string] $path) {
        # the file is still being written: a plain read fails on the clash
        if (-not $path -or -not (Test-Path $path)) { return '' }
        try {
            # the game opens loader.log with delete sharing, so a reader must allow it too, or every open fails
            $fs = New-Object IO.FileStream $path, 'Open', 'Read', ([IO.FileShare]'ReadWrite, Delete')
            $sr = New-Object IO.StreamReader $fs; $text = $sr.ReadToEnd(); $sr.Dispose(); return $text
        } catch { return '' }
    }
    function KillGame { Get-Process swofty, F1_25 -ErrorAction SilentlyContinue | Stop-Process -Force }
    function GameLog {
        $live = FreshLiveLog $t0
        if ($live) { return $live }
        Get-ChildItem "$env:LOCALAPPDATA\Swofty\sessions" -Directory -ErrorAction SilentlyContinue | Where-Object { $_.CreationTime -ge $t0.AddSeconds(-5) } |
            Sort-Object CreationTime -Descending | Select-Object -First 1 | ForEach-Object { Join-Path $_.FullName 'loader.log' }
    }

    # UDP capture, from %TEMP%: python here can't read under %APPDATA% or most of %LOCALAPPDATA% (docs/harness.md)
    $cap = $null
    if ($Udp) {
        $udpWork = Join-Path $env:TEMP ("verve-udp\" + (Get-Date -Format 'yyyyMMdd-HHmmss'))
        New-Item -ItemType Directory -Force $udpWork | Out-Null
        Copy-Item (Join-Path $PSScriptRoot 'udp_capture.py'), (Join-Path $PSScriptRoot 'udp_parse.py') $udpWork -Force
        $udpBin = Join-Path $udpWork 'udp.bin'; $udpStop = Join-Path $udpWork 'stop.flag'; $udpLog = Join-Path $udpWork 'capture.log'
        $cap = Start-Process -FilePath $Python -ArgumentList @('-I', "`"$udpWork\udp_capture.py`"", '--out', "`"$udpBin`"", '--seconds', '14400', '--stop-file', "`"$udpStop`"") `
            -RedirectStandardOutput $udpLog -RedirectStandardError "$udpLog.err" -WindowStyle Hidden -PassThru
        Start-Sleep -Seconds 2
        if ($cap.HasExited) { Log 'ABORT: UDP capture failed to start; nothing launched'; Get-Content "$udpLog.err"; exit 1 }
        Log "udp capture pid $($cap.Id)"
    }

    $env:SWOFTY_GAME_LOG_CHANNELS = $Channels
    function CloseStreams {
        $errCopy.Wait(5000) | Out-Null; $outCopy.Wait(5000) | Out-Null; $errFs.Dispose(); $outFs.Dispose()
    }
    function ResetForRelaunch {
        KillGame
        $job.WaitForExit(30000) | Out-Null
        CloseStreams
        Start-Sleep -Seconds 5
        & $Swofty restore | Out-Null
        & powershell -NoProfile -File (Join-Path $PSScriptRoot 'cleanup_test_profiles.ps1') | Out-Null
        Start-Sleep -Seconds 20   # file locks (addon-profiles, overlay cache) hold on for a while after the game exits
    }
    $planResult = 'not run'
    # relaunch on a skipped intro (the title then ignores the virtual pad) or a transient lock, up to -IntroTries
    for ($try = 1; $try -le $IntroTries; $try++) {
    $t0 = Get-Date
    $psi = New-Object Diagnostics.ProcessStartInfo $Swofty, "--profile $ExpProfile test session $Session --fixture $Fixture --wait 0"
    $psi.UseShellExecute = $false; $psi.CreateNoWindow = $true
    $psi.RedirectStandardInput = $true; $psi.RedirectStandardOutput = $true; $psi.RedirectStandardError = $true
    $job = [Diagnostics.Process]::Start($psi)
    Log "launched $($t0.ToString('HH:mm:ss.fff')): test session $Session (profile $ExpProfile, fixture $Fixture)"
    # stdin stays open and empty. stdout and stderr go to files as they arrive, so the checks below see them live.
    $errPath = Join-Path $OutFull 'test_stderr.txt'; $outPath = Join-Path $OutFull 'test_stdout.txt'
    $errFs = New-Object IO.FileStream $errPath, 'Create', 'Write', 'ReadWrite', 1
    $outFs = New-Object IO.FileStream $outPath, 'Create', 'Write', 'ReadWrite', 1
    $errCopy = $job.StandardError.BaseStream.CopyToAsync($errFs)
    $outCopy = $job.StandardOutput.BaseStream.CopyToAsync($outFs)

    # FAIL CLOSED: the sandbox line and the run folder, within -ConfirmS, or the game dies
    $verdict = 'unconfirmed'; $runDir = $null
    while (-not $job.HasExited -and ((Get-Date) - $t0).TotalSeconds -le $ConfirmS) {
        $line = (ReadShared $errPath) -split "`r?`n" | Where-Object { $_ -match 'no save sandbox|player''s own saves|save sandbox is required|in test mode \(.*save sandbox\)' } | Select-Object -First 1
        if ($line -and $verdict -eq 'unconfirmed') {
            if ($line -match 'no save sandbox|player''s own saves') { $verdict = 'OFF' } else { $verdict = 'ON' }
            Log "sandbox line: $($line.Trim())"
            if ($verdict -eq 'OFF') { break }
        }
        $runDir = Get-ChildItem "$env:LOCALAPPDATA\Swofty\test-runs" -Directory | Where-Object { $_.CreationTime -ge $t0.AddSeconds(-5) -and (Test-Path (Join-Path $_.FullName 'sandbox.json')) } | Select-Object -First 1
        if ($verdict -eq 'ON' -and $runDir) { break }
        Start-Sleep -Milliseconds 500
    }
    if ($verdict -eq 'unconfirmed' -and $job.HasExited -and (ReadShared $errPath) -match 'still locked|lock .* is held by') {
        $planResult = 'game not free'
        Log "attempt ${try}: the game wasn't free (transient lock); nothing launched. Waiting, then retrying."
        ResetForRelaunch
        continue
    }
    if ($verdict -ne 'ON' -or -not $runDir) {
        Log "ABORT: save sandbox $verdict, run folder $(if ($runDir) { 'found' } else { 'missing' }); killing the test and the game"
        $verdict = if ($verdict -eq 'OFF') { 'OFF' } else { 'unconfirmed' }
        $planResult = 'no sandbox'
        KillGame
    } else {
        Log "sandbox confirmed after $([math]::Round(((Get-Date) - $t0).TotalSeconds)) s: $($runDir.Name)"
        Copy-Item (Join-Path $runDir.FullName 'sandbox.json') (Join-Path $OutFull 'sandbox.json') -ErrorAction SilentlyContinue
        # skipped intro: video_1 to legal in under 5 s, and the direct start then never gets past the title
        $intro = 'unknown'; $introEnd = (Get-Date).AddSeconds(90)
        while ($intro -eq 'unknown' -and -not $job.HasExited -and (Get-Date) -lt $introEnd) {
            $gl = GameLog
            if ($gl -and (Test-Path $gl)) {
                $v = Select-String -LiteralPath $gl -Pattern '\[test\] screen video_1$' -ErrorAction SilentlyContinue | Select-Object -First 1
                $l = Select-String -LiteralPath $gl -Pattern '\[test\] screen legal$' -ErrorAction SilentlyContinue | Select-Object -First 1
                if ($v -and $l) {
                    $gap = ([datetime]($l.Line.Substring(0, 23)) - [datetime]($v.Line.Substring(0, 23))).TotalSeconds
                    $intro = if ($gap -lt 5) { 'skipped' } else { 'played' }
                    Log "attempt ${try}: intro video $intro ($([math]::Round($gap, 1)) s)"
                }
            }
            Start-Sleep -Seconds 1
        }
        if ($intro -eq 'skipped') { $planResult = 'intro skipped'; ResetForRelaunch; continue }
        $results =Join-Path $runDir.FullName 'agent\results.jsonl'; $agentCmds = Join-Path $runDir.FullName 'agent\commands.jsonl'
        $script:seq = 0
        function ToJson([string] $cmd) {
            $o = [ordered]@{ seq = $script:seq }
            switch -Regex ($cmd) {
                '^wait screen=(\S+)(?: (\d+))?$' { $o.cmd = 'at'; $o.args = @{ phase = $Matches[1] }; $o.timeout_ms = 1000 * [int]$(if ($Matches[2]) { $Matches[2] } else { 60 }); break }
                '^wait event=(\S+)(?: (\d+))?$' { $o.cmd = 'wait'; $o.args = @{ event = $Matches[1] }; $o.timeout_ms = 1000 * [int]$(if ($Matches[2]) { $Matches[2] } else { 60 }); break }
                '^pad (\S+)(?: (\d+))?$' { $o.cmd = 'pad'; $o.args = [ordered]@{ press = $Matches[1] }; if ($Matches[2]) { $o.args.ms = [int]$Matches[2] }; $o.timeout_ms = 60000; break }
                '^ai_drives_player (on|off)$' { $o.cmd = 'ai_drives_player'; $o.args = @{ on = ($Matches[1] -eq 'on') }; $o.timeout_ms = 30000; break }
                '^@raw (.+)$' { return ($Matches[1] -replace '"seq":\s*\d+', "`"seq`":$script:seq") }
                '^(status|quit)$' { $o.cmd = $Matches[1]; break }
                default { throw "no JSON form for step '$cmd'" }
            }
            $o | ConvertTo-Json -Compress -Depth 4
        }
        function Send([string] $cmd, [int] $timeoutS = 700) {
            $script:seq++
            [IO.File]::AppendAllText($agentCmds, "$(ToJson $cmd)`n", (New-Object Text.UTF8Encoding $false))
            $deadline = (Get-Date).AddSeconds($timeoutS)
            while ((Get-Date) -lt $deadline -and -not $job.HasExited) {
                $line = (ReadShared $results) -split "`r?`n" | Where-Object { $_ -match "`"seq`":$script:seq[,}]" } | Select-Object -First 1
                if ($line) { Log ("{0:HH:mm:ss} > {1}  =>  {2}" -f (Get-Date), $cmd, $line); return }
                Start-Sleep -Milliseconds 300
            }
            Log "> $cmd  =>  NO RESULT"
        }
        function Step([string] $s) {
            if ($s -match '^@sleep (\d+)$') { Start-Sleep -Seconds ([int]$Matches[1]); return $true }
            if ($s -match '^@waitlog (.+) (\d+)$') {
                $re = $Matches[1]; $deadline = (Get-Date).AddSeconds([int]$Matches[2])
                while ((Get-Date) -lt $deadline -and -not $job.HasExited) {
                    $gl = GameLog
                    if ($gl -and (Test-Path $gl)) {
                        # Select-String reads the live log; a plain FileStream open of it comes back empty here
                        # the direct start carries on in the wrong seat when team= or driver= match nothing: never accept that
                        $bad = Select-String -LiteralPath $gl -Pattern '\[direct\].*(no entrant of team|session start failed)' -ErrorAction SilentlyContinue | Select-Object -First 1
                        if ($bad) { Log "DIRECT START FAILED: $($bad.Line.Trim())"; return $false }
                        $hit = Select-String -LiteralPath $gl -Pattern $re -ErrorAction SilentlyContinue | Select-Object -First 1
                        if ($hit) { Log ("{0:HH:mm:ss} log: {1}" -f (Get-Date), $hit.Line.Trim()); return $true }
                    }
                    Start-Sleep -Seconds 1
                }
                Log "WAITLOG FAILED: $re"; return $false
            }
            Send $s; return $true
        }
        $planResult = 'plan done'
        $steps = if ($Plan) { Get-Content $Plan | ForEach-Object { $_.Trim() } | Where-Object { $_ -and -not $_.StartsWith('#') } } else { @() }
        # a bad step must still reach the quit, the restore and the hash check below
        try {
        foreach ($s in $steps) {
            if ($job.HasExited) { $planResult = 'session exited'; break }
            if (((Get-Date) - $t0).TotalSeconds -gt $MaxS) { $planResult = 'hit -MaxS'; break }
            if ($s -match '^@control (\d+)$') {
                $idle = [int]$Matches[1]; $ctl = Join-Path $OutFull 'control.txt'; $done = 0; $last = Get-Date
                if (-not (Test-Path $ctl)) { New-Item -ItemType File $ctl | Out-Null }
                Log "control: waiting for steps in $ctl"
                while (-not $job.HasExited -and ((Get-Date) - $last).TotalSeconds -lt $idle -and ((Get-Date) - $t0).TotalSeconds -le $MaxS) {
                    $lines = @((ReadShared $ctl) -split "`r?`n" | Select-Object -SkipLast 1 | ForEach-Object { $_.Trim() })
                    $new = @($lines | Select-Object -Skip $done); $done = $lines.Count
                    foreach ($c in $new | Where-Object { $_ -and -not $_.StartsWith('#') }) {
                        $last = Get-Date
                        if ($c -eq '@end') { $last = [datetime]::MinValue; break }
                        try { [void](Step $c) } catch { Log "control step failed, going on: $_" }
                    }
                    Start-Sleep -Milliseconds 500
                }
                Log 'control: ended'; continue
            }
            if (-not (Step $s)) { $planResult = "stopped at: $s"; break }
        }
        } catch { $planResult = "plan error: $_"; Log $planResult }
        try { if (-not $job.HasExited) { Send 'quit' 120 } } catch { Log "quit failed: $_" }
        # the shell only leaves at the end of its input
        try { $job.StandardInput.Close() } catch { Log "closing stdin failed: $_" }
        if (-not $job.WaitForExit(120000)) { Log 'quit timed out; killing'; KillGame }
    }
    break
    }   # end of the relaunch loop
    $job.WaitForExit(60000) | Out-Null
    CloseStreams
    Log "plan: $planResult; test exit: $($job.ExitCode); sandbox $verdict; took $([math]::Round(((Get-Date) - $t0).TotalSeconds)) s"
    $gl = GameLog
    if ($gl -and (Test-Path $gl)) { New-Item -ItemType Directory -Force $raw | Out-Null; Copy-Item $gl (Join-Path $raw 'loader.log') -Force }

    if ($cap) {
        New-Item -ItemType File -Force $udpStop | Out-Null
        if (-not $cap.WaitForExit(15000)) { Stop-Process -Id $cap.Id -Force }
        Log "udp recording: $((Get-Item $udpBin -ErrorAction SilentlyContinue).Length) bytes in $udpWork"
        $parsed = Join-Path $udpWork 'udp'
        try { & $Python -I "$udpWork\udp_parse.py" $udpBin --out $parsed --launch-s '1,3,6' } catch { Log "udp parse failed: $_" }
        if (Test-Path $parsed) { $dest = Join-Path $OutFull 'udp'; New-Item -ItemType Directory -Force $dest | Out-Null; Copy-Item "$parsed\*" $dest -Force }
    }
    # the shell leaves its game lock and test profile behind even after a clean quit
    Start-Sleep -Seconds 5
    & $Swofty restore | Out-Null
    & powershell -NoProfile -File (Join-Path $PSScriptRoot 'cleanup_test_profiles.ps1') | Out-Null
    if ($planResult -ne 'plan done') { $verdict = if ($verdict -eq 'ON') { 'ON, plan failed' } else { $verdict } }
    $IntroTries = 0   # the suite and shell loop below doesn't run; the hash check after it does
}

for ($attempt = 1; $attempt -le $IntroTries; $attempt++) {
$t0 = Get-Date
$io = @{ NoNewWindow = $true; PassThru = $true; RedirectStandardOutput = (Join-Path $Out 'test_stdout.txt')
         RedirectStandardError = (Join-Path $Out 'test_stderr.txt') }
if ($Fixture) {
    if (-not $Commands) { throw '-Fixture needs -Commands (the shell reads its commands from that file)' }
    $job = Start-Process -FilePath $Swofty -ArgumentList @('test', 'shell', '--fixture', $Fixture, '--wait', '0') `
        -RedirectStandardInput (Resolve-Path $Commands).Path @io
} elseif ($Test) {
    $job = Start-Process -FilePath $Swofty -ArgumentList @('test', 'run', "`"$((Resolve-Path $Test).Path)`"", '--out', "`"$raw`"", '--wait', '0') @io
} else { throw 'give -Test, or -Fixture with -Commands' }
$null = $job.Handle   # cache the handle: without it Start-Process leaves ExitCode empty, and a failed test exits 0

$verdict = 'unconfirmed'; $intro = 'unknown'; $log = $null   # $log is set below; never reuse the last attempt's
while (-not $job.HasExited) {
    # The game skips its intro video on every other launch, and then the title ignores the virtual pad
    # (docs/harness.md). A shell session needs the full intro: on a skipped one, close it and relaunch.
    if (($Fixture -or $Test) -and $intro -eq 'unknown' -and $log -and (Test-Path $log)) {
        $v = Select-String $log -Pattern '\[test\] screen video_1$' | Select-Object -First 1
        $l = Select-String $log -Pattern '\[test\] screen legal$' | Select-Object -First 1
        if ($v -and $l) {
            $gap = ([datetime]($l.Line.Substring(0, 23)) - [datetime]($v.Line.Substring(0, 23))).TotalSeconds
            $intro = if ($gap -lt 5) { 'skipped' } else { 'played' }
            "intro video $intro ($([math]::Round($gap, 1)) s), attempt $attempt"
            if ($intro -eq 'skipped') {
                Get-Process swofty, F1_25 -ErrorAction SilentlyContinue | Stop-Process -Force
                break
            }
        }
    }
    $log = Get-ChildItem $sessions -Directory -ErrorAction SilentlyContinue | Where-Object { $_.CreationTime -ge $t0.AddSeconds(-5) } |
        Sort-Object CreationTime -Descending | Select-Object -First 1 | ForEach-Object { Join-Path $_.FullName 'loader.log' }
    $live = FreshLiveLog $t0
    if ($live) { $log = $live }
    # `test run` confirms in the session's loader.log; `test shell` prints it on stderr
    # ("[test] starting F1 25 in test mode (run folder ..., save sandbox)")
    $sources = @((Join-Path $Out 'test_stderr.txt')) + @($log | Where-Object { $_ -and (Test-Path $_) })
    if ($verdict -eq 'unconfirmed') {
        $line = $sources | Where-Object { Test-Path $_ } | ForEach-Object { Select-String $_ -Pattern 'no save sandbox|save sandbox is required|in test mode \(.*save sandbox\)' } |
            Select-Object -First 1
        if ($line) {
            if ($line.Line -match 'no save sandbox|player''s own saves') { $verdict = 'OFF' } else { $verdict = 'ON' }
            "sandbox line: $($line.Line.Trim())"
        }
    }
    if ($verdict -eq 'OFF' -or ($verdict -eq 'unconfirmed' -and ((Get-Date) - $t0).TotalSeconds -gt $ConfirmS)) {
        "ABORT: save sandbox $verdict; killing the test and the game"
        Get-Process swofty, F1_25 -ErrorAction SilentlyContinue | Stop-Process -Force
        break
    }
    Start-Sleep -Milliseconds 500
}
$job.WaitForExit(60000) | Out-Null
Start-Sleep -Seconds 5
"test exit: $($job.ExitCode); sandbox $verdict"
# the wrapper can stop on a lock held just after the last game's exit: nothing launched, so it's safe to retry
$stdoutNow = Get-Content (Join-Path $Out 'test_stdout.txt') -Raw -ErrorAction SilentlyContinue
# Only the lock text counts: "never reported the save sandbox" alone may be a real sandbox failure, so that stops here
$launcherLog = Join-Path $raw 'batches\1\launcher.log'
$locked = ($stdoutNow -match 'still locked') -or ((Test-Path $launcherLog) -and (Select-String -LiteralPath $launcherLog -Pattern 'still locked' -Quiet))
if ($verdict -eq 'unconfirmed' -and $locked) { $intro = 'skipped'; "attempt ${attempt}: transient lock; waiting, then retrying" }
if ($intro -ne 'skipped' -or $verdict -eq 'OFF') { break }
# killed for a skipped intro, or stopped on a lock: put the game folder back and free the lock before relaunching
& $Swofty restore | Out-Null
& powershell -NoProfile -File (Join-Path $PSScriptRoot 'cleanup_test_profiles.ps1') | Out-Null
Start-Sleep -Seconds 20
}

$after = Snapshot
$diff = foreach ($k in @($before.Keys) + @($after.Keys) | Select-Object -Unique) {
    if ($before[$k] -ne $after[$k]) { "{0}: {1} -> {2}" -f $k, $before[$k], $after[$k] }
}
# always written, empty when nothing changed: a missing file means the check never ran
Set-Content (Join-Path $Out 'saves_diff.txt') -Value @($diff) -Encoding utf8
if ($diff) { 'SAVES CHANGED: stop sandbox runs and tell Tyler'; $diff; exit 5 }
"saves unchanged ($($after.Count) entries)"
if ($Session) { Log "saves unchanged ($($after.Count) entries)" }
if ($verdict -ne 'ON') { exit 6 }
exit $job.ExitCode
