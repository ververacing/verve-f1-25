<#
Selftests for tools/post_run_check.ps1 on synthetic doctor output (no game, no restore): the benign cache-file line,
WAITING when only the launcher blocks the sidestep, and URGENT for real drift.

Usage:
    powershell -File tools/test_post_run_check.ps1             # exit 0 = all pass
    powershell -File tools/test_post_run_check.ps1 -PureOnly   # only the cases that don't depend on live processes

While F1 25 or the Swofty Launcher is running (a race, or Tyler playing), post_run_check SKIPs every call on purpose,
so the cases that need doctor's path can't run: then only the pure cases run (the two simulated-running ones, which
want SKIPPED whatever is up) and the rest are reported as skipped, a pass of the pure part, as tools/merge_pr.ps1
treats test_ours / test_pause. -PureOnly forces that path.
#>
param([switch] $PureOnly)
$ErrorActionPreference = 'Stop'
$t = Join-Path $env:TEMP ("prc-test-" + (Get-Date -Format 'HHmmss'))
New-Item -ItemType Directory -Force "$t\j", "$t\game", "$t\game-dll" | Out-Null
Set-Content "$t\game-dll\version.dll" 'x'
function Doc([string] $name, [string] $game, [string[]] $lines) {
    $f = Join-Path $t "$name.txt"
    Set-Content $f (@("build id           25251167", "game dir           $game") + $lines)
    $f
}
$cases = @(
    @{ label = 'benign cache-file line alone is clean'; doc = (Doc 'benign' "$t\game" @('drift              swofty/cache/exe-sha256.tsv is not part of the game')); side = 'launcher'; want = 0 },
    @{ label = 'post-run swofty line alone is clean'; doc = (Doc 'swofty' "$t\game" @('drift              swofty is not part of the game')); side = 'launcher'; want = 0 },
    @{ label = 'other swofty/ file + launcher open -> WAITING'; doc = (Doc 'other' "$t\game" @('drift              swofty/cache/other.bin is not part of the game')); side = 'launcher'; want = 3 },
    @{ label = 'other swofty/ file + sidestep refuses on files -> URGENT'; doc = (Doc 'other2' "$t\game" @('drift              swofty/cache/other.bin is not part of the game')); side = 'files'; want = 2 },
    @{ label = 'modded game file + launcher open -> URGENT'; doc = (Doc 'mod' "$t\game" @('drift              2025_asset_groups/ui_package/persistent.erp differs from the baseline')); side = 'launcher'; want = 2 },
    @{ label = 'open journal + launcher open -> URGENT'; doc = (Doc 'journal' "$t\game" @('drift              journal 18e814a0758e6a90-7776 is open')); side = 'launcher'; want = 2 },
    @{ label = 'version.dll present + launcher open -> URGENT'; doc = (Doc 'dll' "$t\game-dll" @('drift              swofty/cache/other.bin is not part of the game')); side = 'launcher'; want = 2 },
    @{ label = 'added file outside swofty/ + launcher open -> URGENT'; doc = (Doc 'added' "$t\game" @('drift              version.dll is not part of the game')); side = 'launcher'; want = 2 },
    # incident 2026-11-15: a launcher (or game) that is up means SKIPPED before any swofty command, whatever doctor would say
    @{ label = 'launcher running + modded file -> SKIPPED, nothing run'; doc = (Doc 'run-l' "$t\game" @('drift              journal 18e844ef557cb610-30780 is open')); side = 'launcher'; running = 'launcher'; want = 4 },
    @{ label = 'game running + clean doctor -> SKIPPED, nothing run'; doc = (Doc 'run-g' "$t\game" @()); side = 'ok'; running = 'game'; want = 4 }
)
$up = @(Get-Process F1_25, swofty-launcher -ErrorAction SilentlyContinue | ForEach-Object { $_.ProcessName } | Select-Object -Unique)
$why = if ($up.Count) { "skipped: a game is running ($($up -join ' and '))" } elseif ($PureOnly) { 'skipped: -PureOnly' } else { '' }
$failed = 0; $skipped = 0
foreach ($c in $cases) {
    # without a simulated running process the case needs both closed for real (post_run_check checks live processes)
    if ($why -and -not $c.running) { $skipped++; "skip {0}: {1}" -f $c.label, $why; continue }
    $a = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $PSScriptRoot 'post_run_check.ps1'), '-DoctorFile', $c.doc, '-JournalDir', "$t\j", '-SimulateSidestep', $c.side)
    if ($c.running) { $a += @('-SimulateRunning', $c.running) }
    $o = & powershell @a
    $code = $LASTEXITCODE
    $ok = $code -eq $c.want
    # a SKIPPED run must stop before doctor: no doctor summary, no sidestep line
    if ($c.want -eq 4 -and ($o | Where-Object { $_ -match '^post-run:|^sidestep for' })) { $ok = $false }
    if (-not $ok) { $failed++ }
    "{0} {1}: exit {2} (want {3}) | {4}" -f $(if ($ok) { 'ok  ' } else { 'FAIL' }), $c.label, $code, $c.want, (($o | Select-Object -Last 1) -replace '\s+', ' ')
}
Remove-Item -Recurse -Force $t
if ($skipped) { "pure part: $($cases.Count - $skipped) case(s) run, $failed failed; $skipped $why" }
exit ([int]($failed -gt 0))
