<#
Refuse a commit that would publish this PC's account details or raw game captures (supervisor's review of #63,
after b5eb3b0 pushed 276 frames, some showing the gamertag). The repo is public.

Refuses when the staged changes:
- add an image (.png .jpg .jpeg .gif .bmp .webp) outside harness/fixtures/frames/ and docs/ (checked crops only);
- add a line containing the user folder, the Steam account id or the 64-bit Steam id (run tools/scrub_logs.ps1).

Install in a local clone (once):
    powershell -File tools/pre_commit_check.ps1 -Install
which writes .git/hooks/pre-commit to call this script. `git commit --no-verify` skips it: don't.
#>
param([switch] $Install)
$ErrorActionPreference = 'Stop'
$git = 'git'
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { $git = 'C:\Program Files\Git\cmd\git.exe' }
if ($Install) {
    $hooks = (& $git rev-parse --git-path hooks)
    New-Item -ItemType Directory -Force $hooks | Out-Null
    $hook = "#!/bin/sh`nexec powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/pre_commit_check.ps1`n"
    [IO.File]::WriteAllText((Join-Path $hooks 'pre-commit'), $hook, (New-Object Text.UTF8Encoding $false))
    "installed $hooks\pre-commit"; exit 0
}

$problems = @()
foreach ($line in & $git diff --cached --name-status --diff-filter=ACMR) {
    $path = ($line -split "`t")[-1]
    if ($path -match '\.(png|jpe?g|gif|bmp|webp)$' -and $path -notmatch '^(harness/fixtures/frames|docs)/') {
        $problems += "image outside harness/fixtures/frames/ or docs/: $path"
    }
}
$account = & (Join-Path $PSScriptRoot 'find_steam_app.ps1') -AccountId
$steam64 = [string]([UInt64]76561197960265728 + [UInt64]$account)
$homeRe = ([regex]::Escape($env:USERPROFILE.TrimEnd('\')) -replace '\\\\', '(?:\\\\|\\|/)')
$checks = @{ 'user folder' = "(?i)$homeRe"; 'Steam account id' = "(?<!\d)$account(?!\d)"; '64-bit Steam id' = "(?<!\d)$steam64(?!\d)" }
$file = ''
foreach ($l in & $git diff --cached -U0 --no-color) {
    if ($l -match '^\+\+\+ b/(.*)$') { $file = $Matches[1]; continue }
    if (-not $l.StartsWith('+') -or $l.StartsWith('+++')) { continue }
    foreach ($k in $checks.Keys) { if ($l -match $checks[$k]) { $problems += "${k} in $file (run tools/scrub_logs.ps1)" } }
}
if ($problems) {
    'pre-commit: refused'
    $problems | Select-Object -Unique | ForEach-Object { "  $_" }
    exit 1
}
exit 0
