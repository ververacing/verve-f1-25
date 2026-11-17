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

Remove-Item -Recurse -Force $d
if ($fails) { "test_hw_display_restore: $fails FAILED"; exit 1 }
'test_hw_display_restore: ok'; exit 0
