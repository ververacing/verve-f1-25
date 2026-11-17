<#
Low-graphics test preset for hardware_settings_config.xml (supervisor's spec, 2026-11-16), swapped in just before a
launch and Tyler's own file swapped back, byte-identical, on every exit path. OPT-IN only: the runners do it only
with -LowGraphics; pause and pre-flight act only while the state file says a swap is active, else they are a no-op.

Usage:
    powershell -File tools/hw_swap.ps1 -In [-Tag <run>] [-Log <run>\hw_swap.txt]
        The live file must equal Tyler's reference BY VALUE (tools/hw_settings.ps1, Compare-HwValues), else it stops
        (exit 2) and writes nothing. Then: a dated byte copy of the live file (the backup that -Back restores), the
        test preset built from it by KEY EDITS (tools/hw_test_preset_keys.csv), the state file (active), and the
        preset written live with its SHA-256 checked. A swap left active by an earlier run is recovered first (as
        -Recover).
    powershell -File tools/hw_swap.ps1 -Back [-Log <file>]
        Restores Tyler's file from the dated backup, byte-identical (SHA-256 checked, one retry). Idempotent: with no
        swap active it does nothing (exit 0). Deferred (exit 3) while F1 25 runs: the game rewrites the file on quit.
    powershell -File tools/hw_swap.ps1 -Recover
        Pre-flight: no swap active = silent no-op. Active and the live file is the recorded preset (by hash, or by value
        after the game re-serialised it) = restore Tyler's file and log it. Anything else = stop and report (exit 2).
    powershell -File tools/hw_swap.ps1 -PauseGate
        tools/safe_to_play.ps1: -Back, printing one line only on failure: "WAIT: ... URGENT: message the supervisor".
    powershell -File tools/hw_swap.ps1 -Status
    powershell -File tools/hw_swap.ps1 -Preview -Source <copy.xml> [-OutFile <preset.xml>]
        The preset of a COPY, with the edit log; nothing live is read or written.

Exit codes: 0 done (or nothing to do); 1 WAIT (-PauseGate only); 2 refused, the live file is in an unknown state
(nothing written); 3 F1 25 is running (nothing written); 5 a file is missing or unreadable (nothing written); 6 the
preset write failed and Tyler's file was restored; 7 URGENT: Tyler's file could not be restored (tell the supervisor).

The preset changes ONLY the declared graphics/display keys: every edit replaces one attribute value in the text, so
every other byte (motion/udp, controls, audio, devices, layout) stays identical. A declared key the file doesn't have,
or whose value isn't of the declared form, is not edited, and the log says so. The backups (Tyler's reference, which
tools/preflight.ps1 already keeps, plus the dated byte copies) live under %LOCALAPPDATA%\verve-f1-25 only, never in
the repo: the file can hold device names.
Test hooks (tools/test_hw_swap.ps1): -Live, -Reference, -StateFile, -BackupDir, -LogFile, -KeysCsv, -GameProcess.
Dot-sourced with no mode switch it only defines its functions.
#>
param(
    [switch] $In,
    [switch] $Back,
    [switch] $Recover,
    [switch] $PauseGate,
    [switch] $Status,
    [switch] $Preview,
    [string] $Tag = '',
    [string] $Log = '',
    [string] $Live = '',
    [string] $Reference = '',
    [string] $StateFile = (Join-Path $env:LOCALAPPDATA 'verve-f1-25\state\hw_swap.json'),
    [string] $BackupDir = (Join-Path $env:LOCALAPPDATA 'verve-f1-25\settings-snapshots\hw-swap'),
    [string] $LogFile = (Join-Path $env:LOCALAPPDATA 'verve-f1-25\state\hw_swap.log'),
    [string] $KeysCsv = (Join-Path $PSScriptRoot 'hw_test_preset_keys.csv'),
    [string] $GameProcess = 'F1_25',
    [string] $Source = '',
    [string] $OutFile = ''
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'hw_settings.ps1')
if (-not $Live) { $Live = $HwFile }
if (-not $Reference) { $Reference = $HwReference }
$script:HwQuiet = $false
$script:HwRoot = 'hardware_settings_config'
$Utf8NoBom = New-Object Text.UTF8Encoding $false

# keys whose values can name Tyler's devices or folders: a log line about one of them shows '<private>' for its values,
# since run-folder logs (hw_swap.txt, transcript.txt) are committed
$script:HwPrivate = '(cpu@name|graphics_card@deviceId|replay_directory@path)'
function HwSay([string] $s, [switch] $FileOnly) {
    if ($s -match $script:HwPrivate) { $s = $s -replace "'[^']*'", "'<private>'" }
    $line = "$(Get-Date -Format s) $s"
    foreach ($f in @($LogFile, $Log)) {
        if (-not $f) { continue }
        try {
            $dir = Split-Path $f -Parent
            if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force $dir | Out-Null }
            [IO.File]::AppendAllText($f, "$line`r`n", $Utf8NoBom)
        } catch { }
    }
    if (-not $script:HwQuiet -and -not $FileOnly) { Write-Host $s }
}

function HwShaBytes([byte[]] $b) {
    $h = [Security.Cryptography.SHA256]::Create()
    try { -join ($h.ComputeHash($b) | ForEach-Object { $_.ToString('X2') }) } finally { $h.Dispose() }
}
function HwShaFile([string] $f) {
    if (-not (Test-Path -LiteralPath $f)) { return 'MISSING' }
    HwShaBytes ([IO.File]::ReadAllBytes($f))
}

function HwDecode([byte[]] $b) {
    # the text and how to write it back byte for byte (BOM and encoding kept; invalid bytes throw)
    $pre = 0
    if ($b.Length -ge 3 -and $b[0] -eq 0xEF -and $b[1] -eq 0xBB -and $b[2] -eq 0xBF) { $enc = New-Object Text.UTF8Encoding($false, $true); $pre = 3 }
    elseif ($b.Length -ge 2 -and $b[0] -eq 0xFF -and $b[1] -eq 0xFE) { $enc = New-Object Text.UnicodeEncoding($false, $false, $true); $pre = 2 }
    elseif ($b.Length -ge 2 -and $b[0] -eq 0xFE -and $b[1] -eq 0xFF) { $enc = New-Object Text.UnicodeEncoding($true, $false, $true); $pre = 2 }
    else { $enc = New-Object Text.UTF8Encoding($false, $true) }
    $preamble = New-Object byte[] $pre
    if ($pre) { [Array]::Copy($b, $preamble, $pre) }
    @{ Text = $enc.GetString($b, $pre, $b.Length - $pre); Enc = $enc; Pre = $preamble }
}
function HwEncode($d, [string] $text) {
    $body = $d.Enc.GetBytes($text)
    $out = New-Object byte[] ($d.Pre.Length + $body.Length)
    [Array]::Copy($d.Pre, $out, $d.Pre.Length)
    [Array]::Copy($body, 0, $out, $d.Pre.Length, $body.Length)
    , $out
}
function HwSameBytes([byte[]] $a, [byte[]] $b) {
    if ($a.Length -ne $b.Length) { return $false }
    for ($i = 0; $i -lt $a.Length; $i++) { if ($a[$i] -ne $b[$i]) { return $false } }
    $true
}

function Get-HwAttrSpans([string] $text) {
    # every attribute of every element, keyed as Get-HwValues keys them ("hw <path>@<attr>"), with the position and
    # length of its raw value in $text. Comments, PIs, CDATA and declarations are skipped.
    $rx = [regex]'<!--[\s\S]*?-->|<\?[\s\S]*?\?>|<!\[CDATA\[[\s\S]*?\]\]>|<![^>]*>|</\s*([^\s>]+)\s*>|<([^\s/>!?]+)((?:\s+[^\s=/>]+\s*=\s*(?:"[^"]*"|''[^'']*''))*)\s*(/?)>'
    $arx = [regex]'\s+([^\s=/>]+)\s*=\s*(?:"([^"]*)"|''([^'']*)'')'
    $spans = [ordered]@{}
    $stack = New-Object System.Collections.ArrayList
    $seen = @{}
    foreach ($m in $rx.Matches($text)) {
        if ($m.Groups[1].Success) {
            if (-not $stack.Count) { throw "unbalanced end tag at $($m.Index)" }
            $local = ($m.Groups[1].Value -split ':')[-1]
            if ($stack[$stack.Count - 1] -ne $local) { throw "end tag </$local> does not close <$($stack[$stack.Count - 1])> at $($m.Index)" }
            $stack.RemoveAt($stack.Count - 1); continue
        }
        if (-not $m.Groups[2].Success) { continue }
        $local = ($m.Groups[2].Value -split ':')[-1]
        [void]$stack.Add($local)
        $p = @($stack) -join '/'
        $seen[$p] = 1 + [int]$seen[$p]
        if ($seen[$p] -gt 1) { $p = "$p[$($seen[$p])]" }
        $base = $m.Groups[3].Index
        foreach ($a in $arx.Matches($m.Groups[3].Value)) {
            $g = if ($a.Groups[2].Success) { $a.Groups[2] } else { $a.Groups[3] }
            $an = ($a.Groups[1].Value -split ':')[-1]
            $spans["hw $p@$an"] = @{ Start = $base + $g.Index; Length = $g.Length; Raw = $g.Value }
        }
        if ($m.Groups[4].Value -eq '/') { $stack.RemoveAt($stack.Count - 1) }
    }
    if ($stack.Count) { throw "unclosed element <$($stack[$stack.Count - 1])>" }
    $spans
}

function Get-HwPresetRules([string] $csv) {
    $rows = @(Import-Csv $csv)
    foreach ($r in $rows) {
        if ($r.key -notmatch '^[\w\[\]/]+@\w+$') { throw "${csv}: bad key '$($r.key)'" }
        if ($r.form -notin 'flag', 'int', 'num', 'word') { throw "${csv}: $($r.key): unknown form '$($r.form)'" }
        if ($r.test_value -notmatch '^[\w.\-]+$') { throw "${csv}: $($r.key): test value '$($r.test_value)' must be plain letters, digits, '.', '-'" }
        if ($r.form -eq 'flag' -and $r.test_value -notin 'on', 'off') { throw "${csv}: $($r.key): a flag's test value is on or off" }
        if ($r.status -notin 'ok', 'unverified') { throw "${csv}: $($r.key): status is ok or unverified" }
    }
    $rows
}

function Test-HwForm([string] $form, [string] $v) {
    switch ($form) {
        'flag' { return ($v -match '^(?i)(true|false|0|1)$') }
        'int' { return ($v -match '^-?\d+$') }
        'num' { return ($v -match '^-?\d+(\.\d+)?$') }
        'word' { return ($v -match '^[A-Za-z][A-Za-z_\-]*$') }
    }
    $false
}
function Resolve-HwValue($rule, [string] $cur) {
    if ($rule.form -ne 'flag') { return $rule.test_value }
    $on = $rule.test_value -eq 'on'
    if ($cur -match '^[01]$') { if ($on) { return '1' } else { return '0' } }
    $w = if ($on) { 'true' } else { 'false' }
    if ($cur -cmatch '^[A-Z]+$') { return $w.ToUpper() }
    if ($cur -cmatch '^[A-Z]') { return ($w.Substring(0, 1).ToUpper() + $w.Substring(1)) }
    $w
}

function Build-HwPreset([byte[]] $src, $rules) {
    # -> @{ Bytes; Edits (Key, Start, Length, Old, New); Lines (the edit log) }. Throws if the text can't be read back
    # byte for byte or its keys don't match the XML reader's.
    $d = HwDecode $src
    if (-not (HwSameBytes (HwEncode $d $d.Text) $src)) { throw 'the file does not read back byte for byte in its own encoding; not edited' }
    $spans = Get-HwAttrSpans $d.Text
    $tmp = [IO.Path]::GetTempFileName()
    try { [IO.File]::WriteAllBytes($tmp, $src); $xmlKeys = @((Get-HwValues $tmp).Keys) } finally { Remove-Item $tmp -Force -ErrorAction SilentlyContinue }
    $missingKeys = @($xmlKeys | Where-Object { -not $spans.Contains($_) })
    if ($missingKeys.Count -or $xmlKeys.Count -ne $spans.Count) { throw "the text scan and the XML reader disagree on the keys ($($missingKeys.Count) missing); not edited" }
    $byKey = [ordered]@{}
    foreach ($r in $rules) { $k = "hw $script:HwRoot/$($r.key)"; if (-not $byKey.Contains($k)) { $byKey[$k] = @() }; $byKey[$k] += $r }
    $lines = @(); $edits = @(); $result = @{}
    foreach ($e in $spans.GetEnumerator()) { $result[$e.Key] = $e.Value.Raw }
    foreach ($pass in 1, 2) {
        foreach ($k in $byKey.Keys) {
            $rs = $byKey[$k]
            $hasReq = @($rs | Where-Object { $_.requires }).Count -gt 0
            if (($pass -eq 1) -eq $hasReq) { continue }   # pass 1: plain keys; pass 2: keys that depend on another key's result
            $short = $k.Substring(3 + $script:HwRoot.Length + 1)
            if (-not $spans.Contains($k)) { $lines += "missing: $short is not in this file; no edit"; continue }
            $cur = $spans[$k].Raw
            if ($cur -match '[&<>]') { $lines += "skipped: ${short}: its value has XML escapes; no edit"; continue }
            $rule = $rs | Where-Object { Test-HwForm $_.form $cur } | Select-Object -First 1
            if (-not $rule) { $lines += "form not recognised: $short is '$cur', not $((@($rs | ForEach-Object { $_.form }) | Select-Object -Unique) -join '/'); no edit"; continue }
            if ($rule.requires) {
                $rk, $rrx = $rule.requires -split '~', 2
                $rv = $result["hw $script:HwRoot/$rk"]
                if ($null -eq $rv -or $rv -notmatch $rrx) { $lines += "not edited: $short needs $rk ~ $rrx, and it is '$rv'"; continue }
            }
            $new = Resolve-HwValue $rule $cur
            if ($new -ceq $cur) { $lines += "already: $short = '$cur'"; continue }
            $edits += [pscustomobject]@{ Key = $k; Start = $spans[$k].Start; Length = $spans[$k].Length; Old = $cur; New = $new }
            $result[$k] = $new
            $lines += "set: ${short}: '$cur' -> '$new'$(if ($rule.status -eq 'unverified') { ' (unverified)' })"
        }
    }
    $sb = New-Object Text.StringBuilder $d.Text
    foreach ($e in $edits | Sort-Object Start -Descending) { [void]$sb.Remove($e.Start, $e.Length).Insert($e.Start, $e.New) }
    @{ Bytes = (HwEncode $d $sb.ToString()); Edits = $edits; Lines = $lines }
}

function Test-HwPresetDiff([string] $srcFile, [string] $presetFile, $edits) {
    # the preset against its source BY VALUE: exactly the edited keys, each at its new value. Returns the problems.
    $want = @{}; foreach ($e in $edits) { $want[$e.Key] = $e.New }
    $a = Get-HwValues $srcFile; $b = Get-HwValues $presetFile
    $bad = @()
    foreach ($k in (@($a.Keys) + @($b.Keys) | Sort-Object -Unique)) {
        if ($want.ContainsKey($k)) { if ($b[$k] -cne $want[$k]) { $bad += "${k}: wanted '$($want[$k])', got '$($b[$k])'" } }
        elseif ($a[$k] -cne $b[$k]) { $bad += "${k}: not declared, but '$($a[$k])' -> '$($b[$k])'" }
    }
    $bad
}

# ---- state ----
function Read-HwState {
    if (-not (Test-Path -LiteralPath $StateFile)) { return $null }
    Get-Content -LiteralPath $StateFile -Raw | ConvertFrom-Json
}
function Write-HwState($st) {
    $dir = Split-Path $StateFile -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force $dir | Out-Null }
    [IO.File]::WriteAllText($StateFile, ($st | ConvertTo-Json -Depth 4), $Utf8NoBom)
}
function Set-HwStateField($st, [string] $name, $value) { $st | Add-Member -NotePropertyName $name -NotePropertyValue $value -Force }

function Test-HwGameUp { @(Get-Process -Name $GameProcess -ErrorAction SilentlyContinue).Count -gt 0 }

function Write-HwVerified([string] $path, [byte[]] $bytes, [string] $sha) {
    # write, then read back and hash; one retry. $true when the file hashes as $sha
    for ($i = 0; $i -lt 2; $i++) {
        try { [IO.File]::WriteAllBytes($path, $bytes) } catch { HwSay "write failed ($($_.Exception.Message))" }
        if ((HwShaFile $path) -eq $sha) { return $true }
        Start-Sleep -Milliseconds 1000
    }
    $false
}

function Get-HwLiveKind($st) {
    # what is live now, for an active swap: tyler-bytes, preset-bytes, preset-values, tyler-values, other, missing
    if (-not (Test-Path -LiteralPath $Live)) { return @{ Kind = 'missing'; Diff = @() } }
    $sha = HwShaFile $Live
    if ($sha -eq $st.backupSha) { return @{ Kind = 'tyler-bytes'; Diff = @() } }
    if ($sha -eq $st.presetSha) { return @{ Kind = 'preset-bytes'; Diff = @() } }
    try {
        $vp = @(Compare-HwValues $st.preset $Live)
        if (-not $vp.Count) { return @{ Kind = 'preset-values'; Diff = @() } }
        if (-not @(Compare-HwValues $st.backup $Live).Count) { return @{ Kind = 'tyler-values'; Diff = @() } }
        if ((Test-Path -LiteralPath $Reference) -and -not @(Compare-HwValues $Reference $Live).Count) { return @{ Kind = 'tyler-values'; Diff = @() } }
        return @{ Kind = 'other'; Diff = $vp }
    } catch { return @{ Kind = 'other'; Diff = @("unreadable: $($_.Exception.Message)") } }
}

function Invoke-HwRestore($st, [string] $why) {
    # Tyler's bytes back from the dated backup, hash-checked. 0 restored, 3 game up (deferred), 7 URGENT
    if (Test-HwGameUp) { HwSay "DEFERRED ($why): $GameProcess is running (it rewrites the file on quit); the test preset stays live until pause or pre-flight restores it"; return 3 }
    if (-not (Test-Path -LiteralPath $st.backup) -or (HwShaFile $st.backup) -ne $st.backupSha) {
        HwSay "URGENT ($why): the backup of Tyler's file is missing or changed ($($st.backup)); NOT restored. Tell the supervisor (reference: $Reference)"
        return 7
    }
    $kind = Get-HwLiveKind $st
    if ($kind.Kind -eq 'tyler-bytes') { HwSay "restore ($why): Tyler's file is already live, byte-identical (sha $($st.backupSha.Substring(0, 12)))" }
    else {
        if ($kind.Kind -eq 'other') { HwSay "note ($why): the live file was neither the preset nor Tyler's file ($($kind.Diff.Count) key(s) differ from the preset); restoring Tyler's file over it"; $kind.Diff | Select-Object -First 20 | ForEach-Object { HwSay "  $_" } }
        Set-HwStateField $st 'phase' 'restoring'; Write-HwState $st
        $bytes = [IO.File]::ReadAllBytes($st.backup)
        if (-not (Write-HwVerified $Live $bytes $st.backupSha)) {
            HwSay "URGENT ($why): Tyler's file could not be restored: the live file does not hash as the backup after two writes. Tell the supervisor (backup: $($st.backup))"
            return 7
        }
        HwSay "restored ($why): Tyler's file, byte-identical (sha $($st.backupSha.Substring(0, 12)); live was $($kind.Kind))"
    }
    Set-HwStateField $st 'active' $false; Set-HwStateField $st 'phase' 'restored'
    Set-HwStateField $st 'restoredAt' (Get-Date -Format o); Set-HwStateField $st 'restoredWhy' $why
    Write-HwState $st
    0
}

function Invoke-HwRecover([string] $why) {
    # an active swap left behind: restore when the preset (by hash or value) is live; anything else is stop-and-report
    $st = Read-HwState
    if (-not $st -or -not $st.active) { return 0 }
    if (Test-HwGameUp) { HwSay "RECOVERY WAITS ($why): a swap is active and $GameProcess is running; nothing written"; return 3 }
    $kind = Get-HwLiveKind $st
    HwSay "recovery ($why): a swap from $($st.since) ($($st.tag)) is still active (phase $($st.phase)); live is $($kind.Kind)"
    if ($kind.Kind -in 'tyler-bytes', 'preset-bytes', 'preset-values' -or $st.phase -in 'writing', 'restoring') { return (Invoke-HwRestore $st $why) }
    if ($kind.Kind -eq 'tyler-values') {
        HwSay "recovery ($why): Tyler's values are live already; nothing written, swap closed"
        Set-HwStateField $st 'active' $false; Set-HwStateField $st 'phase' 'restored'; Set-HwStateField $st 'restoredAt' (Get-Date -Format o); Set-HwStateField $st 'restoredWhy' "$why (values already Tyler's)"
        Write-HwState $st; return 0
    }
    HwSay "STOP ($why): the live hardware settings are neither the recorded test preset nor Tyler's reference; nothing written. Report to the supervisor:"
    $kind.Diff | Select-Object -First 40 | ForEach-Object { HwSay "  vs preset: $_" }
    2
}

function Invoke-HwIn {
    if (Test-HwGameUp) { HwSay "REFUSED: $GameProcess is running; nothing written"; return 3 }
    $rc = Invoke-HwRecover 'before swap-in'
    if ($rc -ne 0) { HwSay "REFUSED: an earlier swap could not be closed (exit $rc); nothing written"; return $rc }
    foreach ($f in @($Live, $Reference, $KeysCsv)) { if (-not (Test-Path -LiteralPath $f)) { HwSay "REFUSED: missing $f; nothing written"; return 5 } }
    try { $chg = @(Compare-HwValues $Reference $Live) } catch { HwSay "REFUSED: unreadable ($($_.Exception.Message)); nothing written"; return 5 }
    if ($chg.Count) {
        HwSay "REFUSED: the live file differs from Tyler's reference by value ($($chg.Count) key(s)); never overwriting an unknown state. Report to the supervisor:"
        $chg | ForEach-Object { HwSay "  $_" }
        return 2
    }
    if (-not (Test-Path $BackupDir)) { New-Item -ItemType Directory -Force $BackupDir | Out-Null }
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $src = [IO.File]::ReadAllBytes($Live)
    $srcSha = HwShaBytes $src
    # the dated byte copy of Tyler's file (reused when an earlier copy has the same bytes)
    $backup = Get-ChildItem $BackupDir -File -Filter 'hardware_settings_config.tyler-*.xml' -ErrorAction SilentlyContinue |
        Where-Object { (HwShaFile $_.FullName) -eq $srcSha } | Select-Object -First 1 | ForEach-Object { $_.FullName }
    if (-not $backup) {
        $backup = Join-Path $BackupDir "hardware_settings_config.tyler-$stamp.xml"
        if (-not (Write-HwVerified $backup $src $srcSha)) { HwSay "REFUSED: the backup copy did not verify ($backup); nothing written"; return 5 }
    }
    try {
        $p = Build-HwPreset $src (Get-HwPresetRules $KeysCsv)
    } catch { HwSay "REFUSED: preset not built ($($_.Exception.Message)); nothing written"; return 5 }
    # every edit goes to the logs; only what the pilot must look at (missing keys, unknown forms) also to the console
    foreach ($l in $p.Lines) { HwSay "  $l" -FileOnly:($l -match '^(set|already): ') }
    if (-not $p.Edits.Count) { HwSay 'REFUSED: no declared key could be edited; nothing written'; return 5 }
    $presetSha = HwShaBytes $p.Bytes
    $preset = Join-Path $BackupDir "hardware_settings_config.preset-$($presetSha.Substring(0, 12)).xml"
    if ((HwShaFile $preset) -ne $presetSha -and -not (Write-HwVerified $preset $p.Bytes $presetSha)) { HwSay "REFUSED: the preset copy did not verify; nothing written"; return 5 }
    $bad = @(Test-HwPresetDiff $backup $preset $p.Edits)
    if ($bad.Count) { HwSay 'REFUSED: the preset differs from Tyler''s file beyond the declared keys; nothing written:'; $bad | ForEach-Object { HwSay "  $_" }; return 5 }
    # the state first, so a crash during the write is recovered (phase writing = restore unconditionally)
    $st = [pscustomobject]@{ active = $true; phase = 'writing'; since = (Get-Date -Format o); tag = $Tag; live = $Live
        backup = $backup; backupSha = $srcSha; preset = $preset; presetSha = $presetSha; reference = $Reference
        edits = $p.Edits.Count; restoredAt = ''; restoredWhy = '' }
    Write-HwState $st
    if (-not (Write-HwVerified $Live $p.Bytes $presetSha)) {
        HwSay 'FAILED: the test preset did not verify after writing; restoring Tyler''s file'
        $r = Invoke-HwRestore $st 'failed swap-in'
        if ($r -eq 0) { return 6 } else { return 7 }
    }
    Set-HwStateField $st 'phase' 'swapped'; Write-HwState $st
    $unv = @($p.Lines | Where-Object { $_ -match '^set: .*\(unverified\)$' }).Count
    HwSay "IN: test preset live ($($p.Edits.Count) key(s) edited, $unv of them unverified, $(@($p.Lines | Where-Object { $_ -notmatch '^(set|already): ' }).Count) not edited (hw_swap.txt); sha $($presetSha.Substring(0, 12))); Tyler's file kept at $backup (sha $($srcSha.Substring(0, 12)))$(if ($Tag) { "; $Tag" })"
    0
}

function Invoke-HwMain {
    $name = 'Local\verve-hw-swap-' + (HwShaBytes ([Text.Encoding]::UTF8.GetBytes(([IO.Path]::GetFullPath($StateFile)).ToLowerInvariant()))).Substring(0, 16)
    $mutex = New-Object Threading.Mutex($false, $name)
    $held = $false
    try {
        try { $held = $mutex.WaitOne(60000) } catch [Threading.AbandonedMutexException] { $held = $true }
        if (-not $held) { HwSay 'another hw_swap call held the lock for 60 s'; if ($PauseGate) { 'WAIT: hardware settings swap is busy (another hw_swap call). URGENT: message the supervisor if it repeats'; return 1 }; return 7 }
        if ($In) { return (Invoke-HwIn) }
        if ($Back) {
            $st = Read-HwState
            if (-not $st -or -not $st.active) { HwSay 'back: no swap active; nothing to do'; return 0 }
            # a tagged swap-back (a runner's, for its own run) never touches another run's swap
            if ($Tag -and $st.tag -ne $Tag) { HwSay "back: the active swap is another run's ($($st.tag)); not touched"; return 0 }
            return (Invoke-HwRestore $st 'swap-back')
        }
        if ($Recover) { return (Invoke-HwRecover 'pre-flight') }
        if ($PauseGate) {
            $script:HwQuiet = $true
            $st = Read-HwState
            if (-not $st -or -not $st.active) { return 0 }
            $r = Invoke-HwRestore $st 'pause'
            if ($r -eq 0) { return 0 }
            $last = Get-Content -LiteralPath $LogFile -Tail 1 -ErrorAction SilentlyContinue
            "WAIT: Tyler's hardware settings are NOT restored (the low-graphics test preset is still live; hw_swap exit ${r}: $(($last -replace '^\S+ ', '').Trim())). URGENT: message the supervisor now"
            return 1
        }
        if ($Status) {
            $st = Read-HwState
            if (-not $st) { 'no swap on record'; return 0 }
            $st | Format-List | Out-String -Width 200
            if ($st.active) { "live now: $((Get-HwLiveKind $st).Kind)" }
            return 0
        }
        if ($Preview) {
            if (-not $Source) { 'preview needs -Source <a copy of the file>'; return 5 }
            $src = [IO.File]::ReadAllBytes($Source)
            $p = Build-HwPreset $src (Get-HwPresetRules $KeysCsv)
            $p.Lines
            "preview: $($p.Edits.Count) key(s) edited"
            if ($OutFile) { [IO.File]::WriteAllBytes($OutFile, $p.Bytes); "preview written: $OutFile (sha $(HwShaBytes $p.Bytes))" }
            return 0
        }
    } finally {
        if ($held) { $mutex.ReleaseMutex() }
        $mutex.Dispose()
    }
}

if ($In -or $Back -or $Recover -or $PauseGate -or $Status -or $Preview) {
    try { $code = Invoke-HwMain } catch {
        HwSay "ERROR: $($_.Exception.Message)"
        if ($PauseGate) { "WAIT: Tyler's hardware settings could not be checked or restored (hw_swap error: $($_.Exception.Message)). URGENT: message the supervisor now"; exit 1 }
        exit 7
    }
    $lines = @($code)
    $exit = [int]$lines[-1]
    if ($lines.Count -gt 1) { $lines[0..($lines.Count - 2)] }
    exit $exit
}
