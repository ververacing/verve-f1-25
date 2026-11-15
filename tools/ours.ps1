<#
PID ownership (incident 2026-11-15, docs/incidents/2026-11-15-killed-tyler-game.md). Dot-source it:

    . (Join-Path $PSScriptRoot 'ours.ps1')
    Ours-Init <run folder>                  # <run folder>\ours.csv: every process we start, with its start time
    Ours-Add $proc 'test shell'             # a [Diagnostics.Process] we started (or adopted: the game the test agent names)
    Ours-AddId <pid> 'game (agent hello)'   # the same by PID; refused if the process is gone
    Ours-Stop 'reason'                      # stops ONLY our recorded processes and their child trees
    Ours-Foreign                            # F1_25* / swofty* processes that are NOT ours (Tyler's game or launcher)

Rules (supervisor, 2026-11-15):
- Nothing ever stops a process by name. Ours-Stop stops a PID only if it is recorded here (or descends from a recorded
  one), and only if its start time still matches the record, so a reused PID never counts. A child counts only if it
  started at or after its parent.
- Ours-Stop does nothing at all while a foreign F1_25 or swofty process is running (returns $false and says so): if
  Tyler's game or launcher is up, ours are left for the next pre-flight rather than risk his session.
- Barriers (supervisor review of #107): the tree descent never enters or goes through steam*, swofty-launcher*,
  explorer or F1_25*. If our shell ever starts Steam, Steam and every game launched through it stay foreign. Steam,
  the launcher and explorer are never ours, even if recorded.
- An F1_25 is ours ONLY when explicitly recorded, by the PID our test agent reports. There is no fallback adoption:
  a game whose PID the agent never reported stays foreign, is never stopped, and is left for pre-flight.
The pure functions (Get-OursTree, Get-ForeignProcs) take a process snapshot so tools/test_ours.ps1 can test them.
#>

$script:OursFile = $null
$script:NeverOurs = '^(steam|swofty-launcher|explorer$)'      # never ours, recorded or not
$script:Barrier = '^(steam|swofty-launcher|explorer$|F1_25)'   # the descent never enters or passes these

function Get-ProcSnapshot {
    # one row per process: Id, ParentId, Name (no .exe), Start (local datetime)
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | ForEach-Object {
        [pscustomobject]@{ Id = [int]$_.ProcessId; ParentId = [int]$_.ParentProcessId
            Name = ($_.Name -replace '\.exe$', ''); Start = $_.CreationDate }
    }
}

function Same-Start($a, $b) {
    if (-not $a -or -not $b) { return $false }
    [math]::Abs(([datetime]$a - [datetime]$b).TotalSeconds) -lt 2
}

function Get-OursTree($records, $snapshot) {
    # the live processes that are ours: recorded PIDs whose start time still matches, plus their descendants
    $byParent = @{}
    foreach ($p in $snapshot) { if (-not $byParent.ContainsKey($p.ParentId)) { $byParent[$p.ParentId] = @() }; $byParent[$p.ParentId] += $p }
    $live = @{}
    foreach ($p in $snapshot) { $live[$p.Id] = $p }
    $out = @{}
    $queue = New-Object System.Collections.Queue
    foreach ($r in $records) {
        $p = $live[[int]$r.Id]
        if ($p -and $p.Name -notmatch $script:NeverOurs -and (Same-Start $p.Start ([datetime]$r.Start))) {
            $out[$p.Id] = $p
            if ($p.Name -notmatch $script:Barrier) { $queue.Enqueue($p) }   # a recorded game is ours, its children aren't searched
        }
    }
    while ($queue.Count) {
        $parent = $queue.Dequeue()
        foreach ($c in @($byParent[$parent.Id])) {
            if ($c -and -not $out.ContainsKey($c.Id) -and $c.Id -ne $parent.Id -and $c.Name -notmatch $script:Barrier -and
                $c.Start -and $parent.Start -and ([datetime]$c.Start) -ge ([datetime]$parent.Start).AddSeconds(-1)) {
                $out[$c.Id] = $c; $queue.Enqueue($c)
            }
        }
    }
    @($out.Values)
}

function Get-ForeignProcs($records, $snapshot) {
    # F1_25* and swofty* (the launcher, its swofty.exe sessions) that aren't ours
    $ours = @{}
    foreach ($p in (Get-OursTree $records $snapshot)) { $ours[$p.Id] = $true }
    @($snapshot | Where-Object { ($_.Name -match '^F1_25' -or $_.Name -match '^swofty') -and -not $ours.ContainsKey($_.Id) })
}

function Ours-Init([string] $runDir) {
    New-Item -ItemType Directory -Force $runDir | Out-Null
    $script:OursFile = Join-Path (Resolve-Path $runDir).Path 'ours.csv'
    if (-not (Test-Path $script:OursFile)) { Set-Content $script:OursFile 'Id,Start,Name,Role,Recorded' -Encoding utf8 }
}

function Ours-Records {
    if (-not $script:OursFile -or -not (Test-Path $script:OursFile)) { return @() }
    @(Import-Csv $script:OursFile)
}

function Ours-AddId([int] $id, [string] $role) {
    if (-not $script:OursFile) { throw 'Ours-Init first' }
    $p = Get-ProcSnapshot | Where-Object { $_.Id -eq $id } | Select-Object -First 1
    if (-not $p) { return $false }
    if ($p.Name -match $script:NeverOurs) { Write-Host "ours: refusing to record $($p.Name) $($p.Id): never ours"; return $false }
    Add-Content $script:OursFile ('{0},{1},{2},"{3}",{4}' -f $p.Id, ([datetime]$p.Start).ToString('o'), $p.Name, $role, (Get-Date).ToString('o')) -Encoding utf8
    $true
}

function Ours-Add($proc, [string] $role) {
    if ($proc) { Ours-AddId ([int]$proc.Id) $role | Out-Null }
}

function Ours-Foreign {
    Get-ForeignProcs (Ours-Records) (Get-ProcSnapshot)
}

function Ours-StopOne($proc, [string] $reason = '') {
    # one process we started (e.g. the UDP capture): stopped only if it is recorded with the same start time
    if (-not $proc) { return $false }
    $snap = Get-ProcSnapshot
    $rec = @(Ours-Records | Where-Object { [int]$_.Id -eq [int]$proc.Id })
    $live = $snap | Where-Object { $_.Id -eq [int]$proc.Id } | Select-Object -First 1
    if (-not $rec.Count -or -not $live -or -not (Same-Start $live.Start ([datetime]$rec[-1].Start))) { return $false }
    Stop-Process -Id $live.Id -Force -ErrorAction SilentlyContinue   # recorded PID, start time verified
    Write-Host "ours: stopped $($live.Name) $($live.Id) ($reason)"
    $true
}

function Ours-Stop([string] $reason = '') {
    # stops our recorded processes (and their trees) only; refuses while anything foreign is running
    $snap = Get-ProcSnapshot
    $rec = Ours-Records
    $foreign = Get-ForeignProcs $rec $snap
    if ($foreign.Count) {
        Write-Host ("ours: NOT stopping anything ($reason): not ours running: " + (($foreign | ForEach-Object { "$($_.Name) $($_.Id)" }) -join ', '))
        return $false
    }
    $tree = Get-OursTree $rec $snap
    foreach ($p in $tree | Sort-Object { [datetime]$_.Start } -Descending) {
        Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue   # by recorded PID, start time verified above
    }
    if ($tree.Count) { Write-Host ("ours: stopped ($reason): " + (($tree | ForEach-Object { "$($_.Name) $($_.Id)" }) -join ', ')) }
    $true
}
