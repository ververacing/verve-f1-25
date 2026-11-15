<#
Run a `swofty test` suite with the UDP capture alongside, then parse the capture (#4).

Usage:
    powershell -File tools/run_with_udp.ps1 -Test harness/tests/udp_tt.test.json -Out runs/<id>

Starts tools/udp_capture.py (127.0.0.1:20777) before the test, stops it with a stop file after the test ends,
and runs tools/udp_parse.py on the recording into <Out>/udp/. The test report goes to <Out>/raw/ as usual.

Python here (the WindowsApps alias) can't open files under %APPDATA% or the rest of %LOCALAPPDATA%, but can under
%TEMP%. So the two scripts run from a copy in %TEMP%\verve-udp\, the recording is written there too, and the parsed
CSVs are copied back into <Out>/udp/. The raw recording stays in %TEMP%\verve-udp\<run>\ (it can be large; nothing
under runs/**/raw/ is committed).

Route tests run on Tyler's own saves, so the whole run is wrapped in tools/saves_guard.ps1: backup before, check
after (<Out>/saves_changes.csv), restore if anything changed. A failed restore exits 4: stop all route tests and
tell Tyler.
#>
param(
    [Parameter(Mandatory)] [string] $Test,
    [Parameter(Mandatory)] [string] $Out,
    [string] $Swofty = "$env:LOCALAPPDATA\Programs\SwoftyLauncher\bin\swofty.exe",
    [string] $Python = 'python',
    [string] $LaunchS = '1,3,6'
)
$ErrorActionPreference = 'Stop'
# PID ownership (incident 2026-11-15): record what we start, stop only that (tools/ours.ps1)
. (Join-Path $PSScriptRoot 'ours.ps1')
Ours-Init $Out
if (@(Ours-Foreign).Count) { 'F1 25 or a Swofty process (launcher) is running that this run did not start; not running'; exit 1 }
$run = Get-Date -Format 'yyyyMMdd-HHmmss'
$work = Join-Path $env:TEMP "verve-udp\$run"
New-Item -ItemType Directory -Force $work | Out-Null
Copy-Item (Join-Path $PSScriptRoot 'udp_capture.py'), (Join-Path $PSScriptRoot 'udp_parse.py') $work -Force
$bin = Join-Path $work 'udp.bin'; $stop = Join-Path $work 'stop.flag'; $log = Join-Path $work 'capture.log'
$cap = Start-Process -FilePath $Python -ArgumentList @('-I', "`"$work\udp_capture.py`"", '--out', "`"$bin`"", '--seconds', '14400', '--stop-file', "`"$stop`"") `
    -RedirectStandardOutput $log -RedirectStandardError "$log.err" -WindowStyle Hidden -PassThru
Ours-Add $cap 'udp capture'
Start-Sleep -Seconds 2
if ($cap.HasExited) { "capture failed to start:"; Get-Content "$log.err"; exit 1 }
"capture pid $($cap.Id) -> $bin"

New-Item -ItemType Directory -Force $Out | Out-Null
$guard = Join-Path $PSScriptRoot 'saves_guard.ps1'
$saves = powershell -NoProfile -File $guard -Action Backup -Label (Split-Path $Out -Leaf)
if ($LASTEXITCODE -ne 0 -or -not $saves) { Ours-StopOne $cap 'save backup failed' | Out-Null; "save backup failed; not running"; exit 1 }
"saves backed up -> $saves"
$raw = Join-Path (Resolve-Path $Out).Path 'raw'
& $Swofty test run $Test --out $raw --wait 0
$code = $LASTEXITCODE
"test exit: $code"
powershell -NoProfile -File $guard -Action Check -Backup $saves -Log $Out
if ($LASTEXITCODE -ne 0) {
    powershell -NoProfile -File $guard -Action Restore -Backup $saves -Log $Out
    if ($LASTEXITCODE -ne 0) { "SAVE RESTORE FAILED: stop route tests and tell Tyler (backup: $saves)"; $code = 4 }
}

New-Item -ItemType File -Force $stop | Out-Null
if (-not $cap.WaitForExit(15000)) { Ours-StopOne $cap 'capture did not stop on its flag' | Out-Null }
Get-Content $log -ErrorAction SilentlyContinue | Select-Object -Last 3
"recording: $((Get-Item $bin -ErrorAction SilentlyContinue).Length) bytes"

$parsed = Join-Path $work 'udp'
& $Python -I "$work\udp_parse.py" $bin --out $parsed --launch-s $LaunchS
if (Test-Path $parsed) { $dest = Join-Path $Out 'udp'; New-Item -ItemType Directory -Force $dest | Out-Null; Copy-Item "$parsed\*" $dest -Force; "parsed -> $dest" }
exit $code
