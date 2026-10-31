<#
Replace this PC's account details in run logs before they are committed (the repo is public; supervisor's review of
#62): the user folder becomes %USERPROFILE%, the Steam account id becomes <steamid> and the 64-bit Steam id
becomes <steam64>. Nothing here is secret, but none of it belongs in the repo.

Usage:
    powershell -File tools/scrub_logs.ps1 runs/<id> [more files or folders]

Rewrites text files (.txt .md .json .jsonl .csv .log .xml .plan) in place and prints how many were changed. The
ids are read from this PC at run time (tools/find_steam_app.ps1), so the script itself names none of them.
It can't know the player's gamertag: names in parser output go through tools/udp_parse.py's is_human.
#>
param([Parameter(Mandatory, ValueFromRemainingArguments)] [string[]] $Paths)
$ErrorActionPreference = 'Stop'
$account = & (Join-Path $PSScriptRoot 'find_steam_app.ps1') -AccountId
$steam64 = [string]([UInt64]76561197960265728 + [UInt64]$account)
$home_ = $env:USERPROFILE.TrimEnd('\')
# the user folder as logs write it: C:\Users\x, C:/Users/x, and JSON-escaped C:\\Users\\x
$homeRe = ([regex]::Escape($home_) -replace '\\\\', '(?:\\\\|\\|/)')
$rules = @(
    @{ re = "(?i)$homeRe"; to = '%USERPROFILE%' },
    @{ re = "(?<!\d)$steam64(?!\d)"; to = '<steam64>' },
    @{ re = "(?<!\d)$account(?!\d)"; to = '<steamid>' }
)
$ext = '.txt', '.md', '.json', '.jsonl', '.csv', '.log', '.xml', '.plan'
$files = foreach ($p in $Paths) {
    if (Test-Path $p -PathType Container) { Get-ChildItem $p -Recurse -File } else { Get-Item $p }
}
$changed = 0
foreach ($f in $files | Where-Object { $_.Extension -in $ext }) {
    $text = [IO.File]::ReadAllText($f.FullName)
    $new = $text
    foreach ($r in $rules) { $new = [regex]::Replace($new, $r.re, $r.to) }
    if ($new -ne $text) { [IO.File]::WriteAllText($f.FullName, $new, (New-Object Text.UTF8Encoding $false)); $changed++ }
}
"scrubbed $changed of $(@($files).Count) file(s)"
