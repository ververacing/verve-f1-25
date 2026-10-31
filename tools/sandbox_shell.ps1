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
function Log([string] $s) { $s; Add-Content $transcript $s -Encoding utf8 }

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

    function Send([string] $cmd, [int] $timeoutS = 400) {
        $script:seq++
        $p.StandardInput.WriteLine($cmd); $p.StandardInput.Flush()
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
        $r = Send 'status' 30
        if ($r -and $r.value) { $v = $r.value; foreach ($k in 'screen', 'top', 'screens') { if ($v.$k) { return ($v.$k | Select-Object -Last 1) } } }
        return ''
    }

    $first = Send $steps[0]
    $ms = if ($first) { [int]$first.ms } else { 0 }
    if ($ms -lt $SkippedIntroS * 1000) {
        Log "intro skipped (splash after $([math]::Round($ms / 1000)) s); relaunching"
        Get-Process swofty, F1_25 -ErrorAction SilentlyContinue | Stop-Process -Force
        Start-Sleep -Seconds 3
        & $Swofty restore | Out-Null
        & powershell -NoProfile -File (Join-Path $PSScriptRoot 'cleanup_test_profiles.ps1') | Out-Null
        $result = 'intro skipped'; continue
    }
    Log "intro played (splash after $([math]::Round($ms / 1000)) s)"

    $result = 'plan done'
    foreach ($s in $steps | Select-Object -Skip 1) {
        if ($p.HasExited) { $result = 'shell exited'; break }
        if ($s -match '^@sleep (\d+)') { Start-Sleep -Seconds ([int]$Matches[1]); continue }
        if ($s -match '^@expect (.+)$') {
            $want = $Matches[1]; $scr = Screen
            if ($scr -notmatch $want) { Log "EXPECT FAILED: screen '$scr' !~ $want; stopping the plan"; $result = "stopped at expect $want"; break }
            continue
        }
        if ($s -match '^@while (\S+) (\d+) (.+)$') {
            $want = $Matches[1]; $max = [int]$Matches[2]; $cmd = $Matches[3]
            for ($i = 0; $i -lt $max; $i++) {
                $scr = Screen
                if ($scr -notmatch $want) { Log "while: screen '$scr' left $want after $i press(es)"; break }
                Send $cmd | Out-Null; Start-Sleep -Seconds 4
            }
            continue
        }
        Send $s | Out-Null
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
$after = Snapshot
$diff = foreach ($k in @($before.Keys) + @($after.Keys) | Select-Object -Unique) {
    if ($before[$k] -ne $after[$k]) { "{0}: {1} -> {2}" -f $k, $before[$k], $after[$k] }
}
$diff | Set-Content (Join-Path $Out 'saves_diff.txt') -Encoding utf8
if ($diff) { Log 'SAVES CHANGED: stop sandbox runs and tell Tyler'; $diff; exit 5 }
Log "saves unchanged ($($after.Count) entries)"
if ($result -ne 'plan done') { exit 6 }
exit 0
