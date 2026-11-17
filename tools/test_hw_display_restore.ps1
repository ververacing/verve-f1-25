<#
Selftest for tools/hw_display_restore.ps1, on synthetic files in %TEMP% only (never the live settings file).
    powershell -File tools/test_hw_display_restore.ps1     # exit 0 = all ok
#>
$ErrorActionPreference = 'Stop'
$tool = Join-Path $PSScriptRoot 'hw_display_restore.ps1'
$d = Join-Path $env:TEMP ("hwdr-test-" + [guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory $d | Out-Null
$fails = 0
function Check([string] $name, [bool] $ok, [string] $detail = '') {
    if ($ok) { "ok   $name" } else { $script:fails++; "FAIL $name $detail" }
}
function Xml([string] $w, [string] $h, [string] $rate = '60hz', [string] $vsync = 'false') {
    "<?xml version=`"1.0`" encoding=`"UTF-8`"?>`r`n<hardware_settings_config version=`"1`">`r`n  <graphics_card deviceId=`"0x0`">`r`n    <resolution width=`"$w`" height=`"$h`" displayMode=`"2`" vsync=`"$vsync`" frameRateLimiterValue=`"60`" />`r`n  </graphics_card>`r`n  <motion>`r`n    <udp enabled=`"true`" ip=`"127.0.0.1`" port=`"20777`" sendRate=`"$rate`" format=`"2026`" />`r`n  </motion>`r`n</hardware_settings_config>`r`n"
}
function Case([string] $name, [string] $liveXml, [int] $wantExit, [scriptblock] $more = $null) {
    $ref = Join-Path $d "$name.ref.xml"; $live = Join-Path $d "$name.live.xml"; $snap = Join-Path $d "$name.snap"; $out = Join-Path $d "$name.out"
    New-Item -ItemType Directory $out | Out-Null
    [IO.File]::WriteAllText($ref, (Xml '1920' '1080'), (New-Object Text.UTF8Encoding $false))
    [IO.File]::WriteAllText($live, $liveXml, (New-Object Text.UTF8Encoding $false))
    $before = [IO.File]::ReadAllBytes($live)
    $o = & powershell -NoProfile -ExecutionPolicy Bypass -File $tool -Out $out -File $live -Reference $ref -SnapDir $snap -NoProcessCheck
    $code = $LASTEXITCODE
    Check "$name : exit $wantExit" ($code -eq $wantExit) "(got ${code}: $($o -join ' | '))"
    if ($more) { & $more $ref $live $snap $out $before $o }
}
. (Join-Path $PSScriptRoot 'hw_settings.ps1')

# 1. the launch 7 case: only width/height fell back -> restored, verified, evidence kept, only that tag changed
Case 'fallback' (Xml '1024' '768') 0 {
    param($ref, $live, $snap, $out, $before, $o)
    Check 'fallback: live equals the reference by value' (@(Compare-HwValues $ref $live).Count -eq 0)
    Check 'fallback: evidence copy saved' (@(Get-ChildItem $snap -Filter '*display-fallback-*.xml').Count -eq 1)
    Check 'fallback: display_fallback.txt says restored' ((Get-Content (Join-Path $out 'display_fallback.txt') -Raw) -match 'display fallback restored')
    $want = (Xml '1920' '1080')
    Check 'fallback: bytes equal the reference layout (only the two attributes edited)' ([IO.File]::ReadAllText($live) -eq $want)
}
# 2. only the width changed -> restored
Case 'width-only' (Xml '1024' '1080') 0 { param($ref, $live) Check 'width-only: equal by value' (@(Compare-HwValues $ref $live).Count -eq 0) }
# 3. another key changed too -> refused, file untouched
Case 'other-key' (Xml '1024' '768' '60hz' 'true') 1 {
    param($ref, $live, $snap, $out, $before)
    Check 'other-key: file untouched' ([Convert]::ToBase64String([IO.File]::ReadAllBytes($live)) -eq [Convert]::ToBase64String($before))
    Check 'other-key: no evidence copy' (-not (Test-Path $snap) -or @(Get-ChildItem $snap).Count -eq 0)
}
# 4. a non-resolution change only -> refused
Case 'vsync-only' (Xml '1920' '1080' '60hz' 'true') 1
# 5. nothing changed (the sendRate flip "60" vs "60hz" is benign) -> nothing to do, file untouched
Case 'benign-flip' (Xml '1920' '1080' '60') 0 {
    param($ref, $live, $snap, $out, $before, $o)
    Check 'benign-flip: says nothing to do' (($o -join ' ') -match 'nothing to do')
    Check 'benign-flip: file untouched' ([Convert]::ToBase64String([IO.File]::ReadAllBytes($live)) -eq [Convert]::ToBase64String($before))
}
# 6. a BOM is kept
$bomXml = [char]0xFEFF + (Xml '1024' '768')
Case 'bom' $bomXml 0 {
    param($ref, $live)
    $b = [IO.File]::ReadAllBytes($live)
    Check 'bom: kept' ($b[0] -eq 0xEF -and $b[1] -eq 0xBB -and $b[2] -eq 0xBF)
    Check 'bom: equal by value' (@(Compare-HwValues $ref $live).Count -eq 0)
}
# 7. the process check is on by default: this test's own process isn't F1 25, so only a structure check here
Check 'process check: on unless -NoProcessCheck' ((Get-Content $tool -Raw) -match "if \(-not \`$NoProcessCheck -and")
# 8. the shell calls it only for resolution-only diffs, and exits 5 otherwise
$sh = Get-Content (Join-Path $PSScriptRoot 'sandbox_shell.ps1') -Raw
Check 'sandbox_shell: resolution-only diff goes to hw_display_restore' ($sh -match 'hw_display_restore\.ps1' -and $sh -match 'resolution@\(width\|height\)')
# 9. -LogName: the start-of-run check logs to its own file, and the default name is unchanged
$ref = Join-Path $d 'ln.ref.xml'; $live = Join-Path $d 'ln.live.xml'; $out = Join-Path $d 'ln.out'
New-Item -ItemType Directory $out | Out-Null
[IO.File]::WriteAllText($ref, (Xml '1920' '1080'), (New-Object Text.UTF8Encoding $false))
[IO.File]::WriteAllText($live, (Xml '1024' '768'), (New-Object Text.UTF8Encoding $false))
& powershell -NoProfile -ExecutionPolicy Bypass -File $tool -Out $out -LogName 'display_fallback_start.txt' -File $live -Reference $ref -SnapDir (Join-Path $d 'ln.snap') -NoProcessCheck | Out-Null
Check 'LogName: restored, exit 0' ($LASTEXITCODE -eq 0)
Check 'LogName: logged to display_fallback_start.txt only' ((Test-Path (Join-Path $out 'display_fallback_start.txt')) -and -not (Test-Path (Join-Path $out 'display_fallback.txt')))
& powershell -NoProfile -ExecutionPolicy Bypass -File $tool -Out $out -File $live -Reference $ref -SnapDir (Join-Path $d 'ln.snap') -NoProcessCheck | Out-Null
Check 'LogName: default is display_fallback.txt, and nothing to do now' ($LASTEXITCODE -eq 0 -and (Get-Content (Join-Path $out 'display_fallback.txt') -Raw) -match 'nothing to do')
# 9b. -FallbackOnly: restores only the exact 1024x768 fallback; another resolution (maybe Tyler's own) is left untouched
$ref2 = Join-Path $d 'fo.ref.xml'; $live2 = Join-Path $d 'fo.live.xml'
[IO.File]::WriteAllText($ref2, (Xml '1920' '1080'), (New-Object Text.UTF8Encoding $false))
[IO.File]::WriteAllText($live2, (Xml '1280' '720'), (New-Object Text.UTF8Encoding $false))
$o2 = & powershell -NoProfile -ExecutionPolicy Bypass -File $tool -FallbackOnly -File $live2 -Reference $ref2 -SnapDir (Join-Path $d 'fo.snap') -NoProcessCheck
Check 'FallbackOnly: 1280x720 refused, exit 1' ($LASTEXITCODE -eq 1 -and ($o2 -join ' ') -match 'FallbackOnly')
Check 'FallbackOnly: 1280x720 left as it is' ((Get-Content $live2 -Raw) -match 'width="1280"')
[IO.File]::WriteAllText($live2, (Xml '1024' '768'), (New-Object Text.UTF8Encoding $false))
& powershell -NoProfile -ExecutionPolicy Bypass -File $tool -FallbackOnly -File $live2 -Reference $ref2 -SnapDir (Join-Path $d 'fo.snap') -NoProcessCheck | Out-Null
Check 'FallbackOnly: 1024x768 restored, exit 0' ($LASTEXITCODE -eq 0 -and (Get-Content $live2 -Raw) -match 'width="1920" height="1080"')
Check 'sandbox_shell: start-of-run check uses -FallbackOnly' ($sh -match "display_fallback_start\.txt' -FallbackOnly")
# 10. the shell runs the start-of-run check before the saves-before snapshot, logging to its own file, with no new stop
$iStart = $sh.IndexOf("-LogName 'display_fallback_start.txt'"); $iSnap = $sh.IndexOf('$before = Snapshot')
Check 'sandbox_shell: start-of-run check before the snapshot' ($iStart -gt 0 -and $iSnap -gt $iStart)
if ($iStart -gt 0 -and $iSnap -gt $iStart) {
    Check 'sandbox_shell: start-of-run check adds no exit or throw' ($sh.Substring($iStart, $iSnap - $iStart) -notmatch '\bexit\b|\bthrow\b')
}

Remove-Item -Recurse -Force $d
if ($fails) { "test_hw_display_restore: $fails FAILED"; exit 1 }
'test_hw_display_restore: ok'; exit 0
