<#
Selftests for tools/pause.ps1, in a temporary repo and state folder (the real pause flag is never touched), with
harmless dummies (copies of ping.exe named PING, never F1_25 or swofty), no popup and no Swofty step (-SkipChecks).

Usage:
    powershell -File tools/test_pause.ps1      # exit 0 = all pass
#>
$ErrorActionPreference = 'Continue'
. (Join-Path $PSScriptRoot 'ours.ps1')
$failed = 0
function Check([string] $label, [bool] $ok, $detail = '') {
    if (-not $ok) { $script:failed++ }
    "{0} {1}{2}" -f $(if ($ok) { 'ok  ' } else { 'FAIL' }), $label, $(if ($detail -and -not $ok) { " | $detail" } else { '' })
}
# Steam records, not the vdf's bytes (supervisor review of #110): pure, so these run even while Tyler plays
. (Join-Path $PSScriptRoot 'steam_records.ps1')
$lkgRows = @([pscustomobject]@{ name = 'savegame@profile#A.BWW'; size = '778568'; sha = 'bde2e3'; localtime = '1794553129' },
             [pscustomobject]@{ name = 'savegame@profile#B'; size = '416'; sha = 'b8649c'; localtime = '1794553129' })
$vdfA = "`"3059520`"`n{`n`t`"ChangeNumber`"`t`t`"41`"`n`t`"savegame@profile#A.BWW`"`n`t{`n`t`t`"size`"`t`t`"778568`"`n`t`t`"localtime`"`t`t`"1794553129`"`n`t`t`"time`"`t`t`"1794553100`"`n`t`t`"sha`"`t`t`"bde2e3`"`n`t}`n`t`"savegame@profile#B`"`n`t{`n`t`t`"size`"`t`t`"416`"`n`t`t`"localtime`"`t`t`"1794553129`"`n`t`t`"sha`"`t`t`"b8649c`"`n`t}`n}"
$vdfB = ($vdfA -replace '"ChangeNumber"\t\t"41"', '"ChangeNumber"		"57"') -replace '"time"\t\t"1794553100"', '"time"		"1794560000"'   # Steam's rewrite on exit
Check 'vdf bytes differ but the records are identical -> no difference (SAFE)' ($vdfA -ne $vdfB -and @(Compare-SteamRecords $vdfB $lkgRows).Count -eq 0)
$vdfC = $vdfA -replace '"sha"\t\t"b8649c"', '"sha"		"ffffff"'
Check 'a changed sha in a record -> a difference (WAIT)' (@(Compare-SteamRecords $vdfC $lkgRows).Count -eq 1)
$vdfD = $vdfA -replace '(?s)\t"savegame@profile#B".*?\}', ''
Check 'a record gone -> a difference (WAIT)' (@(Compare-SteamRecords $vdfD $lkgRows).Count -eq 1)

if (@(Get-ForeignProcs @() (Get-ProcSnapshot)).Count) {
    # pause.ps1 (rightly) says WAIT and does nothing while Tyler's game or launcher is up, so the cases can't run
    'SKIP: a real F1 25 or Swofty process is running; run the selftests with both closed'; exit 1
}
if (Test-Path (Join-Path $env:LOCALAPPDATA 'verve-f1-25\state\paused.txt')) {
    'SKIP: paused (state\paused.txt): it is Tyler''s PC time, so no live dummy processes; pure cases above only'; exit ([int]($failed -gt 0) + 1)
}
$tmp = Join-Path $env:TEMP ("verve-pause-test-" + (Get-Date -Format 'HHmmss'))
$state = Join-Path $tmp 'state'; $repo = Join-Path $tmp 'repo'
New-Item -ItemType Directory -Force $state, (Join-Path $repo 'runs') | Out-Null
$pause = Join-Path $PSScriptRoot 'pause.ps1'
$common = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $pause, '-Repo', $repo, '-StateDir', $state, '-NoPopup', '-SkipChecks', '-QuitWaitS', '3', '-RunnerWaitS', '5')
$tz = [TimeZoneInfo]::FindSystemTimeZoneById('Pacific Standard Time')
$pt = [TimeZoneInfo]::ConvertTime((Get-Date), $tz)
$hd = {}
try {
    # pause-at: set, not due, due
    & powershell @common -At ($pt.AddMinutes(60).ToString('HH:mm')) | Out-Null
    Check '-At writes pause_at.txt' (Test-Path (Join-Path $state 'pause_at.txt'))
    & powershell @common -IfDue -NextMinutes 20 | Out-Null
    Check '-IfDue: a race that ends before pause-at is not due (exit 2), no flag' ($LASTEXITCODE -eq 2 -and -not (Test-Path (Join-Path $state 'paused.txt'))) "exit $LASTEXITCODE"
    $o = & powershell @common -IfDue -NextMinutes 90
    Check '-IfDue: a race that would end after pause-at pauses (exit 0)' ($LASTEXITCODE -eq 0 -and (Test-Path (Join-Path $state 'paused.txt')) -and "$o" -match 'SAFE TO PLAY') "exit $LASTEXITCODE; $o"
    Check 'and pause-at is consumed' (-not (Test-Path (Join-Path $state 'pause_at.txt')))
    Check 'and the verdict is in pause_result.txt' ((Get-Content (Join-Path $state 'pause_result.txt') -Raw) -match 'SAFE TO PLAY')
    & powershell @common -Clear | Out-Null
    Check '-Clear removes the flag (RESUME)' (-not (Test-Path (Join-Path $state 'paused.txt')))

    # a "running race": shell and game of attempt 2 recorded (attempt 1's shell long gone), plus a UDP capture
    $run = Join-Path $repo 'runs\2026-11-15-B-TEST\race_7'; $agent = Join-Path $tmp 'test-runs\shell-x\agent'
    New-Item -ItemType Directory -Force $run, $agent | Out-Null
    Set-Content (Join-Path $agent 'commands.jsonl') '{"seq":1,"cmd":"status"}'
    Set-Content (Join-Path $run 'transcript.txt') @('attempt 2 started', "sandbox: $(Split-Path $agent) ({""schema"":1})")
    $ping = Join-Path $env:WINDIR 'System32\PING.EXE'
    $cap = Start-Process $ping -ArgumentList '-n', '120', '127.0.0.1' -WindowStyle Hidden -PassThru
    $sh = Start-Process $ping -ArgumentList '-n', '120', '127.0.0.1' -WindowStyle Hidden -PassThru
    $gm = Start-Process $ping -ArgumentList '-n', '120', '127.0.0.1' -WindowStyle Hidden -PassThru
    Ours-Init $run
    Ours-Add $cap 'udp capture'; Ours-Add $sh 'test shell (attempt 2)'; Ours-Add $gm 'game (attempt 2, test agent pid)'
    Start-Sleep -Seconds 1
    $t = Get-Date
    $o = & powershell @common
    $secs = ((Get-Date) - $t).TotalSeconds
    Check 'pause: SAFE TO PLAY (exit 0)' ($LASTEXITCODE -eq 0 -and "$o" -match 'SAFE TO PLAY') "exit $LASTEXITCODE; $($o -join ' / ')"
    Check 'quit was sent to the test agent' ((Get-Content (Join-Path $agent 'commands.jsonl') -Raw) -match '"cmd":"quit"')
    Check "the attempt's shell and game were stopped (they ignored the quit)" ($sh.WaitForExit(3000) -and $gm.WaitForExit(3000))
    Check 'the UDP capture (another role) was left running' (-not $cap.HasExited)
    Check 'the race is marked pause_cut.txt' (Test-Path (Join-Path $run 'pause_cut.txt'))
    Check "it took under 60 s ($([int]$secs) s, with a 3 s quit wait)" ($secs -lt 60)
} finally {
    foreach ($h in $cap, $sh, $gm) { if ($h -and -not $h.HasExited) { $h.Kill() } }   # the test's own handles
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}
exit ([int]($failed -gt 0))
