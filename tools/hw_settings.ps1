<#
hardware_settings_config.xml as values (supervisor, 2026-11-16: treated like a save; Tyler's play shares it). Dot-source:
    . tools/hw_settings.ps1
    Get-HwValues <file>                    # ordered: "hw <element path>@<attribute>" -> value
    Compare-HwValues <reference> <current> # one line per changed key: "<key>: '<old>' -> '<new>'"; none when equal
The game rewrites the file with a different layout on launch and quit (118 differing lines, identical values), so
only values count, never lines or timestamps.
#>
$HwFile = Join-Path $env:USERPROFILE 'Documents\My Games\F1 25\hardwaresettings\hardware_settings_config.xml'
$HwReference = Join-Path $env:LOCALAPPDATA 'verve-f1-25\settings-snapshots\hardware_settings_config.ref-20261116.xml'

function Get-HwValues([string] $file) {
    $h = [ordered]@{}
    $xml = New-Object System.Xml.XmlDocument
    $xml.Load($file)
    $seen = @{}
    foreach ($el in $xml.SelectNodes('//*')) {
        $path = @(); $n = $el
        # LocalName, not Name: PowerShell's XML adapter returns an element's "name" attribute for .Name
        while ($n -and $n.NodeType -eq 'Element') { $path = , $n.LocalName + $path; $n = $n.ParentNode }
        $p = $path -join '/'
        $seen[$p] = 1 + [int]$seen[$p]
        if ($seen[$p] -gt 1) { $p = "$p[$($seen[$p])]" }   # repeated siblings keep their order
        foreach ($at in $el.Attributes) { $h["hw $p@$($at.LocalName)"] = $at.Value }
    }
    $h
}

function Compare-HwValues([string] $reference, [string] $current) {
    $a = Get-HwValues $reference
    $b = Get-HwValues $current
    foreach ($k in (@($a.Keys) + @($b.Keys) | Sort-Object -Unique)) {
        if ($a[$k] -ne $b[$k]) { "${k}: '$($a[$k])' -> '$($b[$k])'" }
    }
}
