<#
Drive `swofty test shell --fixture <name>` one command at a time, in the save sandbox, under the supervisor's
conditions (docs/harness.md, "Save sandbox"). Unlike `sandbox_run.ps1 -Commands`, this keeps the shell's stdin open
and waits for each command's result, so steps can check the screen before acting.

Usage:
    powershell -File tools/sandbox_shell.ps1 -Fixture <name> -Plan <plan file> -Out runs/<id>

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
Writes <Out>/transcript.txt (every command and result) and <Out>/saves_diff.txt.
#>
param(
    [Parameter(Mandatory)] [string] $Fixture,
    [Parameter(Mandatory)] [string] $Plan,
    [Parameter(Mandatory)] [string] $Out,
    [int] $ConfirmS = 120,
    [int] $IntroTries = 3,
    [int] $SkippedIntroS = 40,
    [string] $Swofty = "$env:LOCALAPPDATA\Programs\SwoftyLauncher\bin\swofty.exe",
    [string] $SteamApp = 'C:\Program Files (x86)\Steam\userdata\928649988\3059520'
)
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force $Out | Out-Null
$Out = (Resolve-Path $Out).Path
$transcript = Join-Path $Out 'transcript.txt'

function Snapshot {
    $h = [ordered]@{}
    foreach ($f in Get-ChildItem (Join-Path $SteamApp 'remote') -File) {
        $h["file $($f.Name)"] = "{0} {1} {2}" -f $f.Length, $f.LastWriteTimeUtc.Ticks, (Get-FileHash $f.FullName -Algorithm SHA256).Hash
    }
    $rc = Get-Content (Join-Path $SteamApp 'remotecache.vdf') -Raw
    foreach ($m in [regex]::Matches($rc, '"([^"]+)"\s*\{([^{}]*)\}')) {
        $fields = foreach ($k in 'size', 'sha', 'localtime') { [regex]::Match($m.Groups[2].Value, "`"$k`"\s*`"([^`"]*)`"").Groups[1].Value }
        if ($fields[1]) { $h["steam $($m.Groups[1].Value)"] = $fields -join ' ' }
    }
    $h
}
# Write-Host, not output: Log runs inside Send/Screen/Step, whose output is their return value
function Log([string] $s) { Write-Host $s; Add-Content $transcript $s -Encoding utf8 }

if (Get-Process F1_25 -ErrorAction SilentlyContinue) { throw 'F1 25 is running; start sandbox runs with the game closed.' }
$steps = Get-Content $Plan | Where-Object { $_.Trim() -and -not $_.Trim().StartsWith('#') } | ForEach-Object { $_.Trim() }
if ($steps[0] -notmatch '^wait screen=splash') { throw 'the plan must start with `wait screen=splash <s>` (skipped-intro check)' }
$before = Snapshot
Log "saves before: $($before.Count) entries"

$result = 'not run'
for ($attempt = 1; $attempt -le $IntroTries; $attempt++) {
    $psi = New-Object Diagnostics.ProcessStartInfo $Swofty, "test shell --fixture $Fixture --wait 0"
    $psi.UseShellExecute = $false; $psi.RedirectStandardInput = $true
    $psi.RedirectStandardOutput = $true; $psi.RedirectStandardError = $true; $psi.CreateNoWindow = $true
    $p = [Diagnostics.Process]::Start($psi)
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
    if (-not $run) { Log 'ABORT: save sandbox not confirmed'; Get-Process swofty, F1_25 -ErrorAction SilentlyContinue | Stop-Process -Force; $result = 'no sandbox'; break }
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
                $line = Get-Content $results | Where-Object { $_ -match "`"seq`":$script:seq[,}]" } | Select-Object -First 1
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
    if (-not $first) { Log 'ABORT: the agent never answered the first command'; $result = 'no agent'; Get-Process swofty, F1_25 -ErrorAction SilentlyContinue | Stop-Process -Force; break }
    $ms = [int]$first.ms
    if ($ms -lt $SkippedIntroS * 1000) {
        Log "intro skipped (splash after $([math]::Round($ms / 1000)) s); relaunching"
        Get-Process swofty, F1_25 -ErrorAction SilentlyContinue | Stop-Process -Force
        Start-Sleep -Seconds 3
        & $Swofty restore | Out-Null
        & powershell -NoProfile -File (Join-Path $PSScriptRoot 'cleanup_test_profiles.ps1') | Out-Null
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
    if (-not $p.HasExited) { Send 'quit' 120 | Out-Null }
    if (-not $p.WaitForExit(120000)) { Get-Process swofty, F1_25 -ErrorAction SilentlyContinue | Stop-Process -Force }
    $outTask.Result | Set-Content (Join-Path $Out 'shell_stdout.txt') -Encoding utf8
    $errTask.Result | Set-Content (Join-Path $Out 'shell_stderr.txt') -Encoding utf8
    Log "run folder: $($run.Name)"
    break
}
Log "result: $result"

Start-Sleep -Seconds 5
# the shell leaves its game lock and test profile behind even after a clean quit; free them for the next run
& $Swofty restore | Out-Null
& powershell -NoProfile -File (Join-Path $PSScriptRoot 'cleanup_test_profiles.ps1') | Out-Null
$after = Snapshot
$diff = foreach ($k in @($before.Keys) + @($after.Keys) | Select-Object -Unique) {
    if ($before[$k] -ne $after[$k]) { "{0}: {1} -> {2}" -f $k, $before[$k], $after[$k] }
}
$diff | Set-Content (Join-Path $Out 'saves_diff.txt') -Encoding utf8
if ($diff) { Log 'SAVES CHANGED: stop sandbox runs and tell Tyler'; $diff; exit 5 }
Log "saves unchanged ($($after.Count) entries)"
if ($result -ne 'plan done') { exit 6 }
exit 0
