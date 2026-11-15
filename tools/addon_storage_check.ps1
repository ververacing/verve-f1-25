<#
Pre-run refusal (supervisor, 2026-11-14). On 1.9.x `swofty test` stores and swaps addon data under the ACTIVE
profile's name (addon-profiles\<addon>\<active>), even when the run uses an isolated profile such as verve-test. The
active profile is Tyler's. So before a launch: if any addon the run switches on has data under the active profile's
name, refuse and report it. Read-only.

Usage:
    powershell -File tools/addon_storage_check.ps1 -ExpProfile verve-test [-Addon id1,id2]   # exit 0 = clear, 1 = refuse
#>
param(
    [Parameter(Mandatory)] [string] $ExpProfile,
    [string[]] $Addon = @()
)
$ErrorActionPreference = 'Stop'
# under `powershell -File`, -Addon a,b arrives as ONE string "a,b": split it (supervisor review, PR #75)
$Addon = @($Addon | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ })
$data = Join-Path $env:LOCALAPPDATA 'Swofty'
$active = (Get-Content (Join-Path $data 'config.json') -Raw | ConvertFrom-Json).active_profile
$prof = Get-Content (Join-Path $data "profiles\$ExpProfile.json") -Raw | ConvertFrom-Json
$ids = @($prof.addons | Where-Object { $_.enabled } | ForEach-Object { $_.id }) + $Addon | Select-Object -Unique
$hits = foreach ($id in $ids) {
    $d = Join-Path $data "addon-profiles\$id\$active"
    if (Test-Path $d) {
        $f = @(Get-ChildItem $d -Recurse -File -Force)
        if ($f.Count) { "$id`: $($f.Count) file(s) under addon-profiles\$id\$active" }
    }
    # the LIVE data: while .current names a profile that isn't ours (tyler, or one Tyler makes), that profile's files
    # are in addon-storage\<id>\ (addon_storage.rs Holder::Storage). Swofty's top-level dot-files are markers.
    $cur = Join-Path $data "addon-profiles\$id\.current"
    $label = if (Test-Path $cur) { (Get-Content $cur -Raw).Trim() } else { '' }
    $live = Join-Path $data "addon-storage\$id"
    if ($label -notlike 'verve-*' -and $label -notlike 'test-*' -and (Test-Path $live)) {
        $f = @(Get-ChildItem $live -Recurse -File -Force | Where-Object { -not ($_.DirectoryName -eq $live -and $_.Name.StartsWith('.')) })
        if ($f.Count) { "$id`: $($f.Count) file(s) of live data under addon-storage\$id (.current = '$label')" }
    }
}
if ($hits) { "REFUSE: addons in this run have data under the active profile ($active):"; $hits; exit 1 }
"addon storage clear: none of $($ids.Count) addon(s) has data under the active profile ($active)"
exit 0
