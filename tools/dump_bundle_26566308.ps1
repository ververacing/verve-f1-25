<#
Quick stock dump for the V-1 bundle: each row's six driver_characteristics and the six ai_driver_config bundle keys,
read-only `swofty db get` (no --addon, so stock). The fast subset of tools/dump_drivers_26566308.ps1 (that one also
does ratings and all 84 keys, about 100 calls per driver; this one does 7).

Usage:
    powershell -File tools/dump_bundle_26566308.ps1 -Out docs/stock/bundle_26566308.csv [-Drivers a,b,c]

Default drivers: the 20 seats of the f1_2025 entrant list (entrant_list_15 on build 26566308) plus default_driver.
Refuses to start, and stops before the next driver (writing what it has, exit 9), if F1 25, the Swofty Launcher or
swofty-ui is running. Always passes --profile (default verve-test).
#>
param(
    [Parameter(Mandatory)] [string] $Out,
    [string] $Drivers = 'oscar_piastri,lando_norris,charles_leclerc,lewis_hamilton,max_verstappen,yuki_tsunoda,george_russell,andrea-kimi_antonelli,lance_stroll,fernando_alonso,pierre_gasly,franco_colapinto,esteban_ocon,oliver_bearman,liam_lawson,isack_hadjar,alex_albon,carlos_sainz-jr,nico_hulkenberg,gabriel_bortoleto,default_driver',
    [string] $Swofty = "$env:LOCALAPPDATA\Programs\SwoftyLauncher\bin\swofty.exe",
    [string] $Profile = 'verve-test',
    [switch] $NoHeader
)
$ErrorActionPreference = 'Continue'
function Test-Busy { [bool](Get-Process F1_25, swofty-launcher, swofty-ui -ErrorAction SilentlyContinue) }
if (Test-Busy) { 'F1 25, the Swofty Launcher or swofty-ui is running; not dumping'; exit 9 }
$chars = 'aggression', 'control', 'mistakes', 'reaction_speed', 'speed_in', 'speed_out'
$bundle = 'blocking.max_blocking_distance', 'blocking.max_blocking_distance_at_race_start', 'blocking.fraction_of_follow_speed',
          'blocking.fraction_of_follow_speed_at_race_start', 'overtake.overlap_percentage', 'alongside.yield_overtake_rate'
$lines = @()
if (-not $NoHeader) {
    $ver = (& $Swofty --version).Trim()
    $build = ((& $Swofty --profile $Profile doctor) | Where-Object { $_ -match '^build id\s+(\S+)' } | ForEach-Object { $Matches[1] })
    $lines += "# $ver | F1 25 build $build | stock values (no --addon) | profile $Profile | dumped $(Get-Date -Format 'yyyy-MM-dd') | <row>.driver_characteristics.* and <row>.ai_driver_config.<key>"
    $lines += '"row_label","row_index",' + (($chars + ($bundle | ForEach-Object { "ai.$_" }) | ForEach-Object { '"' + $_ + '"' }) -join ',')
}
$enc = New-Object System.Text.UTF8Encoding $false
$full = if ([IO.Path]::IsPathRooted($Out)) { $Out } else { Join-Path (Get-Location) $Out }
foreach ($d in @($Drivers -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })) {
    if (Test-Busy) { [IO.File]::WriteAllLines($full, $lines, $enc); 'STOPPED: F1 25 or the launcher is running; partial output written'; exit 9 }
    $dc = & $Swofty --profile $Profile db get "entrants.drivers.driver[_metadata_=$d].driver_characteristics" 2>$null
    $idx = if ($LASTEXITCODE -eq 0) { ($dc[0].Trim() -replace '^entrants\.drivers\.', '' -replace '\.driver_characteristics$', '') } else { 'MISSING' }
    $v = foreach ($k in $chars) {
        $m = $dc | Where-Object { $_ -match "^\s+$k\s+(\S+)\s*$" } | Select-Object -First 1
        if ($m -and $m -match "^\s+$k\s+(\S+)\s*$") { $Matches[1] } else { 'MISSING' }
    }
    $b = foreach ($k in $bundle) {
        $l = & $Swofty --profile $Profile db get "entrants.drivers.driver[_metadata_=$d].ai_driver_config.$k" 2>$null
        if ($LASTEXITCODE -eq 0) { (($l | Where-Object { $_ -match '^\s+value:' }) -replace '^\s+value:\s*', '') -join ' ' } else { 'MISSING' }
    }
    $lines += (@($d, $idx) + $v + $b | ForEach-Object { '"' + $_ + '"' }) -join ','
    "$d done"
}
[IO.File]::WriteAllLines($full, $lines, $enc)
"wrote $Out ($($lines.Count) lines)"
