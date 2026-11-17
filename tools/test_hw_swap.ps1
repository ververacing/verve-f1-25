<#
Selftests for tools/hw_swap.ps1 and its hooks. Pure: synthetic hardware_settings_config.xml files in a temp folder
(the layout of the game's file, with made-up values), never the real file, Tyler's reference, the state folder or any
game, Swofty or Steam path. No process is started except child powershell runs of hw_swap.ps1 and of a stub runner;
"the game is running" is simulated with -GameProcess set to this test's own process name.

Usage:
    powershell -File tools/test_hw_swap.ps1      # exit 0 ok, 1 failed
#>
$ErrorActionPreference = 'Stop'
$tools = $PSScriptRoot
$swap = Join-Path $tools 'hw_swap.ps1'
$keys = Join-Path $tools 'hw_test_preset_keys.csv'
$root = Join-Path $env:TEMP "hw_swap_test_$PID"
if (Test-Path $root) { Remove-Item $root -Recurse -Force }
New-Item -ItemType Directory -Force $root | Out-Null
$failed = 0
function Check([string] $label, [bool] $ok, $detail = '') {
    if (-not $ok) { $script:failed++ }
    "{0} {1}{2}" -f $(if ($ok) { 'ok  ' } else { 'FAIL' }), $label, $(if ($detail -and -not $ok) { " | $detail" } else { '' })
}

# ---- synthetic files: every key name of the real layout, made-up values, two layouts (the game re-serialises) ----
$base = [ordered]@{
    'cpu' = [ordered]@{ name = 'Synthetic CPU'; processors = '16'; processorStride = '1'; processorBinding = 'true' }
    'resolution' = [ordered]@{ width = '2560'; height = '1440'; displayMode = 'fullscreen'; vsync = '0'; vsyncInterval = '1'; frameRateLimiterEnabled = 'false'; frameRateLimiterValue = '144' }
    'udp' = [ordered]@{ enabled = 'true'; broadcast = 'false'; ip = '127.0.0.1'; port = '20777'; sendRate = '60hz'; format = '2026'; yourTelemetry = 'restricted'; onlineNames = 'off' }
    'antialiasing' = [ordered]@{ taa = 'true'; cas = 'true'; dlss = '2'; fsr3 = '0'; xess = 'off' }
    'aa_quality' = [ordered]@{ value = '3' }; 'aa_sharpness' = [ordered]@{ value = '50' }
    'frame_gen' = [ordered]@{ mode = '1' }; 'multi_frame_gen' = [ordered]@{ value = '2' }
    'dynamicresolution_enabled' = [ordered]@{ value = 'true' }; 'dynamicresolution_target_fps' = [ordered]@{ value = '60' }
    'dynamicresolution_profile' = [ordered]@{ deltaDown = '0.1'; percentageDown = '5'; deltaUp = '0.05'; percentageUp = '5'; alpha = '0.9' }
    'dynamicresolution_min_scale' = [ordered]@{ value = '0.5' }
    'ssao' = [ordered]@{ enabled = 'true'; algorithm = 'hbao' }; 'ssrt' = [ordered]@{ enabled = 'true'; quality = '2' }
    'texture_streaming' = [ordered]@{ sizeInMiB = '4096'; texelDensityBias = '0'; concurrentTextureSwaps = '4' }
    'led_display' = [ordered]@{ fanatecNativeSupport = 'true'; sliProNativeSupport = 'false'; sliProForceBrightness = 'false'; wootingRGBEnabled = 'false' }
    'anisotropic_filter' = [ordered]@{ level = '16' }
    'lighting' = [ordered]@{ quality = 'high'; volumetricFog = 'true'; volumetricFogMapWidth = '160'; volumetricFogMapHeight = '90' }
    'postprocess' = [ordered]@{ motionBlur = 'true'; godRays = 'true'; depthOfField = 'true'; lensStreak = 'true'; lensFlare = 'true'; bloom = 'true'; motionBlurV2 = '1' }
    'shadows' = [ordered]@{ enabled = 'true'; skyShadowMapSize = '2048'; skyShadowCascadeCount = '4'; skyShadowLowLod = 'false'; worldShadowMapSize = '2048'; skyShadowMap32Bits = 'false'; nightShadowMapSize = '1024'; nightShadowCharacterCast = 'true'; nightShadowSourceCount = '4'; sampling = '2'; spotShadowMapSize = '1024'; spotShadowSampling = '1'; crowdInShadows = 'true' }
    'particles' = [ordered]@{ enabled = 'true'; distanceScale = '1.0'; rate = '1.0'; high = 'true' }
    'crowd' = [ordered]@{ distanceScale = '1.0'; billboardDistance = '200' }
    'vehicle_reflections' = [ordered]@{ envMapScale = '1.0'; envMapUpdateMode = '1'; envMapRenderMode = '1'; cubeMapEnabled = 'true'; cubeMapScale = '1.0'; cubeMapUpdateMode = '1' }
    'mirrors' = [ordered]@{ mirrorsUpdateMode = '1'; mirrorsRenderMode = '1'; treesInMirrors = 'true'; crowdInMirrors = 'true'; highDetailMirrors = 'true'; highDetailTyresAndCar = 'true'; particlesInMirrors = 'true' }
    'weather_effects' = [ordered]@{ rainSplashes = 'true'; rainSheets = 'true'; rainBeads = 'true'; rainHigh = 'true'; trackHeatHaze = 'true'; planarReflectionsEnabled = 'true'; planarReflectionsHQEnabled = 'true'; planarReflectionsRangeScale = '1.0'; planarReflectionsRTScale = '1.0'; planarReflectionsMipTailBlur = 'true'; proceduralCloudRTScale = '1.0'; proceduralCloudTiling = '1'; proceduralCloudQuality = '2' }
    'ground_cover' = [ordered]@{ enabled = 'true'; grassFlattening = 'true'; drawDistance = '1.0'; meshes = 'true' }
    'trees' = [ordered]@{ useLOD0 = 'true'; distanceScale = '1.0' }
    'hair' = [ordered]@{ enabled = 'true' }
    'skidmarks' = [ordered]@{ enabled = 'true'; parallax = 'true' }; 'skidmarks_blending' = [ordered]@{ enabled = 'true' }
    'audio' = [ordered]@{ audioUpdateRate = '60'; num_job_worker_threads = '2' }
    'async_compute' = [ordered]@{ enabled = 'true' }; 'cs_culling' = [ordered]@{ enabled = 'true' }; 'vendor_shader_pack' = [ordered]@{ enabled = 'true' }
    'replay_directory' = [ordered]@{ path = 'C:\Replays &amp; Clips' }
    'rt_pathtrace' = [ordered]@{ enabled = 'false' }; 'rt_ray_reconstruction' = [ordered]@{ enabled = 'true' }; 'rt_shadows' = [ordered]@{ enabled = 'true' }
    'rt_reflections' = [ordered]@{ enabled = 'true' }; 'rt_transparent_reflections' = [ordered]@{ enabled = 'true' }; 'rt_ao' = [ordered]@{ enabled = 'true' }
    'rt_ddgi' = [ordered]@{ enabled = 'true' }; 'rt_version' = [ordered]@{ version = '2' }
    'vrs' = [ordered]@{ enabled = 'false' }; 'reflex' = [ordered]@{ mode = '1' }; 'ser' = [ordered]@{ enabled = 'true' }; 'ca' = [ordered]@{ enabled = 'false' }
}
function Copy-Model($m) { $c = [ordered]@{}; foreach ($k in $m.Keys) { $c[$k] = [ordered]@{}; foreach ($a in $m[$k].Keys) { $c[$k][$a] = $m[$k][$a] } }; $c }
function A($attrs) { (@($attrs.Keys) | ForEach-Object { "$_=`"$($attrs[$_])`"" }) -join ' ' }
function Make-Xml($m, [string] $layout = 'a', [string[]] $drop = @()) {
    # layout a: tabs, CRLF, an XML declaration and a comment; layout b: two spaces, LF, attributes in another order
    $nl = if ($layout -eq 'a') { "`r`n" } else { "`n" }
    $t = if ($layout -eq 'a') { "`t" } else { '  ' }
    $o = [Collections.ArrayList]@()
    function El([string] $name, $attrs, [string] $ind) {
        if ($layout -eq 'b') { $r = [ordered]@{}; foreach ($k in @($attrs.Keys | Sort-Object)) { $r[$k] = $attrs[$k] }; $attrs = $r }
        "$ind<$name $(A $attrs) />"
    }
    if ($layout -eq 'a') { [void]$o.Add('<?xml version="1.0" encoding="UTF-8"?>'); [void]$o.Add('<!-- synthetic test file, made-up values -->') }
    [void]$o.Add('<hardware_settings_config applyOOTB="false">')
    [void]$o.Add((El 'cpu' $m['cpu'] $t))
    [void]$o.Add("$t<graphics_card deviceId=`"0x0000`">")
    $r = $m['resolution']
    [void]$o.Add("$t$t<resolution $(A $r)>")
    [void]$o.Add("$t$t$t<refreshRate numerator=`"144000`" denominator=`"1000`" />")
    [void]$o.Add("$t$t$t<windowPosition x=`"0`" y=`"0`" />")
    [void]$o.Add("$t$t$t<outputMonitor index=`"0`" />")
    [void]$o.Add("$t$t$t<aspectRatio auto=`"true`" width=`"16`" height=`"9`" />")
    [void]$o.Add("$t$t$t<hdr mode=`"0`" peakNits=`"1000`" />")
    [void]$o.Add("$t$t</resolution>")
    [void]$o.Add("$t</graphics_card>")
    [void]$o.Add("$t<motion>")
    [void]$o.Add("$t$t<dbox enabled=`"false`" />")
    [void]$o.Add((El 'udp' $m['udp'] "$t$t"))
    [void]$o.Add("$t</motion>")
    foreach ($k in $m.Keys) { if ($k -notin 'cpu', 'resolution', 'udp' -and $k -notin $drop) { [void]$o.Add((El $k $m[$k] $t)) } }
    [void]$o.Add('</hardware_settings_config>')
    ($o -join $nl) + $nl
}
$enc = New-Object Text.UTF8Encoding $false
function Put([string] $path, [string] $text, [switch] $Bom) {
    $b = $enc.GetBytes($text)
    if ($Bom) { $b = [byte[]](0xEF, 0xBB, 0xBF) + $b }
    [IO.File]::WriteAllBytes($path, [byte[]]$b)
}
function Sha([string] $f) { (Get-FileHash -LiteralPath $f -Algorithm SHA256).Hash }

# every hw_swap call of a case goes to that case's own temp folder; refuse anything outside $root
$script:caseNo = 0
function New-Case([string] $name) {
    $script:caseNo++
    $d = Join-Path $root ("c{0:D2}" -f $script:caseNo)
    New-Item -ItemType Directory -Force $d | Out-Null
    $c = @{ Dir = $d; Live = (Join-Path $d 'live\hardware_settings_config.xml'); Ref = (Join-Path $d 'snap\hardware_settings_config.ref.xml')
        State = (Join-Path $d 'state\hw_swap.json'); Backup = (Join-Path $d 'backups'); Log = (Join-Path $d 'state\hw_swap.log') }
    New-Item -ItemType Directory -Force (Split-Path $c.Live), (Split-Path $c.Ref) | Out-Null
    $c
}
function Swap($c, [string[]] $mode, [string] $game = 'verve-no-such-process-xyz') {
    foreach ($p in $c.Live, $c.Ref, $c.State, $c.Backup, $c.Log) {
        $full = [IO.Path]::GetFullPath($p)
        if (-not $full.StartsWith($root, [StringComparison]::OrdinalIgnoreCase) -or $full -match 'My Games\\F1 25') { throw "test path outside the temp root: $full" }
    }
    $a = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $swap) + $mode + @('-Live', $c.Live, '-Reference', $c.Ref, '-StateFile', $c.State,
        '-BackupDir', $c.Backup, '-LogFile', $c.Log, '-KeysCsv', $keys, '-GameProcess', $game)
    $o = @(& powershell @a 2>&1 | ForEach-Object { "$_" })
    @{ Code = $LASTEXITCODE; Out = $o }
}
function State($c) { if (Test-Path $c.State) { Get-Content $c.State -Raw | ConvertFrom-Json } else { $null } }

# ---- 1. the preset: only the declared keys differ, every other byte identical ----
. $swap   # functions only (no mode switch); its parameters become typed variables here ($In, $Back, ...): not reused below
$rules = @(Get-HwPresetRules $keys)
$declared = @{}; foreach ($r in $rules) { $declared["hw hardware_settings_config/$($r.key)"] = $true }
$srcText = Make-Xml $base 'a'
$srcFile = Join-Path $root 'src.xml'; Put $srcFile $srcText
$src = [IO.File]::ReadAllBytes($srcFile)
$p = Build-HwPreset $src $rules
$presetFile = Join-Path $root 'preset.xml'; [IO.File]::WriteAllBytes($presetFile, $p.Bytes)
$diff = @(Compare-HwValues $srcFile $presetFile)
$undeclared = @($diff | ForEach-Object { ($_ -split ': ', 2)[0] } | Where-Object { -not $declared.ContainsKey($_) })
Check "preset: $($p.Edits.Count) key(s) edited, every differing attribute is a declared key" ($p.Edits.Count -gt 20 -and $diff.Count -eq $p.Edits.Count -and -not $undeclared.Count) "$($diff.Count) differ, undeclared: $($undeclared -join '; ')"
Check 'preset: Test-HwPresetDiff finds nothing beyond the declared edits' (@(Test-HwPresetDiff $srcFile $presetFile $p.Edits).Count -eq 0)
# put the old values back into the preset's text at the edited spans: must give the source byte for byte
$pt = $enc.GetString($p.Bytes); $sb = New-Object Text.StringBuilder $pt
$shift = 0; $revert = @()
foreach ($e in $p.Edits | Sort-Object Start) { $revert += [pscustomobject]@{ At = $e.Start + $shift; Len = $e.New.Length; Old = $e.Old }; $shift += $e.New.Length - $e.Old.Length }
foreach ($b in $revert | Sort-Object At -Descending) { [void]$sb.Remove($b.At, $b.Len).Insert($b.At, $b.Old) }
Check 'preset: reverting only the edited attribute values gives the source byte for byte (every other byte identical)' ($sb.ToString() -ceq $srcText)
$pv = Get-HwValues $presetFile
$sv = Get-HwValues $srcFile
$motionSame = -not @($sv.Keys | Where-Object { $_ -match '/(motion|cpu|audio|led_display|replay_directory)' -and $sv[$_] -cne $pv[$_] }).Count
Check 'preset: motion/udp, cpu, audio, led_display and replay_directory untouched' $motionSame
$want = @{ 'graphics_card/resolution@displayMode' = 'windowed'; 'graphics_card/resolution@width' = '1280'; 'graphics_card/resolution@height' = '720'
    'graphics_card/resolution@frameRateLimiterEnabled' = 'true'; 'graphics_card/resolution@frameRateLimiterValue' = '60'
    'antialiasing@taa' = 'false'; 'antialiasing@dlss' = '0'; 'antialiasing@fsr3' = '0'; 'antialiasing@xess' = 'off'; 'rt_ddgi@enabled' = 'false'
    'lighting@quality' = 'low'; 'postprocess@motionBlurV2' = '0'; 'crowd@distanceScale' = '0'; 'ground_cover@enabled' = 'false' }
$wrong = @($want.Keys | Where-Object { $pv["hw hardware_settings_config/$_"] -cne $want[$_] } | ForEach-Object { "$_ = '$($pv["hw hardware_settings_config/$_"])'" })
Check 'preset: windowed 1280x720, 60 fps cap, RT/AA/upscalers off, forms kept (true/false, 0/1, words)' (-not $wrong.Count) ($wrong -join '; ')
Check 'preset: a flag already off stays as it is (rt_pathtrace, logged "already")' (@($p.Lines | Where-Object { $_ -match '^already: rt_pathtrace@enabled' }).Count -eq 1)
# a missing key = no edit, logged; a numeric displayMode = no edit, and so no width/height either (no mode switch)
$m2 = Copy-Model $base; $m2['resolution']['displayMode'] = '1'
$p2 = Build-HwPreset ($enc.GetBytes((Make-Xml $m2 'a' -drop 'hair'))) $rules
Check 'missing key: hair@enabled not edited, logged' (@($p2.Lines | Where-Object { $_ -match '^missing: hair@enabled' }).Count -eq 1 -and -not @($p2.Edits | Where-Object { $_.Key -match 'hair' }).Count)
Check 'displayMode in an unknown form: not edited, and width/height not edited either (logged)' (-not @($p2.Edits | Where-Object { $_.Key -match 'resolution@(displayMode|width|height)' }).Count -and @($p2.Lines | Where-Object { $_ -match '^not edited: graphics_card/resolution@width' }).Count -eq 1)
# a UTF-8 BOM and the other layout survive the same way
$bomFile = Join-Path $root 'bom.xml'; Put $bomFile (Make-Xml $base 'b') -Bom
$pb = Build-HwPreset ([IO.File]::ReadAllBytes($bomFile)) $rules
Check 'a BOM file keeps its BOM and its LF layout' ($pb.Bytes[0] -eq 0xEF -and $pb.Bytes[1] -eq 0xBB -and $pb.Bytes[2] -eq 0xBF -and -not ($enc.GetString($pb.Bytes) -match "`r"))

# ---- 2. in -> back: byte-identical ----
$c = New-Case 'in-back'
Put $c.Live (Make-Xml $base 'a'); Put $c.Ref (Make-Xml $base 'b')   # the reference: same values, the other layout
$orig = Sha $c.Live
$r = Swap $c @('-In', '-Tag', 'case2')
$st = State $c
Check 'in: exit 0, the preset is live (hash recorded), state active' ($r.Code -eq 0 -and (Sha $c.Live) -eq $st.presetSha -and $st.active -and $st.backupSha -eq $orig) "exit $($r.Code): $($r.Out -join ' / ')"
Check 'in: the dated backup is a byte copy of Tyler''s file, outside the live folder' ((Sha $st.backup) -eq $orig -and (Split-Path $st.backup) -eq $c.Backup)
$r = Swap $c @('-Back', '-Tag', 'case2')
Check 'back: exit 0, Tyler''s file byte-identical, state inactive' ($r.Code -eq 0 -and (Sha $c.Live) -eq $orig -and -not (State $c).active) "exit $($r.Code): $($r.Out -join ' / ')"

# ---- 3. idempotent back ----
$r = Swap $c @('-Back')
Check 'back again: exit 0, nothing to do, file unchanged' ($r.Code -eq 0 -and "$($r.Out)" -match 'no swap active' -and (Sha $c.Live) -eq $orig) "exit $($r.Code): $($r.Out -join ' / ')"

# ---- 4. refuse an unknown live state ----
$c = New-Case 'unknown'
$m3 = Copy-Model $base; $m3['udp']['port'] = '20778'; $m3['resolution']['frameRateLimiterValue'] = '90'; $m3['cpu']['name'] = 'Made-up CPU Model'
Put $c.Live (Make-Xml $m3 'a'); Put $c.Ref (Make-Xml $base 'a')
$before = [IO.File]::ReadAllBytes($c.Live); $t0 = (Get-Item $c.Live).LastWriteTimeUtc
$r = Swap $c @('-In')
Check 'in: live differs from the reference by value -> exit 2, nothing written, no swap active' ($r.Code -eq 2 -and (HwSameBytes ([IO.File]::ReadAllBytes($c.Live)) $before) -and (Get-Item $c.Live).LastWriteTimeUtc -eq $t0 -and -not (State $c)) "exit $($r.Code)"
Check 'in: the refusal names the changed keys' ("$($r.Out)" -match 'udp@port' -and "$($r.Out)" -match 'frameRateLimiterValue')
Check 'in: a device key (cpu@name) is named, its values shown as <private> (run logs are committed)' ("$($r.Out)" -match 'cpu@name' -and "$($r.Out)" -notmatch 'Made-up CPU|Synthetic CPU' -and (Get-Content $c.Log -Raw) -notmatch 'Made-up CPU|Synthetic CPU')
# the benign flip still counts as equal (sendRate "60hz" = "60")
$c = New-Case 'flip'
$m4 = Copy-Model $base; $m4['udp']['sendRate'] = '60'
Put $c.Live (Make-Xml $m4 'b'); Put $c.Ref (Make-Xml $base 'a')
$r = Swap $c @('-In')
Check 'in: sendRate 60 vs 60hz (the benign flip) is equal by value -> swap goes ahead' ($r.Code -eq 0) "exit $($r.Code): $($r.Out -join ' / ')"
Swap $c @('-Back') | Out-Null

# ---- 5. a third state at pre-flight: stop and report ----
$c = New-Case 'third'
Put $c.Live (Make-Xml $base 'a'); Put $c.Ref (Make-Xml $base 'a')
Swap $c @('-In', '-Tag', 'case5') | Out-Null
$st = State $c
$m5 = Copy-Model $base; $m5['udp']['port'] = '20999'   # neither the preset nor Tyler's: a value outside the preset changed
Put $c.Live (Make-Xml $m5 'b')
$third = [IO.File]::ReadAllBytes($c.Live)
$r = Swap $c @('-Recover')
Check 'recover: third state -> exit 2, nothing written, swap still active, reported' ($r.Code -eq 2 -and (HwSameBytes ([IO.File]::ReadAllBytes($c.Live)) $third) -and (State $c).active -and "$($r.Out)" -match 'STOP') "exit $($r.Code): $($r.Out -join ' / ')"
$r = Swap $c @('-In')
Check 'in: an earlier swap in a third state blocks a new swap-in (exit 2, nothing written)' ($r.Code -eq 2 -and (HwSameBytes ([IO.File]::ReadAllBytes($c.Live)) $third)) "exit $($r.Code)"
$r = Swap $c @('-Back', '-Tag', 'another-run')
Check "back -Tag of another run: the active swap isn't touched (exit 0, nothing written)" ($r.Code -eq 0 -and (HwSameBytes ([IO.File]::ReadAllBytes($c.Live)) $third) -and (State $c).active) "exit $($r.Code)"

# ---- 6. recovery after a simulated crash (the preset left live) ----
foreach ($how in 'by hash', 'by value (the game re-serialised it)') {
    $c = New-Case 'crash'
    Put $c.Live (Make-Xml $base 'a'); Put $c.Ref (Make-Xml $base 'b')
    $orig = Sha $c.Live
    Swap $c @('-In') | Out-Null   # ... and the runner dies here: no swap-back
    $st = State $c
    if ($how -match 'value') {
        # the game rewrote the preset in its other layout: same values, other bytes
        $pm = Copy-Model $base
        foreach ($e in (Get-HwValues $st.preset).GetEnumerator()) {
            if ($e.Key -match '^hw hardware_settings_config/(?:graphics_card/)?(?:motion/)?([^/@\[]+)@(\w+)$' -and $e.Value -notmatch '[&<>"]' -and $pm.Contains($Matches[1]) -and $pm[$Matches[1]].Contains($Matches[2])) { $pm[$Matches[1]][$Matches[2]] = $e.Value }
        }
        $pm['udp']['sendRate'] = '60hz'
        Put $c.Live (Make-Xml $pm 'b')
    }
    $kind = if ((Sha $c.Live) -eq $st.presetSha) { 'hash' } else { 'value' }
    $r = Swap $c @('-Recover')
    Check "recover ($how): the preset live -> Tyler's file restored byte-identical, logged, swap closed" ($r.Code -eq 0 -and (Sha $c.Live) -eq $orig -and -not (State $c).active -and "$($r.Out)" -match 'restored' -and $how -match $kind) "exit $($r.Code), live by $kind`: $($r.Out -join ' / ')"
}
# a crash with the preset left live, then the next launch's swap-in: recovers first, then swaps in again
$c = New-Case 'crash-in'
Put $c.Live (Make-Xml $base 'a'); Put $c.Ref (Make-Xml $base 'a')
$orig = Sha $c.Live
Swap $c @('-In', '-Tag', 'run-1') | Out-Null
$r = Swap $c @('-In', '-Tag', 'run-2')
Check 'in after a crash: the old swap is recovered first, then the new one goes in' ($r.Code -eq 0 -and "$($r.Out)" -match 'recovery' -and (State $c).tag -eq 'run-2' -and (State $c).backupSha -eq $orig) "exit $($r.Code): $($r.Out -join ' / ')"
Swap $c @('-Back') | Out-Null
Check '... and its swap-back gives Tyler''s file byte-identical' ((Sha $c.Live) -eq $orig)

# ---- 7. the pause path: restored and verified before SAFE TO PLAY ----
$c = New-Case 'pause'
Put $c.Live (Make-Xml $base 'a'); Put $c.Ref (Make-Xml $base 'a')
$orig = Sha $c.Live
Swap $c @('-In') | Out-Null
$r = Swap $c @('-PauseGate')
Check 'pause gate: an active swap is restored byte-identical, exit 0, no output (the verdict stays one line)' ($r.Code -eq 0 -and -not ($r.Out | Where-Object { $_ }) -and (Sha $c.Live) -eq $orig -and -not (State $c).active) "exit $($r.Code): $($r.Out -join ' / ')"
# safe_to_play.ps1: the gate runs after the process checks, before the saves checks and before the SAFE TO PLAY verdict
$stp = Join-Path $tools 'safe_to_play.ps1'
$txt = [IO.File]::ReadAllLines($stp)
$gateAt = (0..($txt.Count - 1) | Where-Object { $txt[$_] -match 'hw_swap\.ps1.*-PauseGate' } | Select-Object -First 1)
$safeAt = (0..($txt.Count - 1) | Where-Object { $txt[$_] -match "Verdict 'SAFE TO PLAY'" } | Select-Object -First 1)
$dscAt = (0..($txt.Count - 1) | Where-Object { $txt[$_] -match '^\$dc = & powershell.*deferred_saves_check\.ps1' } | Select-Object -First 1)
$upAt = (0..($txt.Count - 1) | Where-Object { $txt[$_] -match '\$up\.Count' } | Select-Object -First 1)
$failAt = (0..($txt.Count - 1) | Where-Object { $txt[$_] -match 'Verdict \$hwLine 1' } | Select-Object -First 1)
Check 'safe_to_play: the gate sits after the process checks and before the saves checks and SAFE TO PLAY; a failure is a WAIT verdict' ($null -ne $gateAt -and $upAt -lt $gateAt -and $gateAt -lt $dscAt -and $gateAt -lt $safeAt -and $gateAt -lt $failAt -and $failAt -lt $dscAt) "gate $gateAt, up $upAt, deferred $dscAt, safe $safeAt, fail $failAt"

# ---- 8. a restore failure: WAIT plus URGENT ----
$c = New-Case 'urgent'
Put $c.Live (Make-Xml $base 'a'); Put $c.Ref (Make-Xml $base 'a')
Swap $c @('-In') | Out-Null
$st = State $c
$bk = [IO.File]::ReadAllBytes($st.backup); $bk[$bk.Length - 3] = [byte](($bk[$bk.Length - 3] + 1) % 256); [IO.File]::WriteAllBytes($st.backup, $bk)   # the backup damaged
$r = Swap $c @('-PauseGate')
$line = @($r.Out | Where-Object { $_ })
Check 'pause gate, backup damaged: exit 1, one line "WAIT: URGENT: message the supervisor now: <reason>", nothing overwritten' ($r.Code -eq 1 -and $line.Count -eq 1 -and $line[0] -match '^WAIT: URGENT: message the supervisor now: \S' -and (Sha $c.Live) -eq $st.presetSha -and (State $c).active) "exit $($r.Code): $($r.Out -join ' / ')"
$r = Swap $c @('-Back')
Check 'back, backup damaged: exit 7 (URGENT)' ($r.Code -eq 7 -and "$($r.Out)" -match 'URGENT') "exit $($r.Code)"
# the game running: swap-in refused, swap-back deferred (the game rewrites the file on quit), pause gate WAIT
$c = New-Case 'game'
Put $c.Live (Make-Xml $base 'a'); Put $c.Ref (Make-Xml $base 'a')
$me = (Get-Process -Id $PID).ProcessName
$r = Swap $c @('-In') $me
Check 'in while the game runs: exit 3, nothing written' ($r.Code -eq 3 -and -not (State $c)) "exit $($r.Code)"
Swap $c @('-In') | Out-Null
$r = Swap $c @('-Back') $me
Check 'back while the game runs: exit 3 (deferred), the swap stays active' ($r.Code -eq 3 -and (State $c).active) "exit $($r.Code)"
$r = Swap $c @('-PauseGate') $me
Check 'pause gate while the game runs: WAIT plus URGENT' ($r.Code -eq 1 -and "$($r.Out)" -match '^WAIT: URGENT: message the supervisor now: ') "exit $($r.Code): $($r.Out -join ' / ')"
Swap $c @('-Back') | Out-Null

# ---- 8b. the game rewrites the file in its OWN layout as it quits, after a swap-back was tried while it ran ----
function Game-Layout([string] $from) {
    # the same values, written the way another serialiser would: attributes in reverse order, four-space indents, LF,
    # no XML declaration, no comment, no space before "/>"
    $x = New-Object System.Xml.XmlDocument; $x.Load($from)
    foreach ($el in @($x.SelectNodes('//*'))) {
        $as = @($el.Attributes | ForEach-Object { $_ }); [array]::Reverse($as)
        $el.Attributes.RemoveAll(); foreach ($a in $as) { [void]$el.Attributes.Append($a) }
    }
    foreach ($cm in @($x.SelectNodes('//comment()'))) { [void]$cm.ParentNode.RemoveChild($cm) }
    $s = New-Object System.Xml.XmlWriterSettings
    $s.Indent = $true; $s.IndentChars = '    '; $s.NewLineChars = "`n"; $s.OmitXmlDeclaration = $true; $s.Encoding = $enc
    $ms = New-Object IO.MemoryStream; $w = [System.Xml.XmlWriter]::Create($ms, $s)
    foreach ($n in @($x.ChildNodes)) { if ($n.NodeType -eq 'Element') { $n.WriteTo($w) } }
    $w.Flush(); $w.Dispose()
    $enc.GetString($ms.ToArray()) -replace ' />', '/>'
}
$c = New-Case 'game-exit-write'
Put $c.Live (Make-Xml $base 'a'); Put $c.Ref (Make-Xml $base 'b')
$orig = Sha $c.Live
Swap $c @('-In', '-Tag', 'run-g') | Out-Null
$st = State $c
# the "game" is running (this test's own process name): the swap-back must wait and write nothing
$r = Swap $c @('-Back', '-Tag', 'run-g') $me
Check 'game exit write: a swap-back while the game runs waits (exit 3), writes nothing, the swap stays active' ($r.Code -eq 3 -and (Sha $c.Live) -eq $st.presetSha -and (State $c).active) "exit $($r.Code): $($r.Out -join ' / ')"
# ... the game quits: its exit write is the preset's values in its own layout
$gameText = Game-Layout $c.Live
Put $c.Live $gameText
$gameBytes = [IO.File]::ReadAllBytes($c.Live)
$layoutDiffers = (Sha $c.Live) -ne $st.presetSha -and $gameText -notmatch "`r" -and $gameText -notmatch '<\?xml' -and $gameText -match '\n    <'
$reordered = [regex]::Match($gameText, '<resolution [^>]*').Value -match '^<resolution frameRateLimiterValue='
Check 'game exit write: other bytes (reordered attributes, 4-space indents, LF, no declaration), the preset''s values' ($layoutDiffers -and $reordered -and -not @(Compare-HwValues $st.preset $c.Live).Count)
# the game has exited: the later swap-back restores Tyler's file over the game's write
$r = Swap $c @('-Back', '-Tag', 'run-g')
Check 'game exit write: the swap-back after the game exited gives Tyler''s reference by value AND Tyler''s file by SHA-256' ($r.Code -eq 0 -and -not @(Compare-HwValues $c.Ref $c.Live).Count -and (Sha $c.Live) -eq $orig -and (Sha $c.Live) -eq $st.backupSha -and -not (State $c).active -and "$($r.Out)" -match 'live was preset-values') "exit $($r.Code): $($r.Out -join ' / ')"
# and nothing comes after it: the game's exit write came BEFORE the restore, so the restore is the last write
Check 'game exit write: the game''s write was not left behind (the restore came after it)' (-not (HwSameBytes ([IO.File]::ReadAllBytes($c.Live)) $gameBytes))


# ---- 8c. the swap and the display fallback (#168, the real tools/hw_display_restore.ps1) on one run, in the shell's order ----
$dr = Join-Path $tools 'hw_display_restore.ps1'
$drLabel = 'hw_display_restore.ps1'
Check 'hw_display_restore.ps1 (#168) is in this tree: section 8c runs against the real tool' (Test-Path $dr)
function Display-Step($c, [string] $runDir) {
    # the guard's display-fallback step as sandbox_shell runs it: only for a hardware diff (Tyler's values before the
    # launch vs after) of resolution width/height alone
    $diff = @(Compare-HwValues $c.Ref $c.Live)
    $resOnly = $diff.Count -gt 0 -and -not @($diff | Where-Object { $_ -notmatch '^hw hardware_settings_config/graphics_card/resolution@(width|height): ' }).Count
    if (-not $resOnly) { return @{ Ran = $false; Code = 0; Out = @("not entered ($($diff.Count) change(s))") } }
    $o = @(& powershell -NoProfile -ExecutionPolicy Bypass -File $dr -Out $runDir -File $c.Live -Reference $c.Ref -SnapDir (Join-Path $c.Dir 'evidence') -NoProcessCheck 2>&1 | ForEach-Object { "$_" })
    @{ Ran = $true; Code = $LASTEXITCODE; Out = $o }
}
# (1) the game quits with its 1024x768 fallback in its own layout; the swap-back alone restores, the fallback finds nothing
$c = New-Case 'swap-and-fallback'
Put $c.Live (Make-Xml $base 'a'); Put $c.Ref (Make-Xml $base 'b')
$orig = Sha $c.Live
$run = Join-Path $c.Dir 'run'; New-Item -ItemType Directory -Force $run | Out-Null
Swap $c @('-In', '-Tag', $run) | Out-Null
$st = State $c
$g = Game-Layout $c.Live
$g = [regex]::Replace($g, '(<resolution\b[^>]*\bwidth=")[^"]*', '${1}1024'); $g = [regex]::Replace($g, '(<resolution\b[^>]*\bheight=")[^"]*', '${1}768')
Put $c.Live $g
$fb = @(Compare-HwValues $st.preset $c.Live)
Check 'swap + fallback: the game''s exit write is the preset with a 1024x768 fallback, in its own layout' ($fb.Count -eq 2 -and ($fb -join ' ') -match "resolution@width: '1280' -> '1024'" -and (Sha $c.Live) -ne $st.presetSha)
$r = Swap $c @('-Back', '-Tag', $run)
$d1 = Display-Step $c $run
$a1 = Swap $c @('-AfterGuard', '-Tag', $run)
Check "swap + fallback: the swap-back alone gives Tyler's reference by value AND his SHA-256; the display step ($drLabel) finds nothing to do" ($r.Code -eq 0 -and -not @(Compare-HwValues $c.Ref $c.Live).Count -and (Sha $c.Live) -eq $orig -and -not $d1.Ran -and -not (Test-Path (Join-Path $run 'display_fallback.txt'))) "back $($r.Code); display: $($d1.Out -join ' / ')"
$o = @(& powershell -NoProfile -ExecutionPolicy Bypass -File $dr -File $c.Live -Reference $c.Ref -SnapDir (Join-Path $c.Dir 'evidence') -NoProcessCheck 2>&1 | ForEach-Object { "$_" })
Check 'swap + fallback: hw_display_restore.ps1 itself, run anyway, says nothing to do and writes nothing' ($LASTEXITCODE -eq 0 -and "$o" -match 'nothing to do' -and (Sha $c.Live) -eq $orig) "$o"
Check 'swap + fallback: no "display fallback acted after a swap-back" line when only the swap-back acted' ($a1.Code -eq 0 -and -not ($a1.Out | Where-Object { $_ -match 'display fallback acted after a swap-back' }))
# (2) both act: something writes 1024x768 again after the swap-back (simulated), so the fallback edits too
$c = New-Case 'both-act'
Put $c.Live (Make-Xml $base 'a'); Put $c.Ref (Make-Xml $base 'a')
$run = Join-Path $c.Dir 'run'; New-Item -ItemType Directory -Force $run | Out-Null
Swap $c @('-In', '-Tag', $run) | Out-Null
Swap $c @('-Back', '-Tag', $run) | Out-Null
$t2 = [IO.File]::ReadAllText($c.Live)
$t2 = [regex]::Replace($t2, '(<resolution\b[^>]*\bwidth=")[^"]*', '${1}1024'); $t2 = [regex]::Replace($t2, '(<resolution\b[^>]*\bheight=")[^"]*', '${1}768')
[IO.File]::WriteAllText($c.Live, $t2, $enc)
$d2 = Display-Step $c $run
$a2 = Swap $c @('-AfterGuard', '-Tag', $run)
Check "both act: the display step ($drLabel) restores width/height after the swap-back" ($d2.Ran -and $d2.Code -eq 0 -and -not @(Compare-HwValues $c.Ref $c.Live).Count) "$($d2.Out -join ' / ')"
Check 'both act: hw_swap -AfterGuard logs its own line "display fallback acted after a swap-back" (output and hw_swap.log)' (@($a2.Out | Where-Object { $_ -match '^display fallback acted after a swap-back: ' }).Count -eq 1 -and (Get-Content $c.Log -Raw) -match 'display fallback acted after a swap-back') "$($a2.Out -join ' / ')"
$a3 = Swap $c @('-AfterGuard', '-Tag', 'another-run')
Check "both act: -AfterGuard for another run's tag stays silent" (-not ($a3.Out | Where-Object { $_ }))
# the shell's order: swap-back (finally) -> after-snapshot -> display fallback (when #168 is in) -> -AfterGuard
$sh = Get-Content (Join-Path $tools 'sandbox_shell.ps1') -Raw
$iBack = $sh.IndexOf('$hwSwap -Back'); $iAfter = $sh.IndexOf('$after = Snapshot'); $iGuard = $sh.IndexOf('$hwSwap -AfterGuard'); $iRes = $sh.IndexOf('hw_display_restore.ps1')
Check 'sandbox_shell: swap-back, then the after-snapshot, then the display fallback, then -AfterGuard' ($iBack -gt 0 -and $iBack -lt $iAfter -and $iAfter -lt $iGuard -and $iAfter -lt $iRes -and $iRes -lt $iGuard) "back $iBack, after $iAfter, fallback $iRes, afterguard $iGuard"

# ---- 9. an interrupted run: an exception between in and back still restores (the runners' try/finally) ----
$c = New-Case 'interrupted'
Put $c.Live (Make-Xml $base 'a'); Put $c.Ref (Make-Xml $base 'a')
$orig = Sha $c.Live
$stub = Join-Path $c.Dir 'stub_runner.ps1'
$common = "-Live '$($c.Live)' -Reference '$($c.Ref)' -StateFile '$($c.State)' -BackupDir '$($c.Backup)' -LogFile '$($c.Log)' -KeysCsv '$keys' -GameProcess 'verve-no-such-process-xyz'"
Set-Content $stub -Encoding utf8 -Value @(
    '$ErrorActionPreference = ''Stop''',
    "& powershell -NoProfile -ExecutionPolicy Bypass -File '$swap' -In -Tag stub $common | Out-Null",
    "if (`$LASTEXITCODE -ne 0) { exit 17 }",
    'try {',
    "    if ((Get-FileHash '$($c.Live)' -Algorithm SHA256).Hash -eq '$orig') { exit 21 }   # the preset must be live here",
    '    throw ''simulated runner error mid-launch''',
    '} finally {',
    "    & powershell -NoProfile -ExecutionPolicy Bypass -File '$swap' -Back -Tag stub $common | Out-Null",
    '}')
& { $ErrorActionPreference = 'Continue'; & powershell -NoProfile -ExecutionPolicy Bypass -File $stub *> $null }   # its throw goes to stderr
$stubCode = $LASTEXITCODE
Check 'interrupted run: the throw ends the stub (exit 1) and its finally restored Tyler''s file byte-identical' ($stubCode -eq 1 -and (Sha $c.Live) -eq $orig -and -not (State $c).active) "stub exit $stubCode"
# the real runners and the shell: the swap-back is in a finally around the launch, and only with -LowGraphics
function Get-Ast([string] $f) { $t = $null; $e = $null; $a = [Management.Automation.Language.Parser]::ParseFile($f, [ref]$t, [ref]$e); if ($e.Count) { throw "$f does not parse: $($e[0].Message)" }; $a }
foreach ($name in 'v1_run.ps1', 'b0016_run.ps1', 'sandbox_shell.ps1') {
    $ast = Get-Ast (Join-Path $tools $name)
    $inner = if ($name -eq 'sandbox_shell.ps1') { 'for \(\$attempt = 1' } else { 'sandbox_shell\.ps1|powershell @shellArgs' }
    $tries = @($ast.FindAll({ param($n) $n -is [Management.Automation.Language.TryStatementAst] }, $true) |
        Where-Object { $_.Finally -and $_.Finally.Extent.Text -match 'hw_swap\.ps1''?\)? -Back|\$hwSwap -Back' -and $_.Body.Extent.Text -match $inner })
    Check "${name}: the launch sits in a try whose finally runs hw_swap -Back" ($tries.Count -eq 1)
    # every hw_swap call sits inside an `if ($LowGraphics)` (off by default: a [switch] with no default value)
    $calls = @($ast.FindAll({ param($n) $n -is [Management.Automation.Language.CommandAst] -and $n.Extent.Text -match 'hw_swap\.ps1|\$hwSwap' -and $n.Extent.Text -match '-(In|Back|AfterGuard)\b' }, $true))
    $unguarded = @($calls | Where-Object {
        $q = $_.Parent; $g = $false
        while ($q) { if ($q -is [Management.Automation.Language.IfStatementAst] -and $q.Clauses[0].Item1.Extent.Text -match '^\$LowGraphics$') { $g = $true; break }; $q = $q.Parent }
        -not $g })
    $sw = @($ast.ParamBlock.Parameters | Where-Object { $_.Name.VariablePath.UserPath -eq 'LowGraphics' })
    Check "${name}: -LowGraphics is a switch with no default, and all $($calls.Count) hw_swap call(s) are inside if (`$LowGraphics)" ($calls.Count -ge 1 -and -not $unguarded.Count -and $sw.Count -eq 1 -and $sw[0].StaticType -eq [switch] -and -not $sw[0].DefaultValue) "unguarded: $($unguarded.Count)"
}
foreach ($name in 'v1_run.ps1', 'b0016_run.ps1') {
    $l18 = @(Get-Content (Join-Path $tools $name) | Where-Object { $_ -match '\bexit 18\b' -and $_ -notmatch '^\s*#' -and $_ -match '\{' })
    Check "${name}: every exit 18 prints a line starting 'URGENT: message the supervisor now:' with the reason" ($l18.Count -ge 1 -and -not @($l18 | Where-Object { $_ -notmatch "'URGENT: message the supervisor now: \S[^']+''s hardware settings were NOT restored" }).Count) "$($l18.Count) line(s)"
}
$v1 = Get-Content (Join-Path $tools 'v1_run.ps1') -Raw
Check 'v1_run: -LowGraphics is passed to the shell only when set' ($v1 -match "if \(\`$LowGraphics\) \{ \`$shellArgs \+= '-LowGraphics' \}")

# ---- 10. switch off / no swap active: a no-op ----
$c = New-Case 'off'
Put $c.Live (Make-Xml $base 'a'); Put $c.Ref (Make-Xml $base 'a')
$orig = Sha $c.Live; $t0 = (Get-Item $c.Live).LastWriteTimeUtc
$outs = @()
foreach ($m in @('-Back'), @('-Recover'), @('-PauseGate')) { $r = Swap $c $m; $outs += [pscustomobject]@{ Mode = $m[0]; Code = $r.Code; Out = @($r.Out | Where-Object { $_ }) } }
Check 'no swap active: -Back, -Recover and -PauseGate exit 0 and write nothing (live file, state, backups)' (-not @($outs | Where-Object { $_.Code -ne 0 }).Count -and (Sha $c.Live) -eq $orig -and (Get-Item $c.Live).LastWriteTimeUtc -eq $t0 -and -not (Test-Path $c.State) -and -not (Test-Path $c.Backup)) (($outs | ForEach-Object { "$($_.Mode) $($_.Code)" }) -join ', ')
Check 'no swap active: -Recover and -PauseGate print nothing (pre-flight and the SAFE TO PLAY line unchanged)' (-not @($outs | Where-Object { $_.Mode -ne '-Back' -and $_.Out.Count }).Count)
$pf = Get-Content (Join-Path $tools 'preflight.ps1') -Raw
Check 'preflight: the recovery runs first (before swofty doctor) and a failure is PREFLIGHT FAIL' ($pf.IndexOf('hw_swap.ps1') -gt 0 -and $pf.IndexOf('hw_swap.ps1') -lt $pf.IndexOf('& $Swofty doctor') -and $pf -match 'PREFLIGHT FAIL: hardware settings recovery')

# the declared key list: what the preset may change is committed, nothing else (no values of Tyler's)
Check 'hw_test_preset_keys.csv: every row is a graphics/display key, never motion, cpu, audio, controls or devices' (-not @($rules | Where-Object { $_.key -match '^(motion|cpu|audio|led_display|replay_directory)|@(deviceId|name|index)$' }).Count)

Remove-Item $root -Recurse -Force -ErrorAction SilentlyContinue
if ($failed) { "test_hw_swap: $failed FAILED"; exit 1 }
'test_hw_swap: ok'
