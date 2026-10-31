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

Never restores anything: a change is reported, not repaired (restoring behind Steam caused the incident).
#>
param(
    [string] $Test,
    [string] $Fixture,
    [string] $Commands,
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

$verdict = 'unconfirmed'; $intro = 'unknown'; $log = $null   # $log is set below; never reuse the last attempt's
while (-not $job.HasExited) {
    # The game skips its intro video on every other launch, and then the title ignores the virtual pad
    # (docs/harness.md). A shell session needs the full intro: on a skipped one, close it and relaunch.
    if ($Fixture -and $intro -eq 'unknown' -and $log -and (Test-Path $log)) {
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
if ($intro -ne 'skipped' -or $verdict -eq 'OFF') { break }
# killed for a skipped intro: put the game folder back and free the lock before relaunching
& $Swofty restore | Out-Null
& powershell -NoProfile -File (Join-Path $PSScriptRoot 'cleanup_test_profiles.ps1') | Out-Null
}

$after = Snapshot
$diff = foreach ($k in @($before.Keys) + @($after.Keys) | Select-Object -Unique) {
    if ($before[$k] -ne $after[$k]) { "{0}: {1} -> {2}" -f $k, $before[$k], $after[$k] }
}
$diff | Set-Content (Join-Path $Out 'saves_diff.txt') -Encoding utf8
if ($diff) { 'SAVES CHANGED: stop sandbox runs and tell Tyler'; $diff; exit 5 }
"saves unchanged ($($after.Count) entries)"
if ($verdict -ne 'ON') { exit 6 }
exit $job.ExitCode
