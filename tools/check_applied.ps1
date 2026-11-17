<#
Deterministic build check (#53): the game, as it loaded, must hold exactly what the addon wrote.

Usage:
    powershell -File tools/check_applied.ps1 -Loader runs/<id>/raw/batches/1/loader.log -Folder harness/addons/verve.b0011
    powershell -File tools/check_applied.ps1 -PrefillOnly docs/stock/d1_paths.txt -KeyCache docs/stock/v1_key_cache_26566308.csv

`swofty db get --addon` only applies DB Editor addons, not data addons, so the check reads the game's own record of
the build instead: each start's loader.log has one `[assets] gamedb: overwrote 0x<key> (..., tag T type): OLD -> NEW`
line per changed record (a curve, tag 9, shows only `record at <address>`, so a curve op is checked for its key, not
its value). For every op in <Folder>/db/*.json, `swofty db get <select>.<field>` gives the key hash and
the stock value; the op must then have an overwrite line whose new value equals the op's value (floats within 1e-5;
strings, which the log shows as `label fnv32 0x...`, by FNV-1a 32 of the op's text). An op with no line is allowed
only when its value equals stock (the build dropped it). Prints the count every start must show: 52 baseline + the
ops found. Exit 0 = every op accounted for; 1 = a mismatch or a missing write (build broken: stop the batch).

-PrefillOnly <paths file> (one select.field path per line; blank and # lines skipped) only fills -KeyCache: each path
not cached yet gets one read-only `swofty db get --profile <Profile>` and is added. No loader.log, no add-on, no check.
Run it with nothing running (no game, launcher or swofty). Exit 0 = every path cached; 1 = a path had no key or hash.
Selftest: tools/test_check_applied.ps1 (a stub -Swofty, offline).
#>
param(
    [string] $Loader,   # required unless -PrefillOnly
    [string] $Folder,   # required unless -PrefillOnly
    [int] $Baseline = 52,
    [string] $Swofty = "$env:LOCALAPPDATA\Programs\SwoftyLauncher\bin\swofty.exe",
    # every db get names our test profile: never the active one, which is Tyler's (V-1 readback, 16 Nov)
    [string] $Profile = 'verve-test',
    # path,hash,stock cache (V-1: every launch writes the same 235 paths, only the values change): a cached path needs
    # no swofty call, so a launch's check runs offline in seconds; misses are looked up and added
    [string] $KeyCache = '',
    # a paths file: fill -KeyCache with these paths (db get for the missing ones), then exit; no loader check
    [string] $PrefillOnly = ''
)
if ($Profile -notlike 'verve-*') { throw "-Profile $Profile isn't one of ours (verve-*)" }
$ErrorActionPreference = 'Stop'
# one read-only db get: @{ row = path,hash,stock } or @{ why = 'NO KEY' / 'NO HASH' }
function LookUp([string] $path) {
    $out = & $Swofty db get --profile $Profile $path
    if ($LASTEXITCODE -ne 0) { return @{ why = 'NO KEY' } }
    if (-not (($out | Select-Object -First 1) -match '\((0x[0-9a-f]{16}), type \d+\)')) { return @{ why = 'NO HASH' } }
    $hash = $Matches[1]
    $stock = ($out | Where-Object { $_ -match '^\s*value: ' } | Select-Object -First 1) -replace '^\s*value: ', ''
    @{ row = [pscustomobject]@{ path = $path; hash = $hash; stock = $stock } }
}
if ($PrefillOnly) {
    if (-not $KeyCache) { throw '-PrefillOnly needs -KeyCache (the cache file to fill)' }
    if (-not (Test-Path $PrefillOnly)) { throw "no paths file $PrefillOnly" }
    $cache = [ordered]@{}
    if (Test-Path $KeyCache) { foreach ($r in Import-Csv $KeyCache) { $cache[$r.path] = $r } }
    $paths = @(Get-Content $PrefillOnly | ForEach-Object { $_.Trim() } | Where-Object { $_ -and -not $_.StartsWith('#') })
    $added = 0; $had = 0; $bad = 0
    foreach ($p in $paths) {
        if ($cache.Contains($p)) { $had++; continue }
        $r = LookUp $p
        if ($r.why) { $bad++; "$($r.why) $p"; continue }
        $cache[$p] = $r.row; $added++
    }
    if ($added) { $cache.Values | Sort-Object path | Export-Csv $KeyCache -NoTypeInformation -Encoding UTF8 }
    "prefill: $($paths.Count) path(s) in ${PrefillOnly}: $had already cached, $added looked up and added, $bad problem(s) ($($cache.Count) in $KeyCache)"
    exit $(if ($bad) { 1 } else { 0 })
}
if (-not $Loader -or -not $Folder) { throw 'pass -Loader and -Folder (or -PrefillOnly <paths file> -KeyCache <csv>)' }
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
$cache = @{}; $misses = 0
if ($KeyCache -and (Test-Path $KeyCache)) { foreach ($r in Import-Csv $KeyCache) { $cache[$r.path] = $r } }
foreach ($o in $ops) {
    $path = "$($o.select).$($o.field)"
    if ($cache.ContainsKey($path)) {
        $hash = $cache[$path].hash; $stock = $cache[$path].stock
    } else {
        $misses++
        $r = LookUp $path
        if ($r.why) { $bad++; "$($r.why) $path"; continue }
        $cache[$path] = $r.row; $hash = $r.row.hash; $stock = $r.row.stock
    }
    if ($over.ContainsKey($hash)) {
        $found++
        if ($over[$hash].new -match '^record at ') { $unread++; continue }
        if (-not (SameValue $over[$hash].new "$($o.value)")) { $bad++; "MISMATCH $path ($hash): wrote $($o.value), game has $($over[$hash].new)" }
    } elseif (SameValue $stock "$($o.value)") { $dropped++; $droppedBy[$o.field] = 1 + [int]$droppedBy[$o.field] }
    else { $bad++; "MISSING $path ($hash): wrote $($o.value), stock $stock, no overwrite line" }
}
if ($KeyCache -and $misses) { $cache.Values | Sort-Object path | Export-Csv $KeyCache -NoTypeInformation -Encoding UTF8; "key cache: $misses path(s) looked up and added ($($cache.Count) in $KeyCache)" }
elseif ($KeyCache) { "key cache: all $($ops.Count) paths cached (no swofty call)" }
$expect = $Baseline + $found
"ops $($ops.Count): $found applied ($($found - $unread) value-checked, $unread curves written at the right key but their value isn't logged), $dropped dropped as equal to stock ($(($droppedBy.GetEnumerator() | ForEach-Object { "$($_.Key) $($_.Value)" }) -join ', ')), $bad problem(s)"
"loader total $total overwritten; expected $Baseline + $found = $expect$(if ($total -ne $expect) { ' (DIFFERS: something else wrote records)' })"
exit $(if ($bad -or $total -ne $expect) { 1 } else { 0 })
