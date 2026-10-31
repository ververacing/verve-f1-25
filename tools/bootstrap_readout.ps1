<#
Bootstrap readout for race batches: resample whole starts (the per-start level k makes samples inside one start
correlated), and report each statistic's point estimate and bootstrap SE.

Usage:
    powershell -File tools/bootstrap_readout.ps1 -Summary runs/<id>/summary.csv -Arms <arms.csv> -Mode pairs -Pairs "ROW_slow-ROW_fast,STATS_slow-STATS_fast"
    powershell -File tools/bootstrap_readout.ps1 -Summary runs/<id>/summary.csv -Arms <arms.csv> -Mode slope

-Arms is a CSV with columns: key (a team_id or vehicle id, per -By), arm, source (e.g. ROW / STATS), level (number;
slope mode only). Every car whose key is not in -Arms and not in -Exclude is the stock field. Each sample is
the metric (-Metric: reaction_time or race_start_performance) minus its start's stock-field median.

pairs: for each "A-B", median(rel of arm A) - median(rel of arm B).
slope: per source, the least-squares slope of rel on level.
SE = standard deviation over -N resamples of the starts, drawn with replacement (seed -Seed). A statistic "passes"
when |estimate| >= 2 SE; the caller's criterion decides what passing means.
#>
param(
    [Parameter(Mandatory)] [string] $Summary,
    [Parameter(Mandatory)] [string] $Arms,
    [ValidateSet('pairs', 'slope')] [string] $Mode = 'pairs',
    [string] $Pairs = '',
    [ValidateSet('team_id', 'vehicle')] [string] $By = 'team_id',
    [ValidateSet('reaction_time', 'race_start_performance')] [string] $Metric = 'reaction_time',
    [string[]] $Exclude = @('1'),
    [int] $N = 2000,
    [int] $Seed = 1,
    [string] $Out = ''
)
$ErrorActionPreference = 'Stop'
# `powershell -File ... -Exclude 8,19` passes one string "8,19"; split it
$Exclude = @($Exclude | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ })
function Median([double[]] $v) { $s = $v | Sort-Object; $n = $s.Count; if ($n -eq 0) { return [double]::NaN }; if ($n % 2) { $s[($n - 1) / 2] } else { ($s[$n / 2 - 1] + $s[$n / 2]) / 2 } }
function Slope([double[]] $x, [double[]] $y) {
    $mx = ($x | Measure-Object -Average).Average; $my = ($y | Measure-Object -Average).Average
    $sxy = 0.0; $sxx = 0.0
    for ($i = 0; $i -lt $x.Count; $i++) { $sxy += ($x[$i] - $mx) * ($y[$i] - $my); $sxx += ($x[$i] - $mx) * ($x[$i] - $mx) }
    if ($sxx -eq 0) { return [double]::NaN }; $sxy / $sxx
}

$armMap = @{}; foreach ($a in Import-Csv $Arms) { $armMap[[string]$a.key] = $a }
$byStart = @{}
foreach ($r in Import-Csv $Summary) {
    $st = [int]$r.start
    if (-not $byStart.ContainsKey($st)) { $byStart[$st] = New-Object System.Collections.Generic.List[object] }
    $byStart[$st].Add([pscustomobject]@{ key = [string]$r.$By; rt = [double]$r.$Metric })
}
# per start: relative samples of armed cars
$rel = @{}
foreach ($st in $byStart.Keys) {
    $field = Median ([double[]]($byStart[$st] | Where-Object { -not $armMap.ContainsKey($_.key) -and $_.key -notin $Exclude } | ForEach-Object rt))
    $rel[$st] = @($byStart[$st] | Where-Object { $armMap.ContainsKey($_.key) } | ForEach-Object {
        $a = $armMap[$_.key]; [pscustomobject]@{ arm = $a.arm; source = $a.source; level = $(if ($a.level) { [double]$a.level } else { 0.0 }); rel = $_.rt - $field } })
}
$starts = @($rel.Keys | Sort-Object)

function Stats($sampleStarts) {
    $all = foreach ($st in $sampleStarts) { $rel[$st] }
    $res = [ordered]@{}
    if ($Mode -eq 'pairs') {
        foreach ($p in ($Pairs -split ',' | Where-Object { $_ })) {
            $ab = $p -split '-', 2
            $ma = Median ([double[]]($all | Where-Object arm -eq $ab[0] | ForEach-Object rel))
            $mb = Median ([double[]]($all | Where-Object arm -eq $ab[1] | ForEach-Object rel))
            $res[$p] = $ma - $mb
        }
    } else {
        foreach ($src in ($all | ForEach-Object source | Sort-Object -Unique)) {
            $pts = @($all | Where-Object source -eq $src)
            $res["slope_$src"] = Slope ([double[]]($pts | ForEach-Object level)) ([double[]]($pts | ForEach-Object rel))
        }
    }
    $res
}

$point = Stats $starts
$rng = New-Object System.Random $Seed
$boot = @{}; foreach ($k in $point.Keys) { $boot[$k] = New-Object System.Collections.Generic.List[double] }
for ($b = 0; $b -lt $N; $b++) {
    $pick = for ($i = 0; $i -lt $starts.Count; $i++) { $starts[$rng.Next(0, $starts.Count)] }
    $s = Stats $pick
    foreach ($k in $s.Keys) { if (-not [double]::IsNaN($s[$k])) { $boot[$k].Add($s[$k]) } }
}
$rows = foreach ($k in $point.Keys) {
    $v = $boot[$k]; $m = ($v | Measure-Object -Average).Average
    $se = [math]::Sqrt((($v | ForEach-Object { ($_ - $m) * ($_ - $m) } | Measure-Object -Sum).Sum) / [math]::Max(1, $v.Count - 1))
    [pscustomobject]@{ statistic = $k; estimate = [math]::Round($point[$k], 4); boot_se = [math]::Round($se, 4)
        z = [math]::Round($point[$k] / $(if ($se -gt 0) { $se } else { [double]::NaN }), 2); passes_2se = ([math]::Abs($point[$k]) -ge 2 * $se); starts = $starts.Count; resamples = $v.Count }
}
if ($Out) { [IO.File]::WriteAllLines($Out, [string[]]($rows | ConvertTo-Csv -NoTypeInformation), (New-Object System.Text.UTF8Encoding $false)) }
$rows | Format-Table -AutoSize | Out-String
