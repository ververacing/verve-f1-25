<#
Selftests for PID ownership (tools/ours.ps1) and the "never stop a process we didn't start" rule (incident
2026-11-15, docs/incidents/2026-11-15-killed-tyler-game.md).

Usage:
    powershell -File tools/test_ours.ps1      # exit 0 = all pass

Part 1, pure: Get-OursTree / Get-ForeignProcs on synthetic process snapshots (a reused PID, a child tree, a game
started through Steam, Tyler's launcher).
Part 2, live (the supervisor's check h): the test starts FOREIGN dummies named F1_25.exe and swofty-launcher.exe
(copies of ping.exe in %TEMP%, not recorded as ours) plus one dummy of OURS with a child named swofty.exe. Then
Ours-Stop, post_run_check, storage_sidestep, cleanup_test_profiles, sandbox_shell and safe_to_play are run against
them, and the foreign dummies must all still be alive afterwards. Only then does the test end its own dummies, through
the handles it holds. Refuses to run (exit 1) if a real F1 25 or Swofty process is up: the scripts would then (rightly)
refuse for the real one, and the test must not confuse Tyler's session.
#>
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'ours.ps1')
$failed = 0
function Check([string] $label, [bool] $ok, $detail = '') {
    if (-not $ok) { $script:failed++ }
    "{0} {1}{2}" -f $(if ($ok) { 'ok  ' } else { 'FAIL' }), $label, $(if ($detail -and -not $ok) { " | $detail" } else { '' })
}

# ---- part 1: pure ----
$t = Get-Date '2026-11-15 08:16:00'
$snap = @(
    [pscustomobject]@{ Id = 100; ParentId = 1; Name = 'swofty'; Start = $t }                      # our test shell
    [pscustomobject]@{ Id = 101; ParentId = 100; Name = 'simplified-helper'; Start = $t.AddSeconds(3) }
    [pscustomobject]@{ Id = 102; ParentId = 100; Name = 'swofty'; Start = $t.AddSeconds(4) }       # its child
    [pscustomobject]@{ Id = 200; ParentId = 50; Name = 'F1_25'; Start = $t.AddSeconds(15) }        # our game, via Steam
    [pscustomobject]@{ Id = 300; ParentId = 1; Name = 'swofty-launcher'; Start = $t.AddMinutes(14) }   # Tyler's
    [pscustomobject]@{ Id = 301; ParentId = 300; Name = 'swofty'; Start = $t.AddMinutes(14.2) }
    [pscustomobject]@{ Id = 400; ParentId = 50; Name = 'F1_25'; Start = $t.AddMinutes(14.4) }      # Tyler's game
    [pscustomobject]@{ Id = 500; ParentId = 100; Name = 'swofty'; Start = $t.AddMinutes(-30) }     # older than its "parent": PID reuse, not a child
)
$rec = @([pscustomobject]@{ Id = 100; Start = $t.ToString('o') }, [pscustomobject]@{ Id = 200; Start = $t.AddSeconds(15).ToString('o') })
$tree = @(Get-OursTree $rec $snap | ForEach-Object { $_.Id } | Sort-Object)
Check 'our tree = shell, its children, the adopted game' (($tree -join ',') -eq '100,101,102,200') ($tree -join ',')
$for = @(Get-ForeignProcs $rec $snap | ForEach-Object { $_.Id } | Sort-Object)
Check "Tyler's launcher, its swofty and his game are foreign" (($for -join ',') -eq '300,301,400,500') ($for -join ',')
$reused = @([pscustomobject]@{ Id = 300; Start = $t.ToString('o') })   # a record whose PID now belongs to Tyler's launcher
Check 'a reused PID (start time differs) is not ours' (@(Get-OursTree $reused $snap).Count -eq 0)
Check 'no records: nothing is ours' (@(Get-OursTree @() $snap).Count -eq 0)

# ---- part 2: live foreign dummies ----
if (Get-Process F1_25, swofty, swofty-launcher -ErrorAction SilentlyContinue) {
    'SKIP part 2: a real F1 25 or Swofty process is running; run the selftests with both closed'
    exit 1
}
$ErrorActionPreference = 'Continue'   # the scripts under test refuse on stderr; in 5.1 that must not end this test
$dir = Join-Path $env:TEMP ("verve-foreign-test-" + (Get-Date -Format 'HHmmss'))
New-Item -ItemType Directory -Force $dir | Out-Null
$ping = Join-Path $env:WINDIR 'System32\PING.EXE'
foreach ($n in 'F1_25.exe', 'swofty-launcher.exe', 'swofty.exe') { Copy-Item $ping (Join-Path $dir $n) }
$fGame = Start-Process (Join-Path $dir 'F1_25.exe') -ArgumentList '-n', '300', '127.0.0.1' -WindowStyle Hidden -PassThru
$fLaunch = Start-Process (Join-Path $dir 'swofty-launcher.exe') -ArgumentList '-n', '300', '127.0.0.1' -WindowStyle Hidden -PassThru
$run = Join-Path $dir 'run'
Ours-Init $run
$oursCmd = Start-Process cmd -ArgumentList '/c', "`"$(Join-Path $dir 'swofty.exe')`" -n 300 127.0.0.1" -WindowStyle Hidden -PassThru
Ours-Add $oursCmd 'test dummy (ours)'
Start-Sleep -Seconds 2
try {
    $foreign = @(Ours-Foreign | ForEach-Object { $_.Id })
    Check 'the foreign dummies are seen as foreign' ($foreign -contains $fGame.Id -and $foreign -contains $fLaunch.Id) ($foreign -join ',')
    $oursChild = @(Get-OursTree (Ours-Records) (Get-ProcSnapshot) | Where-Object { $_.Name -eq 'swofty' })
    Check "our dummy's swofty child is ours, not foreign" ($oursChild.Count -eq 1 -and $foreign -notcontains $oursChild[0].Id)
    Check 'Ours-Stop refuses while something foreign runs' (-not (Ours-Stop 'selftest'))
    Check 'and our own dummy is left running too' (-not $oursCmd.HasExited)

    $o = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'post_run_check.ps1') -Out (Join-Path $dir 'prc')
    Check 'post_run_check: SKIPPED (exit 4) before any swofty command' ($LASTEXITCODE -eq 4 -and -not ($o | Where-Object { $_ -match '^post-run:' })) "exit $LASTEXITCODE"
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'storage_sidestep.ps1') -ExpProfile verve-test -DryRun *> $null
    Check 'storage_sidestep refuses' ($LASTEXITCODE -ne 0) "exit $LASTEXITCODE"
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'cleanup_test_profiles.ps1') *> $null
    Check 'cleanup_test_profiles refuses' ($LASTEXITCODE -ne 0) "exit $LASTEXITCODE"
    $plan = Join-Path $dir 'plan.txt'; Set-Content $plan 'wait screen=splash 180'
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'sandbox_shell.ps1') -Fixture none -Plan $plan -ExpProfile verve-test -Out (Join-Path $dir 'shell') *> $null
    Check 'sandbox_shell refuses to start' ($LASTEXITCODE -ne 0 -and -not (Test-Path (Join-Path $dir 'shell\transcript.txt'))) "exit $LASTEXITCODE"
    $v = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'safe_to_play.ps1')
    Check 'safe_to_play says WAIT' ($LASTEXITCODE -eq 1 -and "$v" -match '^WAIT') "$v"

    Check 'the foreign F1_25 dummy is still alive' (-not $fGame.HasExited)
    Check 'the foreign launcher dummy is still alive' (-not $fLaunch.HasExited)

    # foreign gone: now Ours-Stop stops our dummy and its child, and nothing else
    $fGame.Kill(); $fLaunch.Kill(); $fGame.WaitForExit(5000) | Out-Null; $fLaunch.WaitForExit(5000) | Out-Null   # the test's own handles
    Check 'with nothing foreign, Ours-Stop stops our tree' ((Ours-Stop 'selftest') -and $oursCmd.WaitForExit(5000))
    Start-Sleep -Milliseconds 500
    Check "our dummy's child is gone too" (-not @(Get-ProcSnapshot | Where-Object { $_.Name -eq 'swofty' -and $_.ParentId -eq $oursCmd.Id }).Count)
} finally {
    foreach ($h in $fGame, $fLaunch, $oursCmd) { if ($h -and -not $h.HasExited) { $h.Kill() } }   # by the test's own handles only
    Get-ProcSnapshot | Where-Object { $_.Name -eq 'swofty' -and $_.ParentId -eq $oursCmd.Id } | ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Milliseconds 500
    Remove-Item -Recurse -Force $dir -ErrorAction SilentlyContinue
}
exit ([int]($failed -gt 0))
