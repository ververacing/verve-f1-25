<#
Dump the 84 per-driver ai_driver_config keys for some drivers, one column per driver, as CSV.

The keys are not in the launcher's name catalogue, so `swofty db get` does not list them under the driver row, but a
full dotted path resolves by hash. Key names come from docs/ai_driver_config_keys.csv.

Usage:
    powershell -File tools/dump_ai_driver_config.ps1 -Drivers default_driver,max_verstappen -Out docs/stock/ai_driver_config.csv
#>
param(
    [Parameter(Mandatory)] [string] $Drivers,   # comma-separated driver labels
    [Parameter(Mandatory)] [string] $Out,
    [string] $Catalogue = "docs/ai_driver_config_keys.csv",
    [string] $Swofty = "$env:LOCALAPPDATA\Programs\SwoftyLauncher\bin\swofty.exe"
)
# 'Continue', not 'Stop': swofty reports a missing key on stderr, which must not abort the dump
$ErrorActionPreference = 'Continue'
$DriverList = @($Drivers -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
$keys = Import-Csv $Catalogue
$rows = foreach ($k in $keys) {
    $row = [ordered]@{ key = "ai_driver_config.$($k.group).$($k.leaf)"; type = $k.type }
    foreach ($d in $DriverList) {
        $lines = & $Swofty db get "entrants.drivers.driver[_metadata_=$d].ai_driver_config.$($k.group).$($k.leaf)" 2>$null
        $v = if ($LASTEXITCODE -eq 0) { (($lines | Where-Object { $_ -match '^\s+value:' }) -replace '^\s+value:\s*', '') -join ' ' } else { 'MISSING' }
        $row[$d] = $v
    }
    $row['identical'] = (@($DriverList | ForEach-Object { $row[$_] } | Select-Object -Unique).Count -eq 1)
    [pscustomobject]$row
}
$full = if ([IO.Path]::IsPathRooted($Out)) { $Out } else { Join-Path (Get-Location) $Out }
$csv = $rows | ConvertTo-Csv -NoTypeInformation
[IO.File]::WriteAllLines($full, $csv, (New-Object System.Text.UTF8Encoding $false))
"wrote $Out ($($rows.Count) keys x $($DriverList.Count) drivers); differing keys: $(@($rows | Where-Object { -not $_.identical }).Count)"
