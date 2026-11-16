<#
Selftest for tools/hw_settings.ps1 (pure; temp files only, never the real hardware_settings_config.xml).

Usage:
    powershell -File tools/test_hw_settings.ps1      # exit 0 ok, 1 failed
#>
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'hw_settings.ps1')
$d = Join-Path $env:TEMP "hw_settings_test_$PID"
New-Item -ItemType Directory -Force $d | Out-Null
function X([string] $send, [string] $fps, [string] $layout) {
    $udp = "<udp enabled=`"true`" ip=`"127.0.0.1`" port=`"20777`" sendRate=`"$send`" format=`"2026`" />"
    $res = "<resolution width=`"1920`" height=`"1080`" frameRateLimiterValue=`"$fps`" />"
    if ($layout -eq 'a') { "<?xml version=`"1.0`"?>`n<hardware_settings_config>`n  <cpu name=`"CPU`" />`n  <graphics_card>$res</graphics_card>`n  <motion>$udp</motion>`n</hardware_settings_config>" }
    else { "<hardware_settings_config><cpu name=`"CPU`"/><graphics_card>`n$res`n</graphics_card><motion>`n$udp`n</motion></hardware_settings_config>" }
}
$failed = 0
function Case([string] $name, [string] $a, [string] $b, [int] $want) {
    Set-Content "$d\a.xml" $a -Encoding utf8; Set-Content "$d\b.xml" $b -Encoding utf8
    $got = @(Compare-HwValues "$d\a.xml" "$d\b.xml")
    $ok = $got.Count -eq $want
    if (-not $ok) { $script:failed++ }
    "{0} {1}: {2} change(s){3}" -f $(if ($ok) { 'ok  ' } else { 'FAIL' }), $name, $got.Count, $(if ($got) { ' (' + ($got -join '; ') + ')' } else { '' })
}
Case 'identical values, other layout' (X '60hz' '60' 'a') (X '60hz' '60' 'b') 0
Case 'sendRate 60hz vs 60 (the named benign flip)' (X '60hz' '60' 'a') (X '60' '60' 'b') 0
Case 'sendRate 60 vs 30hz (a real change)' (X '60' '60' 'a') (X '30hz' '60' 'b') 1
Case 'frameRateLimiterValue 60 vs 144 (a real change)' (X '60hz' '60' 'a') (X '60hz' '144' 'a') 1
Case '"hz" elsewhere is not normalised' (X '60' '60hz' 'a') (X '60' '60' 'a') 1
Remove-Item $d -Recurse -Force
if ($failed) { "test_hw_settings: $failed FAILED"; exit 1 }
'test_hw_settings: ok'
