<#
Read-only process trace around a launch (supervisor, 2026-11-14): is an addon helper program (for example
teamsimplified.mods' bin\simplified-helper.exe, a `launcher.program` with build and startup set) alive while Swofty's
addon-storage swap runs? The swap's os error 32 (docs/upstream/swofty_addon_storage_lock.md) would fit a helper
holding the folders.

PRIVACY: the repo is public, so this never records what else runs on Tyler's PC. It names only processes matching
swofty*, F1_25*, *helper*, the installed addons' launcher.program names, steam* and MsMpEng; every other process is
only counted. The trace goes to %TEMP%\verve-trace\ (never committed); the run folder gets a short summary.

Usage (the run scripts start it hidden right before the launch):
    powershell -File tools/process_trace.ps1 -Summary <run>\process_trace_summary.txt [-Seconds 45] [-IntervalMs 250]
#>
param(
    [Parameter(Mandatory)] [string] $Summary,
    [int] $Seconds = 45,
    [int] $IntervalMs = 250
)
$ErrorActionPreference = 'Continue'
$dir = Join-Path $env:TEMP 'verve-trace'
New-Item -ItemType Directory -Force $dir | Out-Null
$Log = Join-Path $dir ("trace-" + (Get-Date -Format 'yyyyMMdd-HHmmss') + ".txt")

# names worth naming: Swofty, the game, helpers, the addons' declared helper programs, Steam, Defender
$programs = @(Get-ChildItem (Join-Path $env:LOCALAPPDATA 'Swofty\addons') -Directory -ErrorAction SilentlyContinue | ForEach-Object {
    $m = Join-Path $_.FullName 'swofty.json'
    if (Test-Path $m) { try { $p = (Get-Content $m -Raw | ConvertFrom-Json).launcher.program.windows; if ($p) { [IO.Path]::GetFileNameWithoutExtension($p) } } catch { } }
})
function Named([string] $n) { $n -match '^(swofty|F1_25|steam|MsMpEng$)' -or $n -match 'helper' -or $programs -contains $n }
function W([string] $s) { Add-Content $Log $s -Encoding utf8 }
function Now { (Get-Date).ToString('HH:mm:ss.fff') }
function Ids { $h = @{}; foreach ($p in [Diagnostics.Process]::GetProcesses()) { $h[$p.Id] = $p }; $h }

$t0 = Get-Date
$prev = Ids
$named = @($prev.Values | Where-Object { Named $_.ProcessName })
W "$(Now) start: $($prev.Count) processes, named: $(($named | ForEach-Object { "$($_.ProcessName) pid $($_.Id)" }) -join '; ')"
$seen = @{}   # name -> first and last time seen, for the summary
foreach ($p in $named) { $seen[$p.ProcessName] = @{ first = 'before start'; last = Now; pid = $p.Id } }
$other = 0
while (((Get-Date) - $t0).TotalSeconds -lt $Seconds) {
    Start-Sleep -Milliseconds $IntervalMs
    $now = Ids
    foreach ($id in $now.Keys) {
        if ($prev.ContainsKey($id)) { continue }
        $p = $now[$id]
        if (Named $p.ProcessName) {
            $st = try { $p.StartTime.ToString('HH:mm:ss.fff') } catch { '?' }
            W "$(Now) + $($p.ProcessName) pid $id started $st"
            if (-not $seen.ContainsKey($p.ProcessName)) { $seen[$p.ProcessName] = @{ first = $st; last = Now; pid = $id } }
        } else { $other++ }
    }
    foreach ($id in $prev.Keys) { if (-not $now.ContainsKey($id) -and (Named $prev[$id].ProcessName)) { W "$(Now) - $($prev[$id].ProcessName) pid $id" } }
    foreach ($p in $now.Values) { if ($seen.ContainsKey($p.ProcessName)) { $seen[$p.ProcessName].last = Now } }
    $prev = $now
}
W "$(Now) trace end; $other other process start(s) not named"
$lines = @("process trace $($t0.ToString('HH:mm:ss')) for $Seconds s (full trace in %TEMP%\verve-trace, not committed); $other other process start(s) not named")
$lines += $seen.Keys | Sort-Object | ForEach-Object { "  $_ (pid $($seen[$_].pid)): first seen $($seen[$_].first), last seen $($seen[$_].last)" }
Set-Content $Summary -Value $lines -Encoding utf8
