<#
B-0001 (#30) readout: arm medians relative to each start's stock field, and the verdict by the criterion fixed in
#30 before the run.

Usage:
    powershell -File tools/b0001_readout.ps1 -Summary runs/<id>/summary.csv -Out runs/<id>

Arms by team stat_id: ROW_slow Alpine 5, ROW_fast McLaren 8, STATS_slow Sauber 9, STATS_fast Racing Bulls 6.
Stock field = every other car except Ferrari (team 1, holding vehicle 19). Each sample is reaction_time minus its
start's stock-field median.
#>
param(
    [Parameter(Mandatory)] [string] $Summary,
    [Parameter(Mandatory)] [string] $Out,
    [double] $Win = 0.06,
    [double] $Lose = 0.03
)
$ErrorActionPreference = 'Stop'
function Median([double[]] $v) { $s = $v | Sort-Object; $n = $s.Count; if ($n % 2) { $s[($n - 1) / 2] } else { ($s[$n / 2 - 1] + $s[$n / 2]) / 2 } }
$arms = @{ 5 = 'ROW_slow (Alpine)'; 8 = 'ROW_fast (McLaren)'; 9 = 'STATS_slow (Sauber)'; 6 = 'STATS_fast (Racing Bulls)' }
$rows = Import-Csv $Summary | ForEach-Object { $_.team_id = [int]$_.team_id; $_.start = [int]$_.start; $_.reaction_time = [double]$_.reaction_time; $_ }
$fieldMed = @{}
foreach ($g in ($rows | Group-Object start)) {
    $fieldMed[[int]$g.Name] = Median ([double[]]($g.Group | Where-Object { $_.team_id -notin @(1, 5, 6, 8, 9) } | ForEach-Object reaction_time))
}
$res = foreach ($t in 5, 8, 9, 6) {
    $x = $rows | Where-Object team_id -eq $t
    $rel = [double[]]($x | ForEach-Object { $_.reaction_time - $fieldMed[$_.start] })
    $abs = [double[]]($x | ForEach-Object reaction_time)
    [pscustomobject]@{ arm = $arms[$t]; team_id = $t; n = $rel.Count; median_rel = [math]::Round((Median $rel), 4)
        min_rel = [math]::Round(($rel | Measure-Object -Minimum).Minimum, 4); max_rel = [math]::Round(($rel | Measure-Object -Maximum).Maximum, 4)
        median_abs = [math]::Round((Median $abs), 4) }
}
$m = @{}; foreach ($r in $res) { $m[$r.team_id] = $r.median_rel }
$rowGap = [math]::Round($m[5] - $m[8], 4); $statsGap = [math]::Round($m[9] - $m[6], 4)
$verdict = if ($rowGap -ge $Win -and $statsGap -lt $Lose) { 'ROW WINS (in benchmark)' }
           elseif ($statsGap -ge $Win -and $rowGap -lt $Lose) { 'RATINGS WIN (in benchmark)' }
           else { 'INCONCLUSIVE / BLENDED' }
$enc = New-Object System.Text.UTF8Encoding $false
[IO.File]::WriteAllLines((Join-Path (Resolve-Path $Out) 'arms.csv'), [string[]]($res | ConvertTo-Csv -NoTypeInformation), $enc)
$fs = foreach ($k in ($fieldMed.Keys | Sort-Object)) { [pscustomobject]@{ start = $k; stock_field_median = [math]::Round($fieldMed[$k], 4) } }
[IO.File]::WriteAllLines((Join-Path (Resolve-Path $Out) 'stock_field.csv'), [string[]]($fs | ConvertTo-Csv -NoTypeInformation), $enc)
$res | Format-Table -AutoSize | Out-String
$fs | Format-Table -AutoSize | Out-String
"ROW pair gap (Alpine - McLaren): $rowGap s;  STATS pair gap (Sauber - Racing Bulls): $statsGap s"
"criterion: winner >= $Win s, loser < $Lose s (or reversed)  ->  $verdict"
