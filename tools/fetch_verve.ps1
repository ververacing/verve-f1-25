<#
Fetch Verve's lib/drivers.lua at the commit verve_to_swofty.py pins, into .cache/verve/<commit>/ (gitignored) (#5).

Usage:
    powershell -File tools/fetch_verve.ps1

The file holds Verve's whole multi-series roster, which stays off this repo: only the F1 rows the crosswalk names are
read, and only their derived values reach the addon. Needs the GitHub CLI signed in (ververacing/verve is public).
#>
param(
    [string] $Commit = '80d1798385ac4d62c20677a68ef508a4740dfd68',
    [string] $Gh = 'gh'
)
$ErrorActionPreference = 'Stop'
$dir = Join-Path (Split-Path $PSScriptRoot -Parent) ".cache\verve\$Commit"
New-Item -ItemType Directory -Force $dir | Out-Null
$out = Join-Path $dir 'drivers.lua'
$text = & $Gh api "repos/ververacing/verve/contents/lib/drivers.lua?ref=$Commit" -H 'Accept: application/vnd.github.raw'
if ($LASTEXITCODE -ne 0) { throw "gh api failed ($LASTEXITCODE)" }
# write the bytes as served (LF), so the generator's git blob hash check matches
[IO.File]::WriteAllText($out, (($text -join "`n") + "`n"), (New-Object Text.UTF8Encoding $false))
"wrote $out"
