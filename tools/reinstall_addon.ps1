<#
Install an addon folder cleanly, or uninstall it, working around `swofty addons install` failing on this PC with
"files are still in use" when it replaces an existing install (docs/harness.md, PC hygiene).

Usage:
    powershell -File tools/reinstall_addon.ps1 -Folder <addon folder>       # reinstall from the folder
    powershell -File tools/reinstall_addon.ps1 -Id <addon id> -Uninstall   # remove it from disk and every profile

The addon id is read from the folder's swofty.json. Removes %LOCALAPPDATA%\Swofty\addons\<id> and any
.installing-<id> staging folder (retrying while something briefly holds them), then installs. Profiles that already
enable the id keep it enabled.
#>
param(
    [string] $Folder,
    [string] $Id,
    [switch] $Uninstall,
    [string] $Swofty = "$env:LOCALAPPDATA\Programs\SwoftyLauncher\bin\swofty.exe"
)
$ErrorActionPreference = 'Stop'
if ($Folder) { $Id = (Get-Content (Join-Path $Folder 'swofty.json') -Raw | ConvertFrom-Json).id }
if (-not $Id) { throw 'pass -Folder or -Id' }
if ($Id -notmatch '^[a-z0-9._-]+$') { throw "unexpected addon id '$Id'" }
$addons = Join-Path $env:LOCALAPPDATA 'Swofty\addons'

function Remove-WithRetry([string] $path) {
    for ($i = 1; $i -le 6; $i++) {
        if (-not (Test-Path $path)) { return }
        try { Remove-Item -Recurse -Force $path -Confirm:$false -ErrorAction Stop; return }
        catch { Start-Sleep -Seconds (2 * $i) }
    }
    throw "could not remove $path (still locked)"
}

if ($Uninstall) {
    & $Swofty addons remove $Id --yes
    if ($LASTEXITCODE -ne 0) {
        # remove's own delete hits the same lock; clear the files, then drop the id from every profile file
        Remove-WithRetry (Join-Path $addons $Id)
        Remove-WithRetry (Join-Path $addons ".installing-$Id")
        foreach ($p in Get-ChildItem (Join-Path $env:LOCALAPPDATA 'Swofty\profiles') -Filter *.json) {
            $j = Get-Content $p.FullName -Raw | ConvertFrom-Json
            if ($j.addons | Where-Object id -eq $Id) {
                $j.addons = @($j.addons | Where-Object id -ne $Id)
                [IO.File]::WriteAllText($p.FullName, ($j | ConvertTo-Json -Depth 10), (New-Object System.Text.UTF8Encoding $false))
                "dropped $Id from profile $($p.BaseName)"
            }
        }
    }
    "uninstalled $Id"
    return
}

Remove-WithRetry (Join-Path $addons ".installing-$Id")
Remove-WithRetry (Join-Path $addons $Id)
& $Swofty addons install $Folder
if ($LASTEXITCODE -ne 0) { throw "swofty addons install failed ($LASTEXITCODE)" }
