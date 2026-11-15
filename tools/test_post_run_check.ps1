<#
Selftests for tools/post_run_check.ps1 on synthetic doctor output (no game, no restore): the benign cache-file line,
WAITING when only the launcher blocks the sidestep, and URGENT for real drift.

Usage:
    powershell -File tools/test_post_run_check.ps1      # exit 0 = all pass
#>
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
    @{ label = 'added file outside swofty/ + launcher open -> URGENT'; doc = (Doc 'added' "$t\game" @('drift              version.dll is not part of the game')); side = 'launcher'; want = 2 }
)
$failed = 0
foreach ($c in $cases) {
    $o = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'post_run_check.ps1') -DoctorFile $c.doc -JournalDir "$t\j" -SimulateSidestep $c.side
    $code = $LASTEXITCODE
    $ok = $code -eq $c.want
    if (-not $ok) { $failed++ }
    "{0} {1}: exit {2} (want {3}) | {4}" -f $(if ($ok) { 'ok  ' } else { 'FAIL' }), $c.label, $code, $c.want, (($o | Select-Object -Last 1) -replace '\s+', ' ')
}
Remove-Item -Recurse -Force $t
exit ([int]($failed -gt 0))
