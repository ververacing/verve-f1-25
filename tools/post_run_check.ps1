<#
Post-run check (supervisor, 2026-11-14), run by sandbox_shell.ps1 and sandbox_run.ps1 after every run and in the
PAUSE routine: the game folder must be stock, so a plain Steam launch gives Tyler the stock game.

Clean = doctor shows no drift, 0 open journals and no version.dll in the game folder. Two drift lines are benign
(supervisor ruling, 2026-11-14): `swofty is not part of the game` (post-run) and exactly
`swofty/cache/exe-sha256.tsv is not part of the game` (Swofty's own cache file, seen after every 1.9.51 run).

REAL drift = an open journal, version.dll, a game file that differs from the baseline, or an added file outside the
game's swofty/ folder. OTHER drift = any other added file inside swofty/.

If not clean: tools/storage_sidestep.ps1 for the open journal's addons, ONE `swofty restore`, and a re-check.
- Still not clean, or the sidestep refused: exit 2, URGENT (stop all testing; Tyler must not launch the game).
- Except: the sidestep refused ONLY because a swofty process is running (Tyler's launcher) and there's no REAL drift:
  exit 3, "WAITING: launcher open, restore deferred". Not urgent; run the check again once the launcher is closed.

Usage:
    powershell -File tools/post_run_check.ps1 [-Out runs/<id>]     # exit 0 clean, 2 URGENT, 3 WAITING (launcher open),
                                                                    # 4 SKIPPED (F1 25 running: Tyler may be playing)

While F1 25 is running the game folder is in use (if it isn't our run, it's Tyler playing through Swofty, and an
open journal and installed overlay are expected): the check only reports, exit 4, and never sidesteps or restores.
    powershell -File tools/test_post_run_check.ps1                 # the selftests
#>
param(
    [string] $Out = '',
    [string] $DoctorFile = '',   # test only: read doctor's output from this file instead of running it
    [string] $JournalDir = '',   # test only: look for journals here
    [ValidateSet('', 'ok', 'launcher', 'files')] [string] $SimulateSidestep = '',   # test only: the sidestep's outcome
    [string] $ExpProfile = 'verve-test',   # fallback addon list when doctor names an open journal but its file isn't found
    [string] $Swofty = "$env:LOCALAPPDATA\Programs\SwoftyLauncher\bin\swofty.exe"
)
$ErrorActionPreference = 'Stop'
$log = if ($Out) { New-Item -ItemType Directory -Force $Out | Out-Null; Join-Path $Out 'post_run_check.txt' } else { '' }
function L([string] $s) { $s = $s.Replace($env:USERPROFILE, '%USERPROFILE%'); $s; if ($log) { Add-Content $log $s -Encoding utf8 } }
$journals = if ($JournalDir) { $JournalDir } else { Join-Path $env:LOCALAPPDATA 'Swofty\state\journal' }
if (-not $DoctorFile -and (Get-Process F1_25 -ErrorAction SilentlyContinue)) {
    L 'SKIPPED: F1 25 is running (the game folder is in use; if this isn''t our run, Tyler is playing). Nothing checked or changed; run again once the game is closed.'
    exit 4
}

function State {
    $doc = if ($DoctorFile) { Get-Content $DoctorFile } else { & $Swofty doctor }
    $game = $doc | Where-Object { $_ -match '^game dir\s+(.+)$' } | ForEach-Object { $Matches[1].Trim() } | Select-Object -First 1
    $drift = @($doc | Where-Object { $_ -match '^drift\s+' -and $_ -notmatch '^drift\s+swofty is not part of the game\s*$' -and
        $_ -notmatch '^drift\s+swofty/cache/exe-sha256\.tsv is not part of the game\s*$' })
    # real drift: a modded or replaced game file, or an added file outside swofty/ (an open journal or version.dll too)
    $real = @($drift | Where-Object { $_ -match 'differs from the baseline' -or $_ -match 'journal\s+\S+\s+is open' -or
        ($_ -match '^drift\s+(\S+) is not part of the game' -and $Matches[1] -notmatch '^swofty/') })
    # primary signal: doctor's own "journal <id> is open" line; second: any file in the journal folder (any extension)
    $openIds = @($doc | Where-Object { $_ -match 'journal\s+(\S+)\s+is open' } | ForEach-Object { $Matches[1] })
    $files = @(Get-ChildItem $journals -File -Force -ErrorAction SilentlyContinue)
    $dll = $game -and (Test-Path (Join-Path $game 'version.dll'))
    [pscustomobject]@{ clean = (-not $drift.Count -and -not $openIds.Count -and -not $files.Count -and -not $dll)
        real = ($real.Count -or $openIds.Count -or $files.Count -or $dll)
        drift = $drift; openIds = $openIds; files = $files; dll = $dll }
}
function Show($s, [string] $when) {
    L "$when`: $(if ($s.clean) { 'CLEAN' } else { 'NOT CLEAN' }) (drift lines $($s.drift.Count), doctor's open journals $($s.openIds.Count) [$($s.openIds -join ',')], journal files $($s.files.Count), version.dll $(if ($s.dll) { 'present' } else { 'absent' }))"
    $s.drift | Select-Object -First 5 | ForEach-Object { L "  $_" }
}

$s = State
Show $s 'post-run'
if ($s.clean) { exit 0 }

# the open journal's addons are the ones restore's rollback will swap (game swofty/addons/<id>; core = swofty.core)
# journal format (state\journal\<id>.json, seen 2026-11-14): {"schema_version":1,"id":"18e814a0758e6a90-7776",
# "profile":"verve-test","build_id":"25251167","entries":[{"seq":10,"op":"create-dir","path":"swofty/addons",...},...]}
$ids = foreach ($j in $s.files) {
    try { (Get-Content $j.FullName -Raw | ConvertFrom-Json).entries | Where-Object { $_.path -match '^swofty/addons/([^/]+)$' } |
        ForEach-Object { if ($Matches[1] -eq 'core') { 'swofty.core' } else { $Matches[1] } } } catch { L "could not read journal $($j.Name)" }
}
$ids = @($ids | Select-Object -Unique)
if (-not $ids.Count) {
    # doctor names an open journal but no readable file: fall back to the run profile's enabled addons
    $prof = Get-Content (Join-Path $env:LOCALAPPDATA "Swofty\profiles\$ExpProfile.json") -Raw | ConvertFrom-Json
    $ids = @($prof.addons | Where-Object { $_.enabled } | ForEach-Object { $_.id })
    L "no readable journal file: using $ExpProfile's addons"
}
L "sidestep for: $($ids -join ', ')"
if ($SimulateSidestep) {
    $side = switch ($SimulateSidestep) { 'ok' { 'nothing to move' } 'launcher' { 'REFUSE: a swofty or F1 25 process is running' } 'files' { 'REFUSE: x\tyler holds 1 file(s)' } }
    $sideCode = if ($SimulateSidestep -eq 'ok') { 0 } else { 1 }
    L "test mode: sidestep simulated: $side"
} else {
    # -Log only when set: an empty value through powershell -File is a missing argument, and the call fails
    $sa = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $PSScriptRoot 'storage_sidestep.ps1'), '-Ids', ($ids -join ','))
    if ($log) { $sa += @('-Log', $log) }
    $side = & powershell @sa
    $sideCode = $LASTEXITCODE
    if (-not $log) { $side }
}
if ($sideCode -ne 0) {
    $onlyProcess = @($side | Where-Object { $_ -match '^REFUSE:' }).Count -gt 0 -and
        @($side | Where-Object { $_ -match '^REFUSE:' -and $_ -notmatch 'a swofty or F1 25 process is running' }).Count -eq 0
    if ($onlyProcess -and -not $s.real) {
        L 'WAITING: launcher open, restore deferred (no real drift: no modded game files, no open journal, no version.dll). Run this check again once the launcher is closed.'
        exit 3
    }
    L 'URGENT: the sidestep refused (see above); restore not tried. Stop all testing; Tyler must not launch the game.'; exit 2
}
if ($DoctorFile) { L 'test mode: no restore'; exit 2 }
$ErrorActionPreference = 'Continue'
$r = & $Swofty restore 2>&1 | ForEach-Object { "$_" -replace ' -- still locked.*$', '' }
$rc = $LASTEXITCODE
$ErrorActionPreference = 'Stop'
L "swofty restore exit $rc`: $($r | Select-Object -Last 1)"
$s = State
Show $s 'after restore'
if ($s.clean) { exit 0 }
L 'URGENT: the game folder is still not stock. Stop all testing; Tyler must not launch the game.'
exit 2
