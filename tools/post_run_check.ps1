<#
Post-run check (supervisor, 2026-11-14), run by sandbox_shell.ps1 and sandbox_run.ps1 after every run and in the
PAUSE routine: the game folder must be stock, so a plain Steam launch gives Tyler the stock game.

Clean = doctor shows no drift (or only the accepted post-run line `swofty is not part of the game`), 0 open journals,
and no version.dll in the game folder. If not clean: tools/storage_sidestep.ps1 for the open journal's addons, ONE
`swofty restore`, and a re-check. Still not clean: exit 2, URGENT: stop all testing and tell the supervisor and
Tyler (he must not launch the game).

Usage:
    powershell -File tools/post_run_check.ps1 [-Out runs/<id>]     # exit 0 clean, 2 URGENT
#>
param(
    [string] $Out = '',
    [string] $DoctorFile = '',   # test only: read doctor's output from this file instead of running it
    [string] $JournalDir = '',   # test only: look for journals here
    [string] $ExpProfile = 'verve-test',   # fallback addon list when doctor names an open journal but its file isn't found
    [string] $Swofty = "$env:LOCALAPPDATA\Programs\SwoftyLauncher\bin\swofty.exe"
)
$ErrorActionPreference = 'Stop'
$log = if ($Out) { New-Item -ItemType Directory -Force $Out | Out-Null; Join-Path $Out 'post_run_check.txt' } else { '' }
function L([string] $s) { $s = $s.Replace($env:USERPROFILE, '%USERPROFILE%'); $s; if ($log) { Add-Content $log $s -Encoding utf8 } }
$journals = if ($JournalDir) { $JournalDir } else { Join-Path $env:LOCALAPPDATA 'Swofty\state\journal' }

function State {
    $doc = if ($DoctorFile) { Get-Content $DoctorFile } else { & $Swofty doctor }
    $game = $doc | Where-Object { $_ -match '^game dir\s+(.+)$' } | ForEach-Object { $Matches[1].Trim() } | Select-Object -First 1
    $drift = @($doc | Where-Object { $_ -match '^drift\s+' -and $_ -notmatch 'drift\s+swofty is not part of the game' })
    # primary signal: doctor's own "journal <id> is open" line; second: any file in the journal folder (any extension)
    $openIds = @($doc | Where-Object { $_ -match 'journal\s+(\S+)\s+is open' } | ForEach-Object { $Matches[1] })
    $files = @(Get-ChildItem $journals -File -Force -ErrorAction SilentlyContinue)
    $dll = $game -and (Test-Path (Join-Path $game 'version.dll'))
    [pscustomobject]@{ clean = (-not $drift.Count -and -not $openIds.Count -and -not $files.Count -and -not $dll)
        drift = $drift; openIds = $openIds; files = $files; dll = $dll }
}
function Show($s, [string] $when) {
    L "$when`: $(if ($s.clean) { 'CLEAN' } else { 'NOT CLEAN' }) (drift lines $($s.drift.Count), doctor's open journals $($s.openIds.Count) [$($s.openIds -join ',')], journal files $($s.files.Count), version.dll $(if ($s.dll) { 'present' } else { 'absent' }))"
    $s.drift | Select-Object -First 5 | ForEach-Object { L "  $_" }
}

$s = State
Show $s 'post-run'
if ($s.clean) { exit 0 }
if ($DoctorFile) { L 'test mode: no sidestep or restore'; exit 2 }

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
$side = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'storage_sidestep.ps1') -Ids ($ids -join ',') -Log $log
$sideCode = $LASTEXITCODE
if (-not $log) { $side }
if ($sideCode -ne 0) { L 'URGENT: the sidestep refused (see above); restore not tried. Stop all testing; Tyler must not launch the game.'; exit 2 }
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
