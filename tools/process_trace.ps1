<#
Read-only process trace around a launch (supervisor, 2026-11-14): is an addon helper program (for example
teamsimplified.mods' bin\simplified-helper.exe, a `launcher.program` with build and startup set) alive while Swofty's
addon-storage swap runs? The swap's os error 32 (docs/upstream/swofty_addon_storage_lock.md) would fit a helper
holding the folders.

Usage (the run scripts start it hidden right before the launch):
    powershell -File tools/process_trace.ps1 -Log <run>\process_trace.txt [-Seconds 40] [-IntervalMs 250]

Writes the full process list once, then every -IntervalMs the processes that started (with their start time and
path) or exited since the last sample. Changes nothing.
#>
param(
    [Parameter(Mandatory)] [string] $Log,
    [int] $Seconds = 40,
    [int] $IntervalMs = 250
)
$ErrorActionPreference = 'Continue'
function W([string] $s) { Add-Content $Log $s -Encoding utf8 }
function Now { (Get-Date).ToString('HH:mm:ss.fff') }
function Ids { $h = @{}; foreach ($p in [Diagnostics.Process]::GetProcesses()) { $h[$p.Id] = $p }; $h }
$t0 = Get-Date
$prev = Ids
W "$(Now) full list ($($prev.Count) processes):"
$prev.Values | Sort-Object ProcessName | ForEach-Object { W "  $($_.ProcessName) pid $($_.Id)" }
while (((Get-Date) - $t0).TotalSeconds -lt $Seconds) {
    Start-Sleep -Milliseconds $IntervalMs
    $now = Ids
    foreach ($id in $now.Keys) {
        if ($prev.ContainsKey($id)) { continue }
        $p = $now[$id]
        $st = try { $p.StartTime.ToString('HH:mm:ss.fff') } catch { '?' }
        $path = try { $p.MainModule.FileName -replace [regex]::Escape($env:USERPROFILE), '%USERPROFILE%' } catch { '' }
        W "$(Now) + $($p.ProcessName) pid $id started $st $path"
    }
    foreach ($id in $prev.Keys) { if (-not $now.ContainsKey($id)) { W "$(Now) - $($prev[$id].ProcessName) pid $id" } }
    $prev = $now
}
W "$(Now) trace end"
