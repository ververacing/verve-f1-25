<#
Drive `swofty test shell --fixture <name>` one command at a time, in the save sandbox, under the supervisor's
conditions (docs/harness.md, "Save sandbox"). Unlike `sandbox_run.ps1 -Commands`, this keeps the shell's stdin open
and waits for each command's result, so steps can check the screen before acting.

Usage:
    powershell -File tools/sandbox_shell.ps1 -Fixture <name> -ExpProfile verve-test -Plan <plan file> -Out runs/<id>

-ExpProfile is required. Since 1.9.x `test shell` runs on a copy of --profile, or of the ACTIVE profile when none is
given, which is Tyler's `tyler` with his community addons. So the shell always gets an explicit profile of ours
(verve-*), and refuses the active one. -Addon switches extra addons on in the shell's copy. Every run writes
<Out>/profile.json (the profile file as launched) and <Out>/settings_hash.txt, so each arm's addon list and settings
are on record.

Plan file, one step per line ('#' comments):
    <shell command>              sent as is; waits for its result (e.g. `tile career`, `wait screen=fe_career 60`)
    @expect <regex>              the current screen (from `status`) must match, else the plan stops
    @while <regex> <max> <cmd>   while the current screen matches: send <cmd>, then pause 4 s; at most <max> times.
                                 This is the guard for wizard `a` presses: they stop the moment the screen leaves.
    @sleep <seconds>             wait without input
    @control <idle seconds>      take more steps live from <Out>/control.txt (appended lines), until `@end` or idle

Safety:
- Tyler's `remote\` files and Steam's per-file remotecache records are snapshotted before and after; any change
  -> exit 5 (stop, tell Tyler, never restore).
- The shell must print its sandbox confirmation on stderr within -ConfirmS, else everything is killed.
- The game skips its intro video on every other launch, and then the title ignores the virtual pad. The plan's
  first step must be `wait screen=splash 180`. If that returns in under -SkippedIntroS seconds, the intro was
  skipped: kill, `swofty restore`, clean up, relaunch (up to -IntroTries).
Writes <Out>/transcript.txt (every command and result) and <Out>/saves_diff.txt, plus storage_sidestep.txt and
post_run_check.txt (exit 7 = URGENT: the game folder isn't stock after the run).
#>
param(
    [Parameter(Mandatory)] [string] $Fixture,
    [Parameter(Mandatory)] [string] $Plan,
    [Parameter(Mandatory)] [string] $ExpProfile,   # an isolated profile of ours (verve-*); never the active one
    [Parameter(Mandatory)] [string] $Out,
    [int] $ConfirmS = 120,
    [int] $IntroTries = 3,
    [int] $SkippedIntroS = 40,
    [string[]] $Addon = @(),      # installed addons to switch on in the shell's minimal profile
    [string] $Channels = '',      # SWOFTY_GAME_LOG_CHANNELS for the game, when given
    [switch] $SidestepDryRun,     # the storage sidestep only logs what it would move (pilot: is the Defender exclusion enough?)
    [switch] $Udp,                # record tools/udp_capture.py alongside and parse it into <Out>/udp/
    [string] $Python = 'python',
    [string] $Swofty = "$env:LOCALAPPDATA\Programs\SwoftyLauncher\bin\swofty.exe",
    [string] $SteamApp = ''   # <Steam>\userdata\<steamid>\3059520; found by tools/find_steam_app.ps1 when empty
)
$ErrorActionPreference = 'Stop'
if (-not $SteamApp) { $SteamApp = & (Join-Path $PSScriptRoot 'find_steam_app.ps1') }
New-Item -ItemType Directory -Force $Out | Out-Null
$Out = (Resolve-Path $Out).Path
$transcript = Join-Path $Out 'transcript.txt'

function Snapshot {
    # Steam's remote\ files, Steam's records of them, and the launcher saves of every profile that isn't ours
    & (Join-Path $PSScriptRoot 'guard_snapshot.ps1') -SteamApp $SteamApp
}
# Write-Host, not output: Log runs inside Send/Screen/Step, whose output is their return value
function Log([string] $s) { Write-Host $s; Add-Content $transcript $s -Encoding utf8 }

# PID ownership (incident 2026-11-15): every process we start is recorded in <Out>\ours.csv, and every stop targets
# only those (tools/ours.ps1). Nothing is ever stopped by name.
. (Join-Path $PSScriptRoot 'ours.ps1')
Ours-Init $Out
$script:foreign = $false   # set once a game or launcher that isn't ours shows up: then no post-race Swofty steps at all
if (@(Ours-Foreign).Count) { throw 'F1 25 or a Swofty process (launcher) is running that this run did not start; start sandbox runs with both closed.' }
if ($ExpProfile -notlike 'verve-*') { throw "-ExpProfile $ExpProfile isn't one of ours (verve-*); never run a test on Tyler's profiles" }
$profileFile = Join-Path $env:LOCALAPPDATA "Swofty\profiles\$ExpProfile.json"
if (-not (Test-Path $profileFile)) { throw "no profile $ExpProfile ($profileFile)" }
$activeProfile = (Get-Content (Join-Path $env:LOCALAPPDATA 'Swofty\config.json') -Raw | ConvertFrom-Json).active_profile
if ($ExpProfile -eq $activeProfile) { throw "-ExpProfile $ExpProfile is the active profile; experiments run on an isolated one" }
Copy-Item $profileFile (Join-Path $Out 'profile.json') -Force
# 1.9.x stores addon data under the ACTIVE profile's name, so refuse if any of this run's addons has data there
# -Addon only when there is one: an empty value through powershell -File is a missing argument, and the call fails
$chkArgs = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $PSScriptRoot 'addon_storage_check.ps1'), '-ExpProfile', $ExpProfile)
if (@($Addon) -join ',') { $chkArgs += @('-Addon', (@($Addon) -join ',')) }
$chk = & powershell @chkArgs
$chk | Set-Content (Join-Path $Out 'addon_storage_check.txt') -Encoding utf8
if ($LASTEXITCODE -ne 0) { $chk; throw 'addon storage check refused the run (see addon_storage_check.txt)' }
$settingsHash = (Get-FileHash $profileFile -Algorithm SHA256).Hash
Set-Content (Join-Path $Out 'settings_hash.txt') -Value "$ExpProfile $settingsHash addons+=$($Addon -join ',') active=$activeProfile" -Encoding utf8
$hw = Join-Path $env:USERPROFILE 'Documents\My Games\F1 25\hardwaresettings\hardware_settings_config.xml'
Set-Content (Join-Path $Out 'udp_settings.txt') -Value ((Select-String $hw -Pattern '<udp ' -ErrorAction SilentlyContinue | Select-Object -First 1).Line.Trim()) -Encoding utf8   # Tyler's choice (60 Hz since 2026-11-14); recorded, never changed
$steps = Get-Content $Plan | Where-Object { $_.Trim() -and -not $_.Trim().StartsWith('#') } | ForEach-Object { $_.Trim() }
if ($steps[0] -notmatch '^wait screen=splash') { throw 'the plan must start with `wait screen=splash <s>` (skipped-intro check)' }
$before = Snapshot
# keep the before-snapshot outside the repo (it names save files) for a deferred check (tools/deferred_saves_check.ps1)
$outFull = (Resolve-Path $Out).Path
$snapId = "$(Split-Path (Split-Path $outFull) -Leaf)_$(Split-Path $outFull -Leaf)"
$snapDir = Join-Path $env:LOCALAPPDATA 'verve-f1-25\snapshots'
New-Item -ItemType Directory -Force $snapDir | Out-Null
$before | ConvertTo-Json | Set-Content (Join-Path $snapDir "$snapId.json") -Encoding utf8
Log "saves before: $($before.Count) entries; profile $ExpProfile ($settingsHash) +addons $($Addon -join ','); active profile $activeProfile"

if ($Channels) { $env:SWOFTY_GAME_LOG_CHANNELS = $Channels }
$addonArgs = ($Addon | ForEach-Object { "--addon $_" }) -join ' '
# UDP capture from %TEMP%: python here can't read under %APPDATA% or most of %LOCALAPPDATA% (docs/harness.md)
$cap = $null
if ($Udp) {
    $udpWork = Join-Path $env:TEMP ("verve-udp\shell-" + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    New-Item -ItemType Directory -Force $udpWork | Out-Null
    Copy-Item (Join-Path $PSScriptRoot 'udp_capture.py'), (Join-Path $PSScriptRoot 'udp_parse.py') $udpWork -Force
    $udpBin = Join-Path $udpWork 'udp.bin'; $udpStop = Join-Path $udpWork 'stop.flag'; $udpLog = Join-Path $udpWork 'capture.log'
    $cap = Start-Process -FilePath $Python -ArgumentList @('-I', "`"$udpWork\udp_capture.py`"", '--out', "`"$udpBin`"", '--seconds', '14400', '--stop-file', "`"$udpStop`"") `
        -RedirectStandardOutput $udpLog -RedirectStandardError "$udpLog.err" -WindowStyle Hidden -PassThru
    Ours-Add $cap 'udp capture'
    Start-Sleep -Seconds 2
    if ($cap.HasExited) { Log 'ABORT: UDP capture failed to start; nothing launched'; exit 1 }
    Log "udp capture pid $($cap.Id)"
}

# Swofty 1.9.51 addon-storage bug (docs/upstream/swofty_addon_storage_lock.md): move EMPTY rename targets aside before
# every launch (storage_sidestep.ps1), and check the game folder is stock after every run (post_run_check.ps1, which
# does one sidestep + restore if it isn't). URGENT (exit 7 at the end) means stop all testing: Tyler mustn't launch.
$script:urgent = $false
function Sidestep {
    # a switch can't be passed as -DryRun:$value through powershell -File (it arrives as a string), so add it only when set
    # -Addon only when there is one: an empty value through powershell -File is a missing argument, and the call fails
    $a = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $PSScriptRoot 'storage_sidestep.ps1'), '-ExpProfile', $ExpProfile,
        '-Log', (Join-Path $Out 'storage_sidestep.txt'))
    $ad = @($Addon) -join ','
    if ($ad) { $a += @('-Addon', $ad) }
    if ($SidestepDryRun) { $a += '-DryRun' }
    $o = & powershell @a
    $code = $LASTEXITCODE
    $o | ForEach-Object { Write-Host "sidestep: $_" }
    return $code
}
function PostCheck {
    $o = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'post_run_check.ps1') -Out $Out
    if ($LASTEXITCODE -eq 2) { $script:urgent = $true }
    if ($LASTEXITCODE -eq 3) { Write-Host 'post-run: WAITING: launcher open, restore deferred (not urgent)' }
    if ($LASTEXITCODE -eq 4) { Write-Host 'post-run: SKIPPED: F1 25 or the launcher is running; check again when both have closed'; $script:urgent = $true }
    $o | ForEach-Object { Write-Host "post-run: $_" }
}
$result = 'not run'
$t0 = Get-Date   # also read after the loop, so set it even when nothing launches
for ($attempt = 1; $attempt -le $IntroTries; $attempt++) {
    if ((Sidestep) -ne 0) { Log 'ABORT: storage sidestep refused (storage_sidestep.txt); nothing launched'; $result = 'sidestep refused'; break }
    # read-only: which processes start and exit around the launch (is an addon helper alive during the storage swap?)
    $trace = Start-Process powershell -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $PSScriptRoot 'process_trace.ps1'),
        '-Summary', (Join-Path (Resolve-Path $Out).Path "process_trace_summary_$(Get-Date -Format 'HHmmss').txt"), '-Seconds', '45') -WindowStyle Hidden -PassThru
    Ours-Add $trace 'process trace'
    $psi = New-Object Diagnostics.ProcessStartInfo $Swofty, "--profile $ExpProfile test shell --fixture $Fixture --wait 0 $addonArgs"
    $psi.UseShellExecute = $false; $psi.RedirectStandardInput = $true
    $psi.RedirectStandardOutput = $true; $psi.RedirectStandardError = $true; $psi.CreateNoWindow = $true
    $p = [Diagnostics.Process]::Start($psi)
    Ours-Add $p "test shell (attempt $attempt)"
    $errTask = $p.StandardError.ReadToEndAsync()   # stderr is read from the run folder's files below, not here
    $outTask = $p.StandardOutput.ReadToEndAsync()
    $t0 = Get-Date; $run = $null; $seq = 0
    Log "attempt $attempt started $($t0.ToString('HH:mm:ss'))"

    # sandbox confirmation: the shell creates test-runs\shell-<stamp>-1 with sandbox.json before the game starts
    while (-not $run -and ((Get-Date) - $t0).TotalSeconds -lt $ConfirmS -and -not $p.HasExited) {
        $run = Get-ChildItem "$env:LOCALAPPDATA\Swofty\test-runs" -Directory -Filter 'shell-*' |
            Where-Object { $_.CreationTime -ge $t0.AddSeconds(-5) -and (Test-Path (Join-Path $_.FullName 'sandbox.json')) } |
            Select-Object -First 1
        Start-Sleep -Milliseconds 500
    }
    if (-not $run) {
        Log 'ABORT: save sandbox not confirmed'
        Ours-AdoptNewGame $t0 'game (new F1_25 after our launch)' | Out-Null
        if (-not (Ours-Stop 'save sandbox not confirmed')) { $script:foreign = $true; Log 'not stopping: a process that is not ours is running' }
        $result = 'no sandbox'; break
    }
    Log "sandbox: $($run.FullName) ($((Get-Content (Join-Path $run.FullName 'sandbox.json') -Raw).Trim()))"
    $results = Join-Path $run.FullName 'agent\results.jsonl'

    $commands = Join-Path $run.FullName 'agent\commands.jsonl'
    # The shell reads stdin in blocks (it only acts on a file or at EOF), so commands go straight to the agent's
    # command file in the shell's own JSON form (seen in earlier runs' agent\commands.jsonl). The shell stays up
    # with its stdin open and empty.
    function ToJson([string] $cmd) {
        $o = [ordered]@{ seq = $script:seq }
        switch -Regex ($cmd) {
            '^wait screen=(\S+)(?: (\d+))?$' { $o.cmd = 'at'; $o.args = @{ phase = $Matches[1] }; $o.timeout_ms = 1000 * [int]($(if ($Matches[2]) { $Matches[2] } else { 60 })); break }
            '^pad (\S+)(?: (\d+))?$' { $o.cmd = 'pad'; $o.args = [ordered]@{ press = $Matches[1] }; if ($Matches[2]) { $o.args.ms = [int]$Matches[2] }; $o.timeout_ms = 60000; break }
            '^tile (\S+)$' { $o.cmd = 'tile'; $o.args = @{ tile = $Matches[1] }; $o.timeout_ms = 60000; break }
            '^save now$' { $o.cmd = 'save'; $o.args = @{ op = 'now' }; $o.timeout_ms = 120000; break }
            '^@raw (.+)$' { return ($Matches[1] -replace '"seq":\s*\d+', "`"seq`":$script:seq") }
            '^(home|title|status|quit)$' { $o.cmd = $Matches[1]; if ($Matches[1] -in 'home', 'title') { $o.timeout_ms = 60000 }; break }
            default { throw "no JSON form for shell command '$cmd'" }
        }
        $o | ConvertTo-Json -Compress -Depth 4
    }
    function Send([string] $cmd, [int] $timeoutS = 400) {
        $script:seq++
        $json = ToJson $cmd
        [IO.File]::AppendAllText($commands, "$json`n", (New-Object Text.UTF8Encoding $false))
        $deadline = (Get-Date).AddSeconds($timeoutS)
        while ((Get-Date) -lt $deadline -and -not $p.HasExited) {
            if (Test-Path $results) {
                # the agent is writing this file: a sharing clash here just means trying again
                $line = $null
                try { $line = Get-Content $results | Where-Object { $_ -match "`"seq`":$script:seq[,}]" } | Select-Object -First 1 } catch { }
                if ($line) { Log ("{0:HH:mm:ss} > {1}  =>  {2}" -f (Get-Date), $cmd, $line); return ($line | ConvertFrom-Json) }
            }
            Start-Sleep -Milliseconds 300
        }
        Log "> $cmd  =>  NO RESULT"; return $null
    }
    function Screen {
        # `status` reports the screen stack as value.phase, e.g. "|fe_career|#5f9ae18b|"
        $r = Send 'status' 30
        if ($r -and $r.value -and $r.value.phase) { return [string]$r.value.phase }
        return ''
    }

    $first = Send $steps[0]
    if (-not $first) {
        Log 'ABORT: the agent never answered the first command'; $result = 'no agent'
        Ours-AdoptNewGame $t0 'game (new F1_25 after our launch)' | Out-Null
        if (-not (Ours-Stop 'agent never answered')) { $script:foreign = $true; Log 'not stopping: a process that is not ours is running' }
        break
    }
    # the game is ours by the PID its test agent reports (it starts through Steam, so it isn't in the shell's tree)
    $st = Send 'status' 30
    $gpid = if ($st -and $st.value -and $st.value.pid) { [int]$st.value.pid } else { 0 }
    $gname = if ($gpid) { (Get-Process -Id $gpid -ErrorAction SilentlyContinue).ProcessName } else { '' }
    if ($gname -match '^F1_25') { Ours-AddId $gpid 'game (test agent pid)' | Out-Null; Log "game pid $gpid (test agent)" }
    elseif (Ours-AdoptNewGame $t0 'game (new F1_25 after our launch)') { Log 'game adopted as the one F1_25 started after our launch' }
    else { Log 'game pid unknown: it will never be stopped by this run' }
    $ms = [int]$first.ms
    if ($ms -lt $SkippedIntroS * 1000) {
        Log "intro skipped (splash after $([math]::Round($ms / 1000)) s); relaunching"
        if (-not (Ours-Stop 'intro skipped, relaunch')) { $script:foreign = $true; $result = 'not ours running'; Log 'ABORT: a process that is not ours is running; no relaunch'; break }
        Start-Sleep -Seconds 3
        PostCheck
        & powershell -NoProfile -File (Join-Path $PSScriptRoot 'cleanup_test_profiles.ps1') -Log (Join-Path $Out 'cleanup.txt') | Out-Null
        $result = 'intro skipped'; continue
    }
    Log "intro played (splash after $([math]::Round($ms / 1000)) s)"

    # one plan step; sets $script:stop to the reason when the plan must stop (Log writes to the output, so a
    # return value would be mixed with log lines)
    function Step([string] $s) {
        $script:stop = $null
        if ($s -match '^@sleep (\d+)') { Start-Sleep -Seconds ([int]$Matches[1]); return }
        if ($s -match '^@expect (.+)$') {
            $want = $Matches[1]; $scr = Screen
            if ($scr -notmatch $want) { Log "EXPECT FAILED: screen '$scr' !~ $want; stopping the plan"; $script:stop = "stopped at expect $want" }
            return
        }
        if ($s -match '^@while (\S+) (\d+) (.+)$') {
            $want = $Matches[1]; $max = [int]$Matches[2]; $cmd = $Matches[3]
            for ($i = 0; $i -lt $max; $i++) {
                $scr = Screen
                if ($scr -notmatch $want) { Log "while: screen '$scr' left $want after $i press(es)"; break }
                Send $cmd | Out-Null; Start-Sleep -Seconds 4
            }
            return
        }
        Send $s | Out-Null
    }

    $result = 'plan done'
    # a bad step must still reach the quit, the restore and the hash check below
    try {
    foreach ($s in $steps | Select-Object -Skip 1) {
        if ($p.HasExited) { $result = 'shell exited'; break }
        if ($s -match '^@control (\d+)$') {
            # live control: take further steps from <Out>/control.txt as lines are appended, until `@end` or
            # <idle> seconds without a new line. Lets a screen be mapped from frames before it is put in a plan.
            $idle = [int]$Matches[1]; $ctl = Join-Path $Out 'control.txt'; $done = 0; $last = Get-Date
            if (-not (Test-Path $ctl)) { New-Item -ItemType File $ctl | Out-Null }
            Log "control: waiting for steps in $ctl"
            while (-not $p.HasExited -and ((Get-Date) - $last).TotalSeconds -lt $idle) {
                # shared read: the file is appended to while this runs (a plain Get-Content fails on the clash)
                try {
                    $fs = New-Object IO.FileStream $ctl, 'Open', 'Read', 'ReadWrite'
                    $text = (New-Object IO.StreamReader $fs).ReadToEnd(); $fs.Dispose()
                } catch { Start-Sleep -Milliseconds 300; continue }
                # the last piece is "" after a final newline, or a line still being written: never count it
                $lines = @($text -split "`r?`n" | Select-Object -SkipLast 1 | ForEach-Object { $_.Trim() })
                $new = @($lines | Select-Object -Skip $done); $done = $lines.Count
                foreach ($c in $new | Where-Object { $_ -and -not $_.StartsWith('#') }) {
                    $last = Get-Date
                    if ($c -eq '@end') { $last = [datetime]::MinValue; break }
                    Step $c; if ($script:stop) { Log "control: $script:stop (going on)" }
                }
                Start-Sleep -Milliseconds 500
            }
            Log 'control: ended'; continue
        }
        Step $s; if ($script:stop) { $result = $script:stop; break }
    }
    } catch { $result = "plan error: $_"; Log $result }
    try { if (-not $p.HasExited) { Send 'quit' 120 | Out-Null } } catch { Log "quit failed: $_" }
    # wait up to 120 s for the shell to finish its own restore; if a process that isn't ours appears meanwhile (Tyler
    # opened the launcher or the game), stop waiting and touch nothing more (incident 2026-11-15)
    $waitEnd = (Get-Date).AddSeconds(120)
    while (-not $p.HasExited -and (Get-Date) -lt $waitEnd) {
        if (@(Ours-Foreign).Count) { $script:foreign = $true; break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $p.HasExited -and -not $script:foreign) {
        if (-not (Ours-Stop 'shell did not exit 120 s after quit')) { $script:foreign = $true }
    }
    if (-not $p.HasExited) { Log "shell (pid $($p.Id)) still running; left alone$(if ($script:foreign) { ': a process that is not ours is running' })" }
    if ($outTask.Wait(5000)) { $outTask.Result | Set-Content (Join-Path $Out 'shell_stdout.txt') -Encoding utf8 }
    if ($errTask.Wait(5000)) { $errTask.Result | Set-Content (Join-Path $Out 'shell_stderr.txt') -Encoding utf8 }
    Log "run folder: $($run.Name)"
    # which addons this run really had, for checks that need to prove the arm
    Copy-Item (Join-Path $run.FullName 'addons.json') (Join-Path $Out 'addons.json') -ErrorAction SilentlyContinue
    break
}
Log "result: $result"

if ($cap) {
    New-Item -ItemType File -Force $udpStop | Out-Null
    if (-not $cap.WaitForExit(15000)) { Ours-StopOne $cap 'udp capture did not stop on its flag' | Out-Null }
    Log "udp recording: $((Get-Item $udpBin -ErrorAction SilentlyContinue).Length) bytes"
    $parsed = Join-Path $udpWork 'udp'
    try { & $Python -I "$udpWork\udp_parse.py" $udpBin --out $parsed --launch-s '1,3,6' | Out-Null } catch { Log "udp parse failed: $_" }
    if (Test-Path $parsed) { $dest = Join-Path $Out 'udp'; New-Item -ItemType Directory -Force $dest | Out-Null; Copy-Item "$parsed\*" $dest -Force }
}

# a game or launcher that isn't ours: NO post-race Swofty steps at all (no reads under Swofty, no doctor, no cleanup,
# no saves check). Everything waits for the next pre-flight (supervisor, 2026-11-15).
if ($script:foreign -or @(Ours-Foreign).Count) {
    $who = (@(Ours-Foreign) | ForEach-Object { "$($_.Name) $($_.Id)" }) -join ', '
    Set-Content (Join-Path $Out 'saves_diff_deferred.txt') -Encoding utf8 -Value @("pending $(Get-Date -Format s)", "snapshot $snapId",
        "reason: not ours running as the run ended ($who); post-race Swofty steps not run: loader.log copy (first session folder created after $($t0.ToString('s'))), post_run_check, cleanup_test_profiles, saves check",
        'next: tools/preflight.ps1 (deferred_saves_check finishes the saves check; cleanup runs there), then copy the loader.log by hand')
    Log "POST-RACE DEFERRED: a process that is not ours is running ($who); no Swofty steps run after the race"
    if ($script:urgent) { Log 'URGENT: post_run_check reported URGENT earlier in this run (post_run_check.txt). Stop all testing.'; exit 7 }
    exit 11
}

# the game's log, before the restore below can remove it (a session's copy appears when the game exits). Our
# session is the FIRST one created after our launch: a later one belongs to someone else.
$sessionLog = Get-ChildItem "$env:LOCALAPPDATA\Swofty\sessions" -Directory -ErrorAction SilentlyContinue | Where-Object { $_.CreationTime -ge $t0.AddSeconds(-5) } |
    Sort-Object CreationTime | Select-Object -First 1 | ForEach-Object { Join-Path $_.FullName 'loader.log' }
if ($sessionLog -and (Test-Path $sessionLog)) { New-Item -ItemType Directory -Force (Join-Path $Out 'raw') | Out-Null; Copy-Item $sessionLog (Join-Path $Out 'raw\loader.log') -Force }

Start-Sleep -Seconds 5
# the shell leaves its game lock and test profile behind even after a clean quit; free them for the next run
PostCheck
& powershell -NoProfile -File (Join-Path $PSScriptRoot 'cleanup_test_profiles.ps1') -Log (Join-Path $Out 'cleanup.txt') | Out-Null
try { $after = Snapshot } catch {
    if ("$_" -notmatch 'SKIPPED') { throw }
    # F1 25 or Tyler's launcher was running as the run ended: the save check waits (supervisor, 2026-11-14)
    Set-Content (Join-Path $Out 'saves_diff_deferred.txt') -Encoding utf8 -Value @("pending $(Get-Date -Format s)", "snapshot $snapId",
        'reason: F1 25 or the Swofty Launcher (not ours) was running when the run ended; tools/deferred_saves_check.ps1 finishes it')
    Write-Host 'SAVES CHECK DEFERRED: F1 25 or the Swofty Launcher is running; see saves_diff_deferred.txt'
    # the deferral must never hide an URGENT post-run result (incident 2026-11-15: race 2's exit 2 became exit 11)
    if ($script:urgent) { Log 'URGENT: the game folder is not stock after the run (post_run_check.txt). Stop all testing; tell the supervisor and Tyler.'; exit 7 }
    exit 11
}
$diff = foreach ($k in @($before.Keys) + @($after.Keys) | Select-Object -Unique) {
    if ($before[$k] -ne $after[$k]) { "{0}: {1} -> {2}" -f $k, $before[$k], $after[$k] }
}
# always written, empty when nothing changed: a missing file means the check never ran
Set-Content (Join-Path $Out 'saves_diff.txt') -Value @($diff) -Encoding utf8
Remove-Item (Join-Path $snapDir "$snapId.json") -ErrorAction SilentlyContinue   # the check is done (supervisor: snapshots don't pile up)
if ($diff) { Log 'SAVES CHANGED: stop sandbox runs and tell Tyler'; $diff; exit 5 }
Log "saves unchanged ($($after.Count) entries)"
if ($script:urgent) { Log 'URGENT: the game folder is not stock after the run (post_run_check.txt). Stop all testing; tell the supervisor and Tyler.'; exit 7 }
if ($result -ne 'plan done') { exit 6 }
exit 0
