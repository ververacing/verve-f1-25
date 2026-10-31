<#
Print the Steam userdata folder that holds F1 25's saves (`<Steam>\userdata\<steamid>\3059520`), found at run time
so no account id is written into the repo.

Usage:
    $app = & tools/find_steam_app.ps1            # the folder; `remote\` and `remotecache.vdf` are inside it
    & tools/find_steam_app.ps1 -AccountId        # just the <steamid> folder name (used by scrub_logs.ps1)

The Steam folder comes from the registry (HKCU\Software\Valve\Steam, SteamPath), else the default install path.
More than one account with F1 25 saves on this PC is an error: name the folder with the caller's -SteamApp then.
#>
param([switch] $AccountId, [string] $AppId = '3059520')
$ErrorActionPreference = 'Stop'
$steam = (Get-ItemProperty 'HKCU:\Software\Valve\Steam' -Name SteamPath -ErrorAction SilentlyContinue).SteamPath
if (-not $steam -or -not (Test-Path $steam)) { $steam = 'C:\Program Files (x86)\Steam' }
$found = @(Get-ChildItem (Join-Path $steam 'userdata') -Directory -ErrorAction SilentlyContinue |
    Where-Object { Test-Path (Join-Path $_.FullName "$AppId\remote") })
if ($found.Count -ne 1) { throw "expected one Steam account with F1 25 saves under $steam\userdata, found $($found.Count)" }
if ($AccountId) { $found[0].Name } else { (Resolve-Path (Join-Path $found[0].FullName $AppId)).Path }
