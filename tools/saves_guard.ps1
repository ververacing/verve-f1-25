<#
Protect Tyler's F1 25 saves around a route test (Time Trial, Grand Prix by route + pad), which runs on his own saves.
Tyler's OK (2026-10-31): back up before each route test, compare after, restore the originals if anything changed.

Usage:
    $b = powershell -File tools/saves_guard.ps1 -Action Backup -Label udp_tt     # prints the backup folder
    powershell -File tools/saves_guard.ps1 -Action Check -Backup $b -Log runs/<id>    # exit 0 = unchanged, 1 = changed
    powershell -File tools/saves_guard.ps1 -Action Restore -Backup $b -Log runs/<id>  # put the originals back
    powershell -File tools/saves_guard.ps1 -Action Backup -Label master                # one-off master copy

Backups go to %LOCALAPPDATA%\verve-f1-25\save-backups\<time>-<label>\ (files + hashes.csv), outside the Steam tree,
and are never deleted or overwritten here. Restore first moves whatever the test left (changed or new files) into
<backup>\written_by_test\, so nothing is lost, then copies the originals back, sets their modified time to now and
checks the hashes again. Check and Restore write <Log>\saves_changes.csv (name, change, size and hash before/after,
restored). Backup and Restore refuse to run while F1 25 is running, since the game can hold or rewrite the files.

Steam Cloud syncs the folder when the game exits, so a test's write can already be in the cloud when Restore runs.
The fresh modified time makes the restored local files the newer copy for Steam; if a later launch still shows a
cloud-conflict dialog, stop route tests and tell Tyler rather than clicking through it.
#>
param(
    [Parameter(Mandatory)] [ValidateSet('Backup', 'Check', 'Restore')] [string] $Action,
    [string] $Label = 'route',
    [string] $Backup,
    [string] $Log,
    [string] $Saves = '',   # <Steam>\userdata\<steamid>\3059520\remote; found by tools/find_steam_app.ps1 when empty
    [string] $Root = "$env:LOCALAPPDATA\verve-f1-25\save-backups"
)
$ErrorActionPreference = 'Stop'
if (-not $Saves) { $Saves = Join-Path (& (Join-Path $PSScriptRoot 'find_steam_app.ps1')) 'remote' }

function Hashes([string] $dir) {
    $h = @{}
    foreach ($f in Get-ChildItem $dir -File -Recurse) {
        $h[$f.FullName.Substring($dir.Length).TrimStart('\')] = (Get-FileHash $f.FullName -Algorithm SHA256).Hash
    }
    $h
}
function Get-SaveDiff([string] $backup) {
    $was = @{}; foreach ($r in Import-Csv (Join-Path $backup 'hashes.csv')) { $was[$r.name] = $r.sha256 }
    $now = Hashes $Saves
    foreach ($n in $was.Keys) { if (-not $now.ContainsKey($n)) { [pscustomobject]@{ name = $n; change = 'removed' } } elseif ($now[$n] -ne $was[$n]) { [pscustomobject]@{ name = $n; change = 'changed' } } }
    foreach ($n in $now.Keys) { if (-not $was.ContainsKey($n)) { [pscustomobject]@{ name = $n; change = 'added' } } }
}
function GameRunning { [bool](Get-Process -Name 'F1_25' -ErrorAction SilentlyContinue) }
function Describe([string] $path) {
    if (Test-Path $path) { $f = Get-Item $path; @{ size = $f.Length; sha256 = (Get-FileHash $path -Algorithm SHA256).Hash } } else { @{ size = ''; sha256 = '' } }
}
function WriteLog($d, [string] $after, [bool] $restored) {
    if (-not $Log) { return }
    New-Item -ItemType Directory -Force $Log | Out-Null
    @($d | ForEach-Object {
        $b = Describe (Join-Path $Backup "files\$($_.name)"); $a = Describe (Join-Path $after $_.name)
        [pscustomobject]@{ name = $_.name; change = $_.change; size_before = $b.size; size_after = $a.size
            sha256_before = $b.sha256; sha256_after = $a.sha256; restored = $restored; backup = $Backup }
    }) | Export-Csv (Join-Path $Log 'saves_changes.csv') -NoTypeInformation
}

switch ($Action) {
    'Backup' {
        if (GameRunning) { throw 'F1 25 is running; back up only with the game closed.' }
        $dest = Join-Path $Root "$(Get-Date -Format 'yyyyMMdd-HHmmss')-$Label"
        New-Item -ItemType Directory -Force (Join-Path $dest 'files') | Out-Null
        Copy-Item (Join-Path $Saves '*') (Join-Path $dest 'files') -Recurse -Force
        $h = Hashes $Saves
        $h.GetEnumerator() | Sort-Object Key | ForEach-Object { [pscustomobject]@{ name = $_.Key; sha256 = $_.Value } } |
            Export-Csv (Join-Path $dest 'hashes.csv') -NoTypeInformation
        $copy = Hashes (Join-Path $dest 'files')
        foreach ($n in $h.Keys) { if ($copy[$n] -ne $h[$n]) { throw "backup copy of $n doesn't match the original" } }
        $dest
    }
    'Check' {
        $d = @(Get-SaveDiff $Backup)
        WriteLog $d $Saves $false
        if ($d.Count -eq 0) { "saves unchanged ($((Import-Csv (Join-Path $Backup 'hashes.csv')).Count) files)"; exit 0 }
        $d | ForEach-Object { "$($_.change) $($_.name)" }
        exit 1
    }
    'Restore' {
        if (GameRunning) { throw 'F1 25 is running; restore only with the game closed.' }
        $d = @(Get-SaveDiff $Backup)
        if ($d.Count -eq 0) { WriteLog $d $Saves $false; 'saves unchanged, nothing to restore'; exit 0 }
        $kept = Join-Path $Backup 'written_by_test'
        foreach ($x in $d | Where-Object change -ne 'removed') {
            $to = Join-Path $kept $x.name; New-Item -ItemType Directory -Force (Split-Path $to) | Out-Null
            Move-Item (Join-Path $Saves $x.name) $to -Force
        }
        foreach ($x in $d | Where-Object change -ne 'added') {
            $to = Join-Path $Saves $x.name; New-Item -ItemType Directory -Force (Split-Path $to) | Out-Null
            Copy-Item (Join-Path $Backup "files\$($x.name)") $to -Force
            (Get-Item $to).LastWriteTime = Get-Date
        }
        WriteLog $d $kept $true
        $d | ForEach-Object { "$($_.change) $($_.name): restored (test's copy kept in written_by_test\)" }
        $left = @(Get-SaveDiff $Backup)
        if ($left.Count) { "RESTORE INCOMPLETE:"; $left | ForEach-Object { "  $($_.change) $($_.name)" }; exit 1 }
        'saves match the backup again'
    }
}
