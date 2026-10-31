<#
Deterministic build check before a validation batch (#53): the game database, with the addon's changes, must hold
exactly what the generator wrote.

Usage:
    powershell -File tools/check_build.ps1 -Addon verve.b0011 -Folder harness/addons/verve.b0011 -Drivers max_verstappen,lance_stroll,alex_albon

For each driver, `swofty db get --addon <id>` on the row's driver_characteristics and on its pace Statistic in both
datasets is compared with the addon's own db ops (numbers compared as numbers, curves point by point). The addon must
be installed. Exit 0 = every value matches; 1 = a mismatch (build broken: stop the batch).
#>
param(
    [Parameter(Mandatory)] [string] $Addon,
    [Parameter(Mandatory)] [string] $Folder,
    [Parameter(Mandatory)] [string[]] $Drivers,
    [string] $Swofty = "$env:LOCALAPPDATA\Programs\SwoftyLauncher\bin\swofty.exe"
)
$ErrorActionPreference = 'Stop'
$Drivers = @($Drivers | ForEach-Object { $_ -split ',' } | Where-Object { $_ })
$inv = [Globalization.CultureInfo]::InvariantCulture
$ops = (Get-Content (Join-Path $Folder 'db\verve.json') -Raw | ConvertFrom-Json).ops
function Points([string] $e) { @($e -split ',' | Select-Object -Skip 1 | Where-Object { $_ -notmatch '^(maxx|miny|maxy):' } | ForEach-Object { $p = $_ -split ':'; [double]::Parse($p[0], $inv), [double]::Parse($p[1], $inv) }) }
function Value([string] $path, [string] $key) {
    $out = & $Swofty db get --addon $Addon $path
    if ($LASTEXITCODE -ne 0) { throw "db get failed: $path" }
    $m = $out | Select-String -Pattern "^\s*$([regex]::Escape($key))\s+(\S+)\s*$" | Select-Object -First 1
    if ($m) { $m.Matches[0].Groups[1].Value } else { $null }
}
$bad = 0; $n = 0
foreach ($d in $Drivers) {
    $row = "entrants.drivers.driver[_metadata_=$d]"
    foreach ($o in $ops | Where-Object { $_.select -eq $row }) {
        $field = $o.field -replace '^driver_characteristics\.', ''
        $got = Value "$row.driver_characteristics" $field
        $ok = $null -ne $got -and [math]::Abs([double]::Parse($got, $inv) - [double]::Parse($o.value, $inv)) -lt 1e-6
        $n++; if (-not $ok) { $bad++; "MISMATCH $d $($o.field): wrote $($o.value), game has $got" }
    }
    $holder = ($ops | Where-Object { $_.field -eq 'evolution' -and $_.select -match "driver=$([regex]::Escape($d))\]" })
    if (-not $holder -and $d -eq 'alex_albon') { $holder = $ops | Where-Object { $_.field -eq 'evolution' -and $_.select -match 'driver=alex_albon\]' } }
    foreach ($o in $holder) {
        $got = Value $o.select 'evolution'
        $a = Points $o.value; $b = if ($got) { Points $got } else { @() }
        $ok = $a.Count -eq $b.Count -and -not (0..($a.Count - 1) | Where-Object { [math]::Abs($a[$_] - $b[$_]) -gt 1e-6 })
        $n++; if (-not $ok) { $bad++; "MISMATCH $d pace ($($o.select -replace '.*_metadata_=([^\]]+)\]\.Statistic.*', '$1')): wrote $($o.value), game has $got" }
    }
}
"checked $n values for $($Drivers.Count) drivers: $(if ($bad) { "$bad MISMATCH(ES): build broken" } else { 'all match the generator output' })"
exit $(if ($bad) { 1 } else { 0 })
