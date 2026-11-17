<#
The last step of every PAUSE (and window close): tell Tyler, through the supervisor, whether he can play.
Prints exactly one verdict line, either "SAFE TO PLAY" or "WAIT: <reason>" (supervisor, 2026-11-15, after the
incident in docs/incidents/2026-11-15-killed-tyler-game.md).

Usage:
    powershell -File tools/safe_to_play.ps1        # exit 0 = SAFE TO PLAY, 1 = WAIT

SAFE TO PLAY only once all of these have FINISHED:
1. Nothing of ours is running: no runner or sandbox script (b00xx_run, sandbox_shell, sandbox_run, run_with_udp,
   preflight, post_run_check, cleanup, deferred check) and no process recorded in a recent runs/**/ours.csv.
2. No F1 25 or Swofty process is up (if Tyler's own game or launcher is up, he is already in; the checks wait).
2b. If a low-graphics swap is active (tools/hw_swap.ps1 state), Tyler's hardware_settings_config.xml is restored
   byte-identical and verified; a failure is "WAIT: ... URGENT: message the supervisor now". No swap: a no-op.
3. post_run_check.ps1 exits 0 (CLEAN), cleanup_test_profiles.ps1 exits 0, deferred_saves_check.ps1 has nothing
   pending. These run only after 1 and 2 pass, so this script never runs a swofty command while a game or launcher is up.
#>
param([string] $Repo = (Split-Path $PSScriptRoot -Parent))
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'ours.ps1')
function Verdict([string] $s, [int] $code) { $s; exit $code }

$snap = Get-ProcSnapshot
# 1a. our scripts, by command line (never stopped here; only waited for)
# ourselves and our ancestors don't count (tools/pause.ps1 calls this, and a runner calls pause.ps1 at its race's end)
$mine = @{}; $cur = $PID
while ($cur -and -not $mine.ContainsKey($cur)) { $mine[$cur] = $true; $cur = ($snap | Where-Object { $_.Id -eq $cur } | Select-Object -First 1).ParentId }
$scripts = @(Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe' OR Name = 'pwsh.exe' OR Name = 'python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { -not $mine.ContainsKey([int]$_.ProcessId) -and $_.CommandLine -match '(b00\d\d_run|v1_run|sandbox_shell|sandbox_run|run_with_udp|preflight|post_run_check|cleanup_test_profiles|deferred_saves_check|storage_sidestep|udp_capture|udp_finish_watch)\.(ps1|py)' -and
                   $_.CommandLine -notmatch 'WScript\.Shell\)\.Popup' })   # pause.ps1's own WAIT popup names the scripts in its text (15:04 false WAIT)
if ($scripts.Count) { Verdict "WAIT: cleanup running ($(($scripts | ForEach-Object { ($_.CommandLine -replace '^.*\\', '') -replace '\s.*$', '' }) -join ', '))" 1 }
# 1b. processes recorded as ours in the last two days
$recs = @(Get-ChildItem (Join-Path $Repo 'runs') -Recurse -Filter 'ours.csv' -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -gt (Get-Date).AddDays(-2) } | ForEach-Object { Import-Csv $_.FullName })
$ours = @(Get-OursTree $recs $snap)
if ($ours.Count) { Verdict "WAIT: cleanup running (ours still up: $(($ours | ForEach-Object { "$($_.Name) $($_.Id)" }) -join ', '))" 1 }
# 2. any game or Swofty process now is someone else's
$up = @($snap | Where-Object { $_.Name -match '^F1_25' -or $_.Name -match '^swofty' })
if ($up.Count) { Verdict "WAIT: F1 25 or the Swofty Launcher is open (not ours: $(($up | ForEach-Object { "$($_.Name) $($_.Id)" }) -join ', ')); the post-run checks run once it has closed" 1 }
# 2b. Tyler's hardware settings (tools/hw_swap.ps1): if a low-graphics swap is active, his file is restored and its hash
# verified here, before the saves checks and before any SAFE TO PLAY; a failure is WAIT plus URGENT. No swap active:
# nothing is read or written (the opt-in rule)
$hwg = @(& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'hw_swap.ps1') -PauseGate)
$hwCode = $LASTEXITCODE
if ($hwCode -ne 0) {
    $hwLine = "$($hwg | Select-Object -Last 1)"
    if ($hwLine -notmatch '^WAIT: .*URGENT') { $hwLine = "WAIT: Tyler's hardware settings could not be checked (hw_swap exit $hwCode $hwLine). URGENT: message the supervisor now" }
    Verdict $hwLine 1
}
# 3. the checks themselves
$pc = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'post_run_check.ps1')
if ($LASTEXITCODE -ne 0) { Verdict "WAIT: post-run check not clean (exit $LASTEXITCODE): $($pc | Select-Object -Last 1)" 1 }
$cl = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'cleanup_test_profiles.ps1')
if ($LASTEXITCODE -ne 0) { Verdict "WAIT: test profiles left over: $($cl | Select-Object -Last 1)" 1 }
$dc = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'deferred_saves_check.ps1')
if ($LASTEXITCODE -ne 0 -or ($dc | Where-Object { $_ -match 'CHANGED|still pending' })) { Verdict "WAIT: deferred saves check: $($dc | Select-Object -Last 1)" 1 }
Verdict 'SAFE TO PLAY' 0
