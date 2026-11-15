<#
Steam's per-file records in remotecache.vdf (size, sha, localtime): the same parse as tools/guard_snapshot.ps1's
`steam <name>` entries. Steam rewrites the vdf on every game exit, ours included, so its raw bytes are never compared;
only these records are (supervisor review of #110). Dot-source it:

    . (Join-Path $PSScriptRoot 'steam_records.ps1')
    Get-SteamRecords <vdf text>                     # ordered: name -> "size sha localtime"
    Compare-SteamRecords <vdf text> <lkg steam_records.csv rows>   # the differences, empty when equal
#>

function Get-SteamRecords([string] $vdf) {
    $h = [ordered]@{}
    foreach ($m in [regex]::Matches($vdf, '"([^"]+)"\s*\{([^{}]*)\}')) {
        $fields = foreach ($k in 'size', 'sha', 'localtime') { [regex]::Match($m.Groups[2].Value, "`"$k`"\s*`"([^`"]*)`"").Groups[1].Value }
        if ($fields[1]) { $h[$m.Groups[1].Value] = $fields -join ' ' }
    }
    $h
}

function Compare-SteamRecords([string] $vdf, $lkgRows) {
    $now = Get-SteamRecords $vdf
    $was = [ordered]@{}
    foreach ($r in $lkgRows) { $was[$r.name] = "$($r.size) $($r.sha) $($r.localtime)" }
    foreach ($k in @($was.Keys) + @($now.Keys) | Select-Object -Unique) {
        if ($was[$k] -ne $now[$k]) { "${k}: $($was[$k]) -> $($now[$k])" }
    }
}
