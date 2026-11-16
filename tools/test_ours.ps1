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
the handles it holds.
The live part SKIPS, exit 1 (= not passed), whenever Ours-Foreign isn't empty (a real F1 25 or Swofty process is up)
or a PAUSE or hands-off is in force (%LOCALAPPDATA%\verve-f1-25\state\paused.txt exists; docs/process.md). Dummies
named F1_25.exe / swofty*.exe could make the launcher or Steam think a game is running (supervisor, #107 review).
-PureOnly runs part 1 alone (merge_pr does that outside a testing window or while paused, and says so).
#>
param([switch] $PureOnly)
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
# barriers (supervisor review of #107): a Steam our shell started, and a game launched through it, are never ours
$snap2 = $snap + @(
    [pscustomobject]@{ Id = 600; ParentId = 100; Name = 'steam'; Start = $t.AddSeconds(5) }
    [pscustomobject]@{ Id = 601; ParentId = 600; Name = 'steamwebhelper'; Start = $t.AddSeconds(6) }
    [pscustomobject]@{ Id = 700; ParentId = 600; Name = 'F1_25'; Start = $t.AddMinutes(20) }          # Tyler's, via that Steam
    [pscustomobject]@{ Id = 710; ParentId = 100; Name = 'F1_25'; Start = $t.AddSeconds(8) }           # a child F1_25, never recorded
    [pscustomobject]@{ Id = 720; ParentId = 200; Name = 'werfault'; Start = $t.AddSeconds(30) }       # a child of our recorded game
)
$tree2 = @(Get-OursTree $rec $snap2 | ForEach-Object { $_.Id } | Sort-Object)
Check 'descent never enters steam, its children, or an unrecorded F1_25' (($tree2 -join ',') -eq '100,101,102,200') ($tree2 -join ',')
$for2 = @(Get-ForeignProcs $rec $snap2 | ForEach-Object { $_.Id })
Check 'a game launched through a Steam our shell started is foreign' ($for2 -contains 700 -and $for2 -contains 710) ($for2 -join ',')
$recSteam = $rec + @([pscustomobject]@{ Id = 600; Start = $t.AddSeconds(5).ToString('o') })
Check 'steam is never ours, even if recorded' (@(Get-OursTree $recSteam $snap2 | Where-Object { $_.Name -match '^steam' }).Count -eq 0)
Check 'no fallback adoption exists (a game is ours only by a reported PID)' (-not (Get-Command Ours-AdoptNewGame -ErrorAction SilentlyContinue))
# orphans (pause of 2026-11-15 21:56): a recorded shell that has exited leaves its children with its PID as parent
$snap3 = @(
    [pscustomobject]@{ Id = 802; ParentId = 800; Name = 'swofty'; Start = $t.AddSeconds(1) }      # child of the exited shell
    [pscustomobject]@{ Id = 803; ParentId = 800; Name = 'swofty'; Start = $t.AddMinutes(30) }     # started after the shell's exit
    [pscustomobject]@{ Id = 804; ParentId = 800; Name = 'F1_25'; Start = $t.AddSeconds(2) }       # a game is never ours by descent
    [pscustomobject]@{ Id = 805; ParentId = 900; Name = 'swofty'; Start = $t.AddSeconds(1) }      # same name, unrelated parent
)
$rec3 = @([pscustomobject]@{ Id = 800; Start = $t.ToString('o'); Name = 'swofty'; Exit = $t.AddMinutes(13).ToString('o') })
$tree3 = @(Get-OursTree $rec3 $snap3 | ForEach-Object { $_.Id } | Sort-Object)
Check 'orphan rule: a child of our exited shell, started before its recorded exit, is ours (802 only)' (($tree3 -join ',') -eq '802') ($tree3 -join ',')
$for3 = @(Get-ForeignProcs $rec3 $snap3 | ForEach-Object { $_.Id } | Sort-Object)
Check 'orphan rule: same name under an unrelated parent, a later start, and a game are foreign' (($for3 -join ',') -eq '803,804,805') ($for3 -join ',')
$snap4 = $snap3 + @([pscustomobject]@{ Id = 800; ParentId = 1; Name = 'notepad'; Start = $t.AddMinutes(20) })   # PID 800 reused
Check 'orphan rule: a reused recorded PID (alive, later start) adopts no orphans' (@(Get-OursTree $rec3 $snap4).Count -eq 0)
$snap5 = $snap3 + @([pscustomobject]@{ Id = 300; ParentId = 1; Name = 'swofty-launcher'; Start = $t.AddMinutes(14) })
Check 'orphan rule: with the launcher up, no orphan is ours' (@(Get-OursTree $rec3 $snap5).Count -eq 0)
$rec3b = @([pscustomobject]@{ Id = 800; Start = $t.ToString('o'); Name = 'swofty'; Exit = '' })
Check 'orphan rule: without a recorded exit, no orphan is ours' (@(Get-OursTree $rec3b $snap3).Count -eq 0)

# ---- part 2: live foreign dummies ----
if ($PureOnly) { 'part 2 (live dummies) not run: -PureOnly'; exit ([int]($failed -gt 0)) }
if (@(Get-ForeignProcs @() (Get-ProcSnapshot)).Count) {
    'SKIP part 2: a real F1 25 or Swofty process is running; run the selftests with both closed'
    exit 1
}
if (Test-Path (Join-Path $env:LOCALAPPDATA 'verve-f1-25\state\paused.txt')) {
    'SKIP part 2: a PAUSE or hands-off is in force (state\paused.txt); no dummy processes while paused'
    exit 1
}
$ErrorActionPreference = 'Continue'   # the scripts under test refuse on stderr; in 5.1 that must not end this test
$dir = Join-Path $env:TEMP ("verve-foreign-test-" + (Get-Date -Format 'HHmmss'))
New-Item -ItemType Directory -Force $dir | Out-Null
$ping = Join-Path $env:WINDIR 'System32\PING.EXE'
foreach ($n in 'F1_25.exe', 'swofty-launcher.exe', 'swofty.exe') { Copy-Item $ping (Join-Path $dir $n) }
New-Item -ItemType Directory -Force (Join-Path $dir 'steamdir') | Out-Null
Copy-Item (Join-Path $env:WINDIR 'System32\cmd.exe') (Join-Path $dir 'steamdir\steam.exe')   # a "Steam" that can start a child
$fGame = Start-Process (Join-Path $dir 'F1_25.exe') -ArgumentList '-n', '300', '127.0.0.1' -WindowStyle Hidden -PassThru
$fLaunch = Start-Process (Join-Path $dir 'swofty-launcher.exe') -ArgumentList '-n', '300', '127.0.0.1' -WindowStyle Hidden -PassThru
$run = Join-Path $dir 'run'
Ours-Init $run
$oursCmd = Start-Process cmd -ArgumentList '/c', "`"$(Join-Path $dir 'swofty.exe')`" -n 300 127.0.0.1" -WindowStyle Hidden -PassThru
Ours-Add $oursCmd 'test dummy (ours)'
$oursCap = Start-Process $ping -ArgumentList '-n', '300', '127.0.0.1' -WindowStyle Hidden -PassThru
Ours-Add $oursCap 'udp capture'   # another role of ours: a scoped stop must leave it running
# our recorded shell starts "Steam", which starts an "F1_25" (as if Tyler launched through a Steam our shell started)
# (a .cmd file avoids cmd's nested-quote rules: shell cmd -> steam.exe (a cmd copy) -> F1_25.exe)
$chain = Join-Path $dir 'chain.cmd'
Set-Content $chain -Encoding ascii -Value ('@"{0}" /d /c "{1}" -n 300 127.0.0.1' -f (Join-Path $dir 'steamdir\steam.exe'), (Join-Path $dir 'F1_25.exe'))
$oursShell2 = Start-Process cmd -ArgumentList '/d', '/c', "`"$chain`"" -WindowStyle Hidden -PassThru
Ours-Add $oursShell2 'test dummy shell that starts steam (ours)'
Start-Sleep -Seconds 2
$st2 = @(Get-ProcSnapshot | Where-Object { $_.Name -eq 'steam' -and $_.ParentId -eq $oursShell2.Id })
$g2 = @(Get-ProcSnapshot | Where-Object { $_.Name -eq 'F1_25' -and $st2.Count -and $_.ParentId -eq $st2[0].Id })
try {
    $foreign = @(Ours-Foreign | ForEach-Object { $_.Id })
    Check 'the foreign dummies are seen as foreign' ($foreign -contains $fGame.Id -and $foreign -contains $fLaunch.Id) ($foreign -join ',')
    $oursChild = @(Get-OursTree (Ours-Records) (Get-ProcSnapshot) | Where-Object { $_.Name -eq 'swofty' })
    Check "our dummy's swofty child is ours, not foreign" ($oursChild.Count -eq 1 -and $foreign -notcontains $oursChild[0].Id)
    Check 'the steam -> F1_25 chain under our shell exists' ($st2.Count -eq 1 -and $g2.Count -eq 1)
    $treeNow = @(Get-OursTree (Ours-Records) (Get-ProcSnapshot) | ForEach-Object { $_.Id })
    Check 'that steam and its F1_25 are not in our tree' ($treeNow -notcontains $st2[0].Id -and $treeNow -notcontains $g2[0].Id)
    Check 'and that F1_25 is listed as foreign' (@(Ours-Foreign | ForEach-Object { $_.Id }) -contains $g2[0].Id)
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
    Check 'the steam dummy and its F1_25 are still alive' (@(Get-ProcSnapshot | Where-Object { $_.Id -in @($st2[0].Id, $g2[0].Id) }).Count -eq 2)

    # foreign gone: now Ours-Stop stops our dummy and its child, and nothing else
    $fGame.Kill(); $fLaunch.Kill(); $fGame.WaitForExit(5000) | Out-Null; $fLaunch.WaitForExit(5000) | Out-Null   # the test's own handles
    # the steam chain is the test's own too: end it by the PIDs found under the test's shell handle, then that shell
    foreach ($id in @($g2[0].Id, $st2[0].Id)) { Stop-Process -Id $id -Force -ErrorAction SilentlyContinue }
    if (-not $oursShell2.HasExited) { $oursShell2.Kill() }
    Start-Sleep -Milliseconds 500
    Check 'a role-scoped stop stops only that role' ((Ours-Stop 'selftest' '^test dummy \(ours\)') -and $oursCmd.WaitForExit(5000) -and -not $oursCap.HasExited)
    Check 'with nothing foreign, Ours-Stop stops the rest of our tree' ((Ours-Stop 'selftest') -and $oursCap.WaitForExit(5000))
    Start-Sleep -Milliseconds 500
    Check "our dummy's child is gone too" (-not @(Get-ProcSnapshot | Where-Object { $_.Name -eq 'swofty' -and $_.ParentId -eq $oursCmd.Id }).Count)
} finally {
    foreach ($id in @($g2 | ForEach-Object { $_.Id }) + @($st2 | ForEach-Object { $_.Id })) { Stop-Process -Id $id -Force -ErrorAction SilentlyContinue }   # the test's own chain
    foreach ($h in $fGame, $fLaunch, $oursCmd, $oursShell2, $oursCap) { if ($h -and -not $h.HasExited) { $h.Kill() } }   # by the test's own handles only
    Get-ProcSnapshot | Where-Object { $_.Name -eq 'swofty' -and $_.ParentId -eq $oursCmd.Id } | ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Milliseconds 500
    Remove-Item -Recurse -Force $dir -ErrorAction SilentlyContinue
}
exit ([int]($failed -gt 0))
