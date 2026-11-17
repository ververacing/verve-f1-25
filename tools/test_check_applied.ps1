<#
Selftest for tools/check_applied.ps1 -PrefillOnly and its offline build check, with a stub -Swofty script and files in
%TEMP% only (never the real key cache, never swofty).
    powershell -File tools/test_check_applied.ps1 [-Python python]     # exit 0 = all ok
The stub answers `db get --profile verve-* <path>` with a fake `<path> (0x<16 hex>, type 3)` line (the hash is the
first 8 bytes of the path's SHA-256) and a `  value: 0.28` line; a path containing 'nosuch' is exit 1 (no key).
#>
param([string] $Python = 'python')
$ErrorActionPreference = 'Stop'
$tool = Join-Path $PSScriptRoot 'check_applied.ps1'
$paths = Join-Path (Split-Path $PSScriptRoot -Parent) 'docs\stock\d1_paths.txt'
$d = Join-Path $env:TEMP ("ca-test-" + [guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory $d | Out-Null
$fails = 0
function Check([string] $name, [bool] $ok, [string] $detail = '') {
    if ($ok) { "ok   $name" } else { $script:fails++; "FAIL $name $detail" }
}
$utf8 = New-Object Text.UTF8Encoding $false
$stub = Join-Path $d 'swofty_stub.ps1'
$calls = Join-Path $d 'calls.txt'
[IO.File]::WriteAllText($stub, @'
Add-Content (Join-Path $PSScriptRoot 'calls.txt') ($args -join ' ')
if ($args.Count -ne 5 -or $args[0] -ne 'db' -or $args[1] -ne 'get' -or $args[2] -ne '--profile' -or $args[3] -notlike 'verve-*') { 'stub: unexpected call'; exit 2 }
$p = $args[4]
if ($p -match 'nosuch') { "error: no record at $p"; exit 1 }
$sha = [Security.Cryptography.SHA256]::Create()
$h = -join ($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($p))[0..7] | ForEach-Object { $_.ToString('x2') })
"$p (0x$h, type 3)"
'  value: 0.28'
exit 0
'@, $utf8)
function StubHash([string] $p) {
    $sha = [Security.Cryptography.SHA256]::Create()
    '0x' + (-join ($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($p))[0..7] | ForEach-Object { $_.ToString('x2') }))
}
function NCalls { if (Test-Path $calls) { @(Get-Content $calls).Count } else { 0 } }
function Run([string[]] $a) {
    if (Test-Path $calls) { Remove-Item $calls }
    $ErrorActionPreference = 'Continue'   # local: a refusal's stderr line must not throw here
    $o = @(& powershell -NoProfile -ExecutionPolicy Bypass -File $tool @a -Swofty $stub 2>&1 | ForEach-Object { "$_" })
    @{ code = $LASTEXITCODE; out = $o; calls = (NCalls) }
}

$all = @(Get-Content $paths | Where-Object { $_ -and -not $_.StartsWith('#') })
Check 'd1_paths.txt has 76 paths' ($all.Count -eq 76) "($($all.Count))"
$cache = Join-Path $d 'cache.csv'
$other = 'entrants.drivers.driver[_metadata_=alex_albon].ai_driver_config.alongside.yield_overtake_rate'
@([pscustomobject]@{ path = $other; hash = '0xab43387f3babe94a'; stock = '1' },
  [pscustomobject]@{ path = $all[0]; hash = '0x1111111111111111'; stock = '0.04' }) | Export-Csv $cache -NoTypeInformation -Encoding UTF8
$pf = Join-Path $d 'paths.txt'
[IO.File]::WriteAllText($pf, ("# D1 paths`r`n`r`n" + ($all -join "`r`n") + "`r`n"), $utf8)

# 1. prefill: only the 75 missing paths are looked up; cached rows (ours and others) are kept as they were
$r = Run @('-PrefillOnly', $pf, '-KeyCache', $cache)
$rows = @(Import-Csv $cache)
$byPath = @{}; foreach ($x in $rows) { $byPath[$x.path] = $x }
Check 'prefill: exit 0' ($r.code -eq 0) "($($r.code): $($r.out -join ' | '))"
Check 'prefill: 75 db get calls, all with --profile verve-test' ($r.calls -eq 75 -and @(Get-Content $calls | Where-Object { $_ -notlike 'db get --profile verve-test *' }).Count -eq 0) "($($r.calls))"
Check 'prefill: 77 rows (76 paths + 1 other)' ($rows.Count -eq 77) "($($rows.Count))"
Check 'prefill: new rows carry the stub hash and stock' (@($all[1..75] | Where-Object { $byPath[$_].hash -ne (StubHash $_) -or $byPath[$_].stock -ne '0.28' }).Count -eq 0)
Check 'prefill: the pre-cached row and the other row are unchanged' ($byPath[$all[0]].hash -eq '0x1111111111111111' -and $byPath[$all[0]].stock -eq '0.04' -and $byPath[$other].hash -eq '0xab43387f3babe94a')
Check 'prefill: summary line' (($r.out -join "`n") -match 'prefill: 76 path\(s\) in .*: 1 already cached, 75 looked up and added, 0 problem\(s\) \(77 in ') ($r.out -join ' | ')

# 2. again: everything cached, no call, the file untouched
$h0 = (Get-FileHash $cache).Hash
$r = Run @('-PrefillOnly', $pf, '-KeyCache', $cache)
Check 'prefill again: exit 0, no db get, cache file unchanged' ($r.code -eq 0 -and $r.calls -eq 0 -and (Get-FileHash $cache).Hash -eq $h0) "($($r.code), $($r.calls) calls)"

# 3. a path with no key: exit 1, reported, not added
$bad = Join-Path $d 'bad.txt'
[IO.File]::WriteAllText($bad, "entrants.drivers.driver[_metadata_=nosuch].ai_driver_config.race_start.min_reaction_time_lower_bound`r`n", $utf8)
$r = Run @('-PrefillOnly', $bad, '-KeyCache', $cache)
Check 'prefill: a missing key is exit 1 (NO KEY), nothing added' ($r.code -eq 1 -and ($r.out -join "`n") -match 'NO KEY' -and (Get-FileHash $cache).Hash -eq $h0) "($($r.code): $($r.out -join ' | '))"

# 4. -PrefillOnly without -KeyCache is refused
$r = Run @('-PrefillOnly', $pf)
Check 'prefill without -KeyCache: refused' ($r.code -ne 0 -and $r.calls -eq 0) "($($r.code))"
$r = Run @('-KeyCache', $cache)
Check 'no -Loader/-Folder and no -PrefillOnly: refused' ($r.code -ne 0 -and $r.calls -eq 0) "($($r.code))"

# 5. the D1 build check offline on the filled cache: a d1_make add-on and a loader.log that holds its 36 ops
$gen = Join-Path $d 'gen'
& $Python -I (Join-Path $PSScriptRoot 'd1_make.py') --seed 1 --launch 2 --out $gen | Out-Null
$folder = Join-Path $gen 'verve.d1-L02'
$ops = (Get-Content (Join-Path $folder 'db\d1.json') -Raw | ConvertFrom-Json).ops
Check 'd1_make wrote 36 ops' (@($ops).Count -eq 36)
function Loader([string] $file, [string] $firstValue) {
    $l = @('[assets] gamedb: loading')
    $k = 0
    foreach ($o in $ops) {
        $v = if ($k -eq 0) { $firstValue } else { $o.value }
        $h = $byPath["$($o.select).$($o.field)"].hash
        $l += "[assets] gamedb: overwrote $h (key 12345, tag 2 float): 0.28 -> $v"
        $k++
    }
    $l += "[assets] gamedb: $(56 + @($ops).Count) overwritten"
    [IO.File]::WriteAllLines($file, [string[]]$l, $utf8)
}
# the first op's path is the one pre-cached with a made-up hash: give it the stub hash so every op has a line
$byPath[$all[0]] = [pscustomobject]@{ path = $all[0]; hash = (StubHash $all[0]); stock = '0.04' }
@($byPath.Values) | Sort-Object path | Export-Csv $cache -NoTypeInformation -Encoding UTF8
$log = Join-Path $d 'loader.log'
Loader $log '0.65'
$r = Run @('-Loader', $log, '-Folder', $folder, '-Baseline', '56', '-KeyCache', $cache)
$t = $r.out -join "`n"
Check 'build check: exit 0, no db get, 36 applied, expected 56 + 36 = 92' ($r.code -eq 0 -and $r.calls -eq 0 -and $t -match 'ops 36: 36 applied' -and $t -match 'expected 56 \+ 36 = 92' -and $t -match 'all 36 paths cached') ($r.out -join ' | ')
Loader $log '0.6'
$r = Run @('-Loader', $log, '-Folder', $folder, '-Baseline', '56', '-KeyCache', $cache)
Check 'build check: a wrong value is exit 1 (MISMATCH)' ($r.code -eq 1 -and ($r.out -join "`n") -match 'MISMATCH') ($r.out -join ' | ')

# 6. C-1's build check offline on the same cache: c1_make's launch 1 (56 ops at 0.20 / 0.35 / 0.65, D1's 76 paths)
$genC = Join-Path $d 'genc1'
& $Python -I (Join-Path $PSScriptRoot 'c1_make.py') --seed 2026111705 --launch 1 --out $genC | Out-Null
$folder = Join-Path $genC 'verve.c1-L01'
$ops = (Get-Content (Join-Path $folder 'db\c1.json') -Raw | ConvertFrom-Json).ops
Check 'c1_make wrote 56 ops at three levels' (@($ops).Count -eq 56 -and (@($ops | ForEach-Object { $_.value } | Sort-Object -Unique) -join ',') -eq '0.20,0.35,0.65')
Loader $log "$(@($ops)[0].value)"
$r = Run @('-Loader', $log, '-Folder', $folder, '-Baseline', '56', '-KeyCache', $cache)
$t = $r.out -join "`n"
Check 'C-1 build check: exit 0, no db get (no new path), 56 applied, expected 56 + 56 = 112' ($r.code -eq 0 -and $r.calls -eq 0 -and $t -match 'ops 56: 56 applied' -and $t -match 'expected 56 \+ 56 = 112' -and $t -match 'all 56 paths cached') ($r.out -join ' | ')
$wrong = if (@($ops)[0].value -eq '0.20') { '0.35' } else { '0.20' }
Loader $log $wrong
$r = Run @('-Loader', $log, '-Folder', $folder, '-Baseline', '56', '-KeyCache', $cache)
Check 'C-1 build check: another level in the game is exit 1 (MISMATCH)' ($r.code -eq 1 -and ($r.out -join "`n") -match 'MISMATCH') ($r.out -join ' | ')

Remove-Item $d -Recurse -Force
if ($fails) { "test_check_applied: $fails FAILED"; exit 1 }
'test_check_applied: all ok'
exit 0
