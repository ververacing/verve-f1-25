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
    [string] $Swofty = "$env:LOCALAPPDATA\Programs\SwoftyLauncher\bin\swofty.exe"
)
$ErrorActionPreference = 'Stop'
$log = if ($Out) { New-Item -ItemType Directory -Force $Out | Out-Null; Join-Path $Out 'post_run_check.txt' } else { '' }
function L([string] $s) { $s = $s.Replace($env:USERPROFILE, '%USERPROFILE%'); $s; if ($log) { Add-Content $log $s -Encoding utf8 } }
$journals = Join-Path $env:LOCALAPPDATA 'Swofty\state\journal'

function State {
    $doc = & $Swofty doctor
    $game = $doc | Where-Object { $_ -match '^game dir\s+(.+)$' } | ForEach-Object { $Matches[1].Trim() } | Select-Object -First 1
    $drift = @($doc | Where-Object { $_ -match '^drift\s+' -and $_ -notmatch 'drift\s+swofty is not part of the game' })
    $open = @(Get-ChildItem $journals -Filter *.json -ErrorAction SilentlyContinue)
    $dll = $game -and (Test-Path (Join-Path $game 'version.dll'))
    [pscustomobject]@{ clean = (-not $drift.Count -and -not $open.Count -and -not $dll); drift = $drift; open = $open; dll = $dll }
}
function Show($s, [string] $when) {
    L "$when`: $(if ($s.clean) { 'CLEAN' } else { 'NOT CLEAN' }) (drift lines $($s.drift.Count), open journals $($s.open.Count), version.dll $(if ($s.dll) { 'present' } else { 'absent' }))"
    $s.drift | Select-Object -First 5 | ForEach-Object { L "  $_" }
}

$s = State
Show $s 'post-run'
if ($s.clean) { exit 0 }

# the open journal's addons are the ones restore's rollback will swap (game swofty/addons/<id>; core = swofty.core)
$ids = foreach ($j in $s.open) {
    (Get-Content $j.FullName -Raw | ConvertFrom-Json).entries | Where-Object { $_.path -match '^swofty/addons/([^/]+)$' } |
        ForEach-Object { if ($Matches[1] -eq 'core') { 'swofty.core' } else { $Matches[1] } }
}
$ids = @($ids | Select-Object -Unique)
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
