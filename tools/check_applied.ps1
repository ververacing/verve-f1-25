<#
Deterministic build check (#53): the game, as it loaded, must hold exactly what the addon wrote.

Usage:
    powershell -File tools/check_applied.ps1 -Loader runs/<id>/raw/batches/1/loader.log -Folder harness/addons/verve.b0011

`swofty db get --addon` only applies DB Editor addons, not data addons, so the check reads the game's own record of
the build instead: each start's loader.log has one `[assets] gamedb: overwrote 0x<key> (..., tag T type): OLD -> NEW`
line per changed record (a curve, tag 9, shows only `record at <address>`, so a curve op is checked for its key, not
its value). For every op in <Folder>/db/*.json, `swofty db get <select>.<field>` gives the key hash and
the stock value; the op must then have an overwrite line whose new value equals the op's value (floats within 1e-5;
strings, which the log shows as `label fnv32 0x...`, by FNV-1a 32 of the op's text). An op with no line is allowed
only when its value equals stock (the build dropped it). Prints the count every start must show: 52 baseline + the
ops found. Exit 0 = every op accounted for; 1 = a mismatch or a missing write (build broken: stop the batch).
#>
param(
    [Parameter(Mandatory)] [string] $Loader,
    [Parameter(Mandatory)] [string] $Folder,
    [int] $Baseline = 52,
    [string] $Swofty = "$env:LOCALAPPDATA\Programs\SwoftyLauncher\bin\swofty.exe"
)
$ErrorActionPreference = 'Stop'
$inv = [Globalization.CultureInfo]::InvariantCulture
function Fnv1a([string] $s) { $h = [uint32]2166136261; foreach ($b in [Text.Encoding]::UTF8.GetBytes($s)) { $h = [uint32](([uint64]($h -bxor $b) * 16777619) % 4294967296) }; '0x{0:x8}' -f $h }
function SameValue([string] $logged, [string] $value) {
    if ($logged -match '^label fnv32 (0x[0-9a-f]{8})' -or $logged -match 'label fnv32 (0x[0-9a-f]{8})') { return $Matches[1] -eq (Fnv1a $value) }
    $a = 0.0; $b = 0.0
    if ([double]::TryParse($logged, [Globalization.NumberStyles]::Float, $inv, [ref]$a) -and [double]::TryParse($value, [Globalization.NumberStyles]::Float, $inv, [ref]$b)) { return [math]::Abs($a - $b) -lt 1e-5 }
    $logged -eq $value
}

$over = @{}
foreach ($l in Get-Content $Loader) {
    if ($l -match 'gamedb: overwrote (0x[0-9a-f]{16}) \(key [^,]+, tag \d+ \w+\): (.*) -> (.*)$') { $over[$Matches[1]] = @{ old = $Matches[2]; new = $Matches[3] } }
    elseif ($l -match 'gamedb: (\d+) overwritten') { $total = [int]$Matches[1] }
}
$ops = foreach ($f in Get-ChildItem (Join-Path $Folder 'db') -Filter *.json) { (Get-Content $f.FullName -Raw | ConvertFrom-Json).ops }
$found = 0; $dropped = 0; $bad = 0; $unread = 0; $droppedBy = @{}
foreach ($o in $ops) {
    $path = "$($o.select).$($o.field)"
    $out = & $Swofty db get $path
    if ($LASTEXITCODE -ne 0) { $bad++; "NO KEY $path"; continue }
    if (-not (($out | Select-Object -First 1) -match '\((0x[0-9a-f]{16}), type \d+\)')) { $bad++; "NO HASH $path"; continue }
    $hash = $Matches[1]
    $stock = ($out | Where-Object { $_ -match '^\s*value: ' } | Select-Object -First 1) -replace '^\s*value: ', ''
    if ($over.ContainsKey($hash)) {
        $found++
        if ($over[$hash].new -match '^record at ') { $unread++; continue }
        if (-not (SameValue $over[$hash].new "$($o.value)")) { $bad++; "MISMATCH $path ($hash): wrote $($o.value), game has $($over[$hash].new)" }
    } elseif (SameValue $stock "$($o.value)") { $dropped++; $droppedBy[$o.field] = 1 + [int]$droppedBy[$o.field] }
    else { $bad++; "MISSING $path ($hash): wrote $($o.value), stock $stock, no overwrite line" }
}
$expect = $Baseline + $found
"ops $($ops.Count): $found applied ($($found - $unread) value-checked, $unread curves written at the right key but their value isn't logged), $dropped dropped as equal to stock ($(($droppedBy.GetEnumerator() | ForEach-Object { "$($_.Key) $($_.Value)" }) -join ', ')), $bad problem(s)"
"loader total $total overwritten; expected $Baseline + $found = $expect$(if ($total -ne $expect) { ' (DIFFERS: something else wrote records)' })"
exit $(if ($bad -or $total -ne $expect) { 1 } else { 0 })
