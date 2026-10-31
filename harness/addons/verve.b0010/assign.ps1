<#
B-0010 assignment (#8): 2x2 crossed reaction_speed x mistakes, row values only, 2 drivers per cell.

Usage (from the repo root):
    powershell -File harness/addons/verve.b0010/assign.ps1

System.Random seed 10010; each draw is a Fisher-Yates shuffle of the 18 non-Ferrari drivers (vehicle order) and
takes the first 8: drivers 1-2 -> rs 0.10 / m 0.10, 3-4 -> rs 0.10 / m 0.90, 5-6 -> rs 0.90 / m 0.10,
7-8 -> rs 0.90 / m 0.90. A draw is accepted when, for stock row reaction_speed and for stock row mistakes separately,
the cell means span at most 0.10 (the pre-registered constraint). Writes arms.csv and db/b0010.json next to this file.
#>
$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$rows = Import-Csv (Join-Path $here '..\..\..\docs\stock\driver_rows_benchmark_austria.csv') | Where-Object { $_.vehicle -notin '8', '19' }
$cells = @(@{ rs = 0.10; m = 0.10 }, @{ rs = 0.10; m = 0.90 }, @{ rs = 0.90; m = 0.10 }, @{ rs = 0.90; m = 0.90 })
$rng = New-Object System.Random 10010
for ($draw = 1; $draw -le 100000; $draw++) {
    $p = @($rows)
    for ($i = $p.Count - 1; $i -gt 0; $i--) { $j = $rng.Next(0, $i + 1); $t = $p[$i]; $p[$i] = $p[$j]; $p[$j] = $t }
    $rsMeans = @(); $mMeans = @()
    for ($c = 0; $c -lt 4; $c++) {
        $rsMeans += ([double]$p[2 * $c].reaction_speed + [double]$p[2 * $c + 1].reaction_speed) / 2
        $mMeans += ([double]$p[2 * $c].mistakes + [double]$p[2 * $c + 1].mistakes) / 2
    }
    $rsSpan = ($rsMeans | Measure-Object -Maximum).Maximum - ($rsMeans | Measure-Object -Minimum).Minimum
    $mSpan = ($mMeans | Measure-Object -Maximum).Maximum - ($mMeans | Measure-Object -Minimum).Minimum
    if ($rsSpan -le 0.10 + 1e-9 -and $mSpan -le 0.10 + 1e-9) { break }
}
"accepted on draw $draw; cell-mean span: stock rs $([math]::Round($rsSpan, 3)), stock mistakes $([math]::Round($mSpan, 3))"
$arms = for ($c = 0; $c -lt 4; $c++) {
    foreach ($d in $p[(2 * $c)..(2 * $c + 1)]) {
        $cl = $cells[$c]
        [pscustomobject]@{ key = $d.vehicle; arm = ('rs{0:0.00}_m{1:0.00}' -f $cl.rs, $cl.m); rs = $cl.rs; m = $cl.m; driver = $d.driver
            stock_rs = $d.reaction_speed; stock_m = $d.mistakes }
    }
}
$arms | Export-Csv (Join-Path $here 'arms.csv') -NoTypeInformation
$ops = foreach ($a in $arms) {
    foreach ($f in @(@('reaction_speed', $a.rs), @('mistakes', $a.m))) {
        [ordered]@{ op = 'set'; select = "entrants.drivers.driver[_metadata_=$($a.driver)]"; field = "driver_characteristics.$($f[0])"; value = ('{0:0.00}' -f $f[1]) }
    }
}
New-Item -ItemType Directory -Force (Join-Path $here 'db') | Out-Null
[IO.File]::WriteAllText((Join-Path $here 'db\b0010.json'), ([ordered]@{ schema_version = 1; ops = @($ops) } | ConvertTo-Json -Depth 5), (New-Object System.Text.UTF8Encoding $false))
# ops whose value equals the stock row are dropped by the build (docs/harness.md), so they don't count as overwrites
$same = @($arms | ForEach-Object { if ([double]$_.stock_rs -eq $_.rs) { 1 }; if ([double]$_.stock_m -eq $_.m) { 1 } }).Count
"ops: $(@($ops).Count), equal to stock: $same, expect overwritten: $(52 + @($ops).Count - $same)"
$arms | Format-Table -AutoSize | Out-String
