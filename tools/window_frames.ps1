<#
Save the F1 25 window to downscaled PNGs every few seconds while a test runs, to see what menu screens show
(`swofty test`'s own `capture` step doesn't work yet: "no frame within its time limit", docs/std/testing.md).

Usage:
    powershell -File tools/window_frames.ps1 -Out runs/<id>/frames [-EveryS 2] [-Width 640] [-MaxS 900]

Uses PrintWindow with PW_RENDERFULLCONTENT on the game's main window, so it works when the window isn't in front.
Stops when the -Stop file appears, after -MaxS seconds, or once the game has run and exited.
#>
param(
    [Parameter(Mandatory)] [string] $Out,
    [double] $EveryS = 2,
    [int] $Width = 640,
    [int] $MaxS = 900,
    [string] $Stop = ''
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System; using System.Runtime.InteropServices;
public static class Win {
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
    [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint flags);
}
'@
New-Item -ItemType Directory -Force $Out | Out-Null
$t0 = Get-Date; $seen = $false; $n = 0
while (((Get-Date) - $t0).TotalSeconds -lt $MaxS -and -not ($Stop -and (Test-Path $Stop))) {
    $p = Get-Process F1_25 -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
    if (-not $p) { if ($seen -and -not (Get-Process F1_25 -ErrorAction SilentlyContinue)) { break }; Start-Sleep -Milliseconds 500; continue }
    $seen = $true
    $r = New-Object Win+RECT
    if ([Win]::GetClientRect($p.MainWindowHandle, [ref]$r) -and $r.R -gt 0 -and $r.B -gt 0) {
        $bmp = New-Object Drawing.Bitmap $r.R, $r.B
        $g = [Drawing.Graphics]::FromImage($bmp); $dc = $g.GetHdc()
        [void][Win]::PrintWindow($p.MainWindowHandle, $dc, 3)   # PW_CLIENTONLY | PW_RENDERFULLCONTENT
        $g.ReleaseHdc($dc); $g.Dispose()
        $h = [int]($r.B * $Width / $r.R)
        $small = New-Object Drawing.Bitmap $bmp, $Width, $h
        $small.Save((Join-Path $Out ("{0}.png" -f (Get-Date -Format 'HHmmss_ff'))), [Drawing.Imaging.ImageFormat]::Png)
        $small.Dispose(); $bmp.Dispose(); $n++
    }
    Start-Sleep -Milliseconds ([int]($EveryS * 1000))
}
"frames: $n -> $Out"
