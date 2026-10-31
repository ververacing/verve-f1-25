<#
Fit the race-start draws of stock cars against their driver rows, pooled over several batches.

Usage:
    powershell -File tools/fit_start_model.ps1 -Runs "runs/<a>|8,19,...;runs/<b>|8,19,..." [-Out <dir>]

-Runs lists run folders (each with summary.csv) and, after "|", the vehicle ids to leave out of that batch (Ferrari
plus every car the batch modified). -Rows is a CSV of vehicle, driver, mistakes, reaction_speed (stock rows).

Models, by analogy with F-06 (k = a per-start factor, the same form for both draws):
  reaction  r ~ U[0.28 - 0.24*k*rs, 0.42 - 0.18*k*rs]   mean 0.35 - 0.21*k*rs
  bad start b ~ U[0.06 - 0.02*k*m,  0.42 - 0.14*k*m]    mean 0.24 - 0.08*k*m
where rs = row reaction_speed, m = row mistakes, b = 1 - race_start_performance/100 (F-38).
The bad-start form moves each min/max bound pair from its upper toward its lower bound with skill, as the reaction
bounds do. It is a hypothesis this script tests: it reports the pooled slope of b on m, k per start from each draw,
their correlation, and how many samples fall outside the k = 0 envelope ([0.06, 0.42] for b, [0.28, 0.42] shifted).
#>
param(
    [Parameter(Mandatory)] [string] $Runs,
    [string] $Rows = 'docs/stock/driver_rows_benchmark_austria.csv',
    [string] $Out = ''
)
$ErrorActionPreference = 'Stop'
function Slope([double[]] $x, [double[]] $y) {
    $mx = ($x | Measure-Object -Average).Average; $my = ($y | Measure-Object -Average).Average
    $sxy = 0.0; $sxx = 0.0
    for ($i = 0; $i -lt $x.Count; $i++) { $sxy += ($x[$i] - $mx) * ($y[$i] - $my); $sxx += ($x[$i] - $mx) * ($x[$i] - $mx) }
    [pscustomobject]@{ slope = $sxy / $sxx; intercept = $my - $sxy / $sxx * $mx }
}
function Corr([double[]] $x, [double[]] $y) {
    $mx = ($x | Measure-Object -Average).Average; $my = ($y | Measure-Object -Average).Average
    $sxy = 0.0; $sxx = 0.0; $syy = 0.0
    for ($i = 0; $i -lt $x.Count; $i++) { $sxy += ($x[$i] - $mx) * ($y[$i] - $my); $sxx += ($x[$i] - $mx) * ($x[$i] - $mx); $syy += ($y[$i] - $my) * ($y[$i] - $my) }
    $sxy / [math]::Sqrt($sxx * $syy)
}

$row = @{}; foreach ($r in Import-Csv $Rows) { $row[[string]$r.vehicle] = $r }
$samples = New-Object System.Collections.Generic.List[object]
foreach ($spec in ($Runs -split ';' | Where-Object { $_ })) {
    $dir, $ex = $spec -split '\|'
    $exclude = @($ex -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    $batch = Split-Path $dir -Leaf
    foreach ($s in Import-Csv (Join-Path $dir 'summary.csv')) {
        if ($exclude -contains [string]$s.vehicle) { continue }
        $rw = $row[[string]$s.vehicle]
        $samples.Add([pscustomobject]@{ batch = $batch; start = "$batch/$($s.start)"; vehicle = [int]$s.vehicle; driver = $rw.driver
            m = [double]$rw.mistakes; rs = [double]$rw.reaction_speed
            r = [double]$s.reaction_time; b = 1 - [double]$s.race_start_performance / 100 })
    }
}
"samples: $($samples.Count) from $(@($samples.start | Sort-Object -Unique).Count) starts"

# pooled slopes (k common): b on m -> slope = -0.08 k; r on rs -> slope = -0.21 k
$fb = Slope @($samples.m) @($samples.b); $fr = Slope @($samples.rs) @($samples.r)
"bad start: b = {0:N4} + {1:N4} * m   (model: 0.24 - 0.08k*m -> k = {2:N2}; intercept model 0.24)" -f $fb.intercept, $fb.slope, (-$fb.slope / 0.08)
"reaction:  r = {0:N4} + {1:N4} * rs  (model: 0.35 - 0.21k*rs -> k = {2:N2}; intercept model 0.35)" -f $fr.intercept, $fr.slope, (-$fr.slope / 0.21)

# k per start from each draw's mean (method of moments)
$perStart = foreach ($g in ($samples | Group-Object start)) {
    $mb = ($g.Group.b | Measure-Object -Average).Average; $mm = ($g.Group.m | Measure-Object -Average).Average
    $mr = ($g.Group.r | Measure-Object -Average).Average; $mrs = ($g.Group.rs | Measure-Object -Average).Average
    [pscustomobject]@{ start = $g.Name; n = $g.Count; mean_b = [math]::Round($mb, 4); k_bad = [math]::Round((0.24 - $mb) / (0.08 * $mm), 3)
        mean_r = [math]::Round($mr, 4); k_reaction = [math]::Round((0.35 - $mr) / (0.21 * $mrs), 3) }
}
$perStart | Format-Table -AutoSize
"corr(k_bad, k_reaction) over starts: {0:N2}" -f (Corr @($perStart.k_bad) @($perStart.k_reaction))
"mean k_bad {0:N3} (sd {1:N3}); mean k_reaction {2:N3} (sd {3:N3})" -f ($perStart.k_bad | Measure-Object -Average).Average,
    [math]::Sqrt((($perStart.k_bad | % { $_ * $_ } | Measure-Object -Average).Average) - [math]::Pow(($perStart.k_bad | Measure-Object -Average).Average, 2)),
    ($perStart.k_reaction | Measure-Object -Average).Average,
    [math]::Sqrt((($perStart.k_reaction | % { $_ * $_ } | Measure-Object -Average).Average) - [math]::Pow(($perStart.k_reaction | Measure-Object -Average).Average, 2))

# envelope: with k in [0, 1], b must lie in [0.06 - 0.02m, 0.42] and r in [0.28 - 0.24rs, 0.42]
$outB = @($samples | Where-Object { $_.b -lt (0.06 - 0.02 * $_.m) - 1e-6 -or $_.b -gt 0.42 + 1e-6 }).Count
$outR = @($samples | Where-Object { $_.r -lt (0.28 - 0.24 * $_.rs) - 1e-6 -or $_.r -gt 0.42 + 1e-6 }).Count
"b range {0:N4} .. {1:N4}; outside the k in [0,1] envelope: {2}" -f ($samples.b | Measure-Object -Minimum).Minimum, ($samples.b | Measure-Object -Maximum).Maximum, $outB
"r range {0:N4} .. {1:N4}; outside the k in [0,1] envelope: {2}" -f ($samples.r | Measure-Object -Minimum).Minimum, ($samples.r | Measure-Object -Maximum).Maximum, $outR

# within-start test: does b fall inside U[0.06 - 0.02 k m, 0.42 - 0.14 k m] with that start's k_bad?
$kb = @{}; foreach ($p in $perStart) { $kb[$p.start] = $p.k_bad }
$inside = @($samples | Where-Object { $k = $kb[$_.start]; $_.b -ge (0.06 - 0.02 * $k * $_.m) - 0.01 -and $_.b -le (0.42 - 0.14 * $k * $_.m) + 0.01 }).Count
"b inside its start's fitted interval (+-0.01): $inside of $($samples.Count)"

if ($Out) {
    New-Item -ItemType Directory -Force $Out | Out-Null
    $samples | Export-Csv -NoTypeInformation (Join-Path $Out 'start_model_samples.csv')
    $perStart | Export-Csv -NoTypeInformation (Join-Path $Out 'start_model_per_start.csv')
}
