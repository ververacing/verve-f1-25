<#
The only way the agent merges a PR (supervisor, 2026-11-15, after two slips where a merge went out in the same
command as the commit or PR create). It refuses unless ALL of these hold:
- the PR is open, not a draft, and at least -MinAgeMinutes (5) old;
- GitHub says it's mergeable, and no CI check failed or is still pending;
- on the PR's exact head commit, checked out in a temporary worktree, the repo's selftests pass:
  race_feel --selftest, test_udp_parse, b0014_check --selftest, test_post_run_check, test_ours (live foreign
  dummies: needs F1 25 and Swofty closed), b0015_check / b0016_check --selftest;
- the PR's added lines carry no user folder, Steam account id or 64-bit Steam id, add no image outside docs/ or
  harness/fixtures/frames/, and add no unfiltered process trace (the pre-commit hook's rules, re-checked on the PR).
Then it merges with a merge commit, as its own step, and prints the merge commit.

Usage:
    powershell -File tools/merge_pr.ps1 -Pr 98            # exit 0 merged, 1 refused (reason printed)
    powershell -File tools/merge_pr.ps1 -Pr 98 -DryRun   # every check, no merge
#>
param(
    [Parameter(Mandatory)] [int] $Pr,
    [int] $MinAgeMinutes = 5,
    [switch] $DryRun,
    [string] $Python = 'python'
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot
function Refuse([string] $why) { "REFUSED #${Pr}: $why"; exit 1 }

$j = gh pr view $Pr --json state,isDraft,createdAt,mergeable,headRefOid,headRefName,title,statusCheckRollup | ConvertFrom-Json
if ($j.state -ne 'OPEN') { Refuse "state is $($j.state)" }
if ($j.isDraft) { Refuse 'it is a draft' }
$age = ((Get-Date).ToUniversalTime() - ([datetime]$j.createdAt).ToUniversalTime()).TotalMinutes
if ($age -lt $MinAgeMinutes) { Refuse ("created {0:N1} min ago; wait until it's {1} min old" -f $age, $MinAgeMinutes) }
if ($j.mergeable -ne 'MERGEABLE') { Refuse "GitHub says mergeable = $($j.mergeable)" }
$bad = @($j.statusCheckRollup | Where-Object {
    $st = if ($_.conclusion) { $_.conclusion } elseif ($_.state) { $_.state } else { $_.status }
    $st -notin 'SUCCESS', 'NEUTRAL', 'SKIPPED', 'COMPLETED' })
if ($bad.Count) { Refuse "checks not passed: $(($bad | ForEach-Object { "$($_.name)=$(if ($_.conclusion) { $_.conclusion } else { $_.status })" }) -join ', ')" }
"#$Pr '$($j.title)': open, $([math]::Round($age)) min old, mergeable, $(@($j.statusCheckRollup).Count) check(s) ok; head $($j.headRefOid.Substring(0,7))"

# tests and the hook's rules on the exact head commit, in a throwaway worktree
$wt = Join-Path $env:TEMP ("verve-merge-$Pr-" + (Get-Date -Format 'HHmmss'))
git -C $repo fetch -q origin "pull/$Pr/head"
git -C $repo worktree add -q --detach $wt $j.headRefOid
try {
    $fails = @()
    Push-Location $wt
    foreach ($t in @(@('race_feel --selftest', @('-I', 'tools/race_feel.py', '--selftest')), @('test_udp_parse', @('-I', 'tools/test_udp_parse.py')),
                     @('b0014_check --selftest', @('-I', 'tools/b0014_check.py', '--selftest')))) {
        if (-not (Test-Path ($t[1] | Where-Object { $_ -like 'tools/*' } | Select-Object -First 1))) { "  skip $($t[0]) (not in this tree)"; continue }
        & $Python @($t[1]) *> $null
        if ($LASTEXITCODE -ne 0) { $fails += $t[0] } else { "  ok $($t[0])" }
    }
    if (Test-Path 'tools/test_post_run_check.ps1') {
        & powershell -NoProfile -ExecutionPolicy Bypass -File tools/test_post_run_check.ps1 *> $null
        if ($LASTEXITCODE -ne 0) { $fails += 'test_post_run_check' } else { '  ok test_post_run_check' }
    }
    # PID ownership and the foreign-dummy check (incident 2026-11-15); b0015/b0016 scorers when present
    # the live part (dummy F1_25/swofty processes) only inside a testing window and not while paused (#107 review)
    if (Test-Path 'tools/test_ours.ps1') {
        $tz = [TimeZoneInfo]::FindSystemTimeZoneById('Pacific Standard Time')
        $pt = [TimeZoneInfo]::ConvertTime((Get-Date), $tz)
        $inWin = $pt.Hour -lt 6 -or ($pt.Hour -ge 9 -and $pt.Hour -lt 17)
        $ovr = Join-Path $env:LOCALAPPDATA 'verve-f1-25\state\window_override.txt'   # one line: the override's end, ISO, PT
        if (-not $inWin -and (Test-Path $ovr)) { try { $inWin = $pt -lt [datetime](Get-Content $ovr -TotalCount 1) } catch { } }
        $paused = Test-Path (Join-Path $env:LOCALAPPDATA 'verve-f1-25\state\paused.txt')
        if ($inWin -and -not $paused) {
            & powershell -NoProfile -ExecutionPolicy Bypass -File tools/test_ours.ps1 *> $null
            if ($LASTEXITCODE -ne 0) { $fails += 'test_ours' } else { '  ok test_ours (pure + live)' }
        } else {
            & powershell -NoProfile -ExecutionPolicy Bypass -File tools/test_ours.ps1 -PureOnly *> $null
            $why = if ($paused) { 'paused' } else { "outside a testing window ($($pt.ToString('HH:mm')) PT)" }
            if ($LASTEXITCODE -ne 0) { $fails += 'test_ours (pure)' } else { "  ok test_ours (pure only: $why; live part not run)" }
        }
    }
    if (Test-Path 'tools/test_pause.ps1') {
        # like test_ours: the live cases (PING dummies, a real pause run) only inside a window and not while paused
        if ($inWin -and -not $paused) {
            & powershell -NoProfile -ExecutionPolicy Bypass -File tools/test_pause.ps1 *> $null
            if ($LASTEXITCODE -ne 0) { $fails += 'test_pause' } else { '  ok test_pause (pure + live)' }
        } else {
            & powershell -NoProfile -ExecutionPolicy Bypass -File tools/test_pause.ps1 -PureOnly *> $null
            $why = if ($paused) { 'paused' } else { 'outside a testing window' }
            if ($LASTEXITCODE -ne 0) { $fails += 'test_pause (pure)' } else { "  ok test_pause (pure only: $why; live part not run)" }
        }
    }
    foreach ($t in @(@('b0015_check --selftest', 'tools/b0015_check.py'), @('b0016_check --selftest', 'tools/b0016_check.py'), @('weather_check --selftest', 'tools/weather_check.py'), @('b0018_check --selftest', 'tools/b0018_check.py'), @('udp_finish_watch --selftest', 'tools/udp_finish_watch.py'))) {
        if (Test-Path $t[1]) {
            & $Python -I $t[1] --selftest *> $null
            if ($LASTEXITCODE -ne 0) { $fails += $t[0] } else { "  ok $($t[0])" }
        }
    }
    # the hook's rules on the PR's added lines and files
    $base = (git merge-base origin/main $j.headRefOid).Trim()
    $account = & (Join-Path $repo 'tools\find_steam_app.ps1') -AccountId
    $steam64 = [string]([UInt64]76561197960265728 + [UInt64]$account)
    $homeRe = ([regex]::Escape($env:USERPROFILE.TrimEnd('\')) -replace '\\\\', '(?:\\\\|\\|/)')
    foreach ($l in git diff --name-status --diff-filter=ACMR "$base" $j.headRefOid) {
        $path = ($l -split "`t")[-1]
        if ($path -match '\.(png|jpe?g|gif|bmp|webp)$' -and $path -notmatch '^(harness/fixtures/frames|docs)/') { $fails += "image outside docs/: $path" }
        if ($path -notmatch '^tools/' -and (Split-Path $path -Leaf) -match '^(process_)?trace' -and (Split-Path $path -Leaf) -notmatch '^process_trace_summary') { $fails += "unfiltered trace: $path" }
    }
    $file = ''
    foreach ($l in git diff -U0 --no-color "$base" $j.headRefOid) {
        if ($l -match '^\+\+\+ b/(.*)$') { $file = $Matches[1]; continue }
        if (-not $l.StartsWith('+') -or $l.StartsWith('+++')) { continue }
        if ($l -match "(?i)$homeRe") { $fails += "user folder in $file" }
        if ($l -match "(?<!\d)$account(?!\d)") { $fails += "Steam account id in $file" }
        if ($l -match "(?<!\d)$steam64(?!\d)") { $fails += "64-bit Steam id in $file" }
    }
    Pop-Location
} finally {
    if ((Get-Location).Path -eq $wt) { Pop-Location }
    git -C $repo worktree remove --force $wt
}
if ($fails) { Refuse "tests or hook rules failed: $(($fails | Select-Object -Unique) -join '; ')" }
'  ok hook rules on the PR diff'
if ($DryRun) { "DRY RUN: #$Pr would merge"; exit 0 }
gh pr merge $Pr --merge | Out-Null
$m = gh pr view $Pr --json state,mergeCommit | ConvertFrom-Json
if ($m.state -ne 'MERGED') { "merge didn't complete: state $($m.state)"; exit 1 }
"MERGED #$Pr as $($m.mergeCommit.oid.Substring(0,7))"
exit 0
