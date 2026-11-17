<#
The display fallback restore (supervisor, 2026-11-16, after V-1 launch 7). When a test session ends with the ONLY
hardware-settings change being graphics_card/resolution@width and @height (the game wrote its 1024x768 fallback, most
likely while the display slept), put just those two values back from Tyler's reference and verify.

Usage:
    powershell -File tools/hw_display_restore.ps1 [-Out <run folder>] [-LogName <file name>] [-FallbackOnly]
        [-File <live xml>] [-Reference <reference xml>] [-SnapDir <evidence folder>] [-NoProcessCheck]   # test hooks

Steps: refuse while F1 25 or a Swofty process is up; compare the live file with the reference by value
(tools/hw_settings.ps1); go on only if the changes are exactly the resolution width and/or height; save the live file
to <SnapDir> as evidence; set those attributes on the single <resolution> element to the reference's values by an
in-place text edit (every other byte stays the same, the BOM is kept); then verify 0 value changes against the reference.
Writes <Out>\<LogName> (default display_fallback.txt; the start-of-run check in sandbox_shell uses
display_fallback_start.txt). -FallbackOnly (the start-of-run and preflight checks): go on only if the live
resolution is exactly the game's 1024x768 fallback; any other resolution may be Tyler's own choice and is left alone.
Exit 0 = restored and verified; 1 = refused or failed (nothing written, or the
evidence copy kept): the caller treats it as SAVES CHANGED (exit 5).
#>
param(
    [string] $Out = '',
    [string] $LogName = 'display_fallback.txt',
    [string] $File = '',
    [string] $Reference = '',
    [string] $SnapDir = (Join-Path $env:LOCALAPPDATA 'verve-f1-25\settings-snapshots'),
    [switch] $FallbackOnly,
    [switch] $NoProcessCheck
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'hw_settings.ps1')
if (-not $File) { $File = $HwFile }
if (-not $Reference) { $Reference = $HwReference }
$log = @()
function Say([string] $m) { $script:log += $m; $m }
function Done([int] $code) {
    if ($Out) { Set-Content (Join-Path $Out $LogName) -Encoding utf8 -Value $script:log }
    exit $code
}
$ResKeys = '^hw hardware_settings_config/graphics_card/resolution@(width|height)$'

if (-not $NoProcessCheck -and (Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Name -match '^(F1_25|swofty)' })) {
    Say 'display fallback: REFUSED: F1 25 or a Swofty process is running'; Done 1
}
if (-not (Test-Path $File) -or -not (Test-Path $Reference)) { Say "display fallback: REFUSED: missing file ($File / $Reference)"; Done 1 }
$ref = Get-HwValues $Reference
$cur = Get-HwValues $File
$changed = @(foreach ($k in @($ref.Keys) + @($cur.Keys) | Select-Object -Unique) { if ($ref[$k] -ne $cur[$k]) { $k } })
if (-not $changed.Count) { Say 'display fallback: nothing to do (live equals the reference by value)'; Done 0 }
$other = @($changed | Where-Object { $_ -notmatch $ResKeys })
if ($other.Count) { Say "display fallback: REFUSED: other keys changed too: $($other -join ', ')"; Done 1 }
Say ("display fallback: live differs only in " + (($changed | ForEach-Object { "$($_ -replace '^hw hardware_settings_config/graphics_card/', '') $($ref[$_]) -> $($cur[$_])" }) -join ', '))
$wk = 'hw hardware_settings_config/graphics_card/resolution@width'; $hk = 'hw hardware_settings_config/graphics_card/resolution@height'
if ($FallbackOnly -and -not ($cur[$wk] -eq '1024' -and $cur[$hk] -eq '768')) {
    Say "display fallback: REFUSED (-FallbackOnly): the live resolution $($cur[$wk])x$($cur[$hk]) isn't the 1024x768 fallback; left as it is (it may be Tyler's own choice)"; Done 1
}

New-Item -ItemType Directory -Force $SnapDir | Out-Null
$ev = Join-Path $SnapDir ("hardware_settings_config.display-fallback-{0}.xml" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
Copy-Item $File $ev
Say "display fallback: evidence copy $(Split-Path $ev -Leaf)"

$bytes = [IO.File]::ReadAllBytes($File)
$bom = $bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF
$skip = 0; if ($bom) { $skip = 3 }
$text = [Text.Encoding]::UTF8.GetString($bytes, $skip, $bytes.Length - $skip)
$ms = ([regex] '<resolution\b[^>]*>').Matches($text)
if ($ms.Count -ne 1) { Say "display fallback: REFUSED: expected one <resolution> element, found $($ms.Count)"; Done 1 }
$tag = $ms[0].Value; $newTag = $tag
foreach ($k in $changed) {
    $attr = ([regex]::Match($k, $ResKeys)).Groups[1].Value
    $want = $ref[$k]
    $pat = '\b' + $attr + '="[^"]*"'
    if (-not ([regex]::IsMatch($newTag, $pat))) { Say "display fallback: REFUSED: no $attr attribute on <resolution>"; Done 1 }
    $newTag = [regex]::Replace($newTag, $pat, "$attr=`"$want`"")
}
$text2 = $text.Substring(0, $ms[0].Index) + $newTag + $text.Substring($ms[0].Index + $tag.Length)
$outBytes = [Text.Encoding]::UTF8.GetBytes($text2)
if ($bom) { $outBytes = [byte[]](0xEF, 0xBB, 0xBF) + $outBytes }
[IO.File]::WriteAllBytes($File, $outBytes)
$left = @(Compare-HwValues $Reference $File)
if ($left.Count) { Say "display fallback: FAILED: still differs after the edit: $($left -join '; ')"; Done 1 }
Say 'display fallback restored (live equals the reference by value)'
Done 0
