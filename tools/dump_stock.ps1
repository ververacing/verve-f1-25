<#
Recursively dump stock game-database values with `swofty db get` (no --addon, so stock).

Usage:
    powershell -File tools/dump_stock.ps1 -Path "entrants.drivers.driver[_metadata_=max_verstappen]" -Out docs/stock/driver_max_verstappen.txt
    powershell -File tools/dump_stock.ps1 -Path "<path>" -Out <file> -MaxDepth 4

`swofty db get` lists one level: "  key  value" lines, an empty value for a container, "table, N rows" for a table
(whose listing names its rows, which live beside it as <table>_N). This walks both, indenting by depth.
#>
param(
    [Parameter(Mandatory)] [string] $Path,
    [Parameter(Mandatory)] [string] $Out,
    [int] $MaxDepth = 8,
    [int] $MaxNodes = 5000,
    [string] $Swofty = "$env:LOCALAPPDATA\Programs\SwoftyLauncher\bin\swofty.exe"
)
$ErrorActionPreference = 'Stop'
$script:nodes = 0
$sb = New-Object System.Text.StringBuilder

function Get-Level([string] $p) {
    $lines = & $Swofty db get $p
    if ($LASTEXITCODE -ne 0) { return $null }
    $resolved = $lines[0].Trim()
    $items = foreach ($l in $lines | Select-Object -Skip 1) {
        $parts = $l.Trim() -split '\s{2,}', 2
        if ($parts.Count -eq 1 -and $l -match '^\s{2}\S+\s*$') { $parts = @($parts[0], '') }
        if ($parts.Count -eq 2) { [pscustomobject]@{ Key = $parts[0]; Value = $parts[1] } }
    }
    [pscustomobject]@{ Resolved = $resolved; Items = @($items); Raw = @($lines | Select-Object -Skip 1) }
}

function Walk([string] $p, [int] $depth) {
    $script:nodes++
    if ($script:nodes -gt $MaxNodes) { [void]$sb.AppendLine(('  ' * $depth) + "... node limit $MaxNodes reached"); return }
    $lvl = Get-Level $p
    if (-not $lvl) { [void]$sb.AppendLine(('  ' * $depth) + "!! $p : not in the game database"); return }
    $base = $lvl.Resolved
    # a leaf prints "path (0x<hash>, type N)" then "value: ..."; an empty list shows as "value:" with nothing after
    if ($base -match '\(0x[0-9a-f]{16}, type \d+\)') {
        foreach ($l in $lvl.Raw) { [void]$sb.AppendLine(('  ' * $depth) + $l.Trim()) }
        return
    }
    foreach ($it in $lvl.Items) {
        $pad = '  ' * $depth
        if ($it.Value -match '^table, \d+ rows$') {
            [void]$sb.AppendLine("$pad$($it.Key)  [$($it.Value)]")
            if ($depth -ge $MaxDepth) { continue }
            $rows = Get-Level "$base.$($it.Key)"
            foreach ($row in $rows.Items) {
                [void]$sb.AppendLine("$pad  $($row.Key)  ($($row.Value))")
                Walk "$base.$($row.Key)" ($depth + 2)
            }
        } elseif ($it.Value -eq '') {
            [void]$sb.AppendLine("$pad$($it.Key)")
            if ($depth -lt $MaxDepth) { Walk "$base.$($it.Key)" ($depth + 1) }
        } else {
            [void]$sb.AppendLine("$pad$($it.Key)  $($it.Value)")
        }
    }
}

$ver = (& $Swofty --version) -replace '^swofty\s+', ''
[void]$sb.AppendLine("# swofty $ver | stock values (no --addon) | dumped $(Get-Date -Format yyyy-MM-dd)")
[void]$sb.AppendLine("# root: $Path")
$first = Get-Level $Path
if ($first) { [void]$sb.AppendLine("# resolved: $($first.Resolved)") }
Walk $Path 0
$enc = New-Object System.Text.UTF8Encoding $false
$full = if ([IO.Path]::IsPathRooted($Out)) { $Out } else { Join-Path (Get-Location) $Out }
New-Item -ItemType Directory -Force (Split-Path $full) | Out-Null
[IO.File]::WriteAllText($full, $sb.ToString(), $enc)
"wrote $Out ($script:nodes nodes)"
