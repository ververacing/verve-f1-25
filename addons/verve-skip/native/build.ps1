<#
Build verve_skip.dll with Zig, matching Swofty's addon template (templates/addon/native/build.sh). No MSVC, no UAC.

Usage:
    powershell -File addons/verve-skip/native/build.ps1

Zig: the template doesn't pin a version, so this uses 0.17.1, the portable zip from ziglang.org, unpacked in
%LOCALAPPDATA%\verve-f1-25\tools\. The SDK headers are fetched once from Swofty's template at the commit below into
build\sdk\ (not committed), so a Swofty update can't change a build by surprise. Bump $SdkCommit on purpose.
#>
param(
    [string] $Zig = "$env:LOCALAPPDATA\verve-f1-25\tools\zig-x86_64-windows-0.17.1\zig.exe",
    [string] $SdkCommit = 'ebcea51cbd8402dec5033c498a813db938d0baef'
)
$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
if (-not (Test-Path $Zig)) { throw "Zig not found: $Zig (see the note at the top of this script)" }

$build = Join-Path $here 'build'
$sdk = Join-Path $build 'sdk'
$stamp = Join-Path $sdk '.commit'
if (-not (Test-Path $stamp) -or (Get-Content $stamp -Raw).Trim() -ne $SdkCommit) {
    $repo = 'Swofty-Developments/SwoftyLauncher'
    $prefix = 'templates/addon/native/include/'
    $tree = gh api "repos/$repo/git/trees/${SdkCommit}?recursive=1" | ConvertFrom-Json
    $files = @($tree.tree | Where-Object { $_.type -eq 'blob' -and $_.path.StartsWith($prefix) })
    if (-not $files.Count) { throw "no SDK headers at $prefix in $SdkCommit" }
    if (Test-Path $sdk) { Remove-Item -Recurse -Force $sdk -Confirm:$false }
    foreach ($f in $files) {
        $dest = Join-Path $sdk $f.path.Substring($prefix.Length)
        New-Item -ItemType Directory -Force (Split-Path $dest) | Out-Null
        $b64 = (gh api "repos/$repo/git/blobs/$($f.sha)" | ConvertFrom-Json).content
        [IO.File]::WriteAllBytes($dest, [Convert]::FromBase64String($b64))
    }
    Set-Content $stamp $SdkCommit -Encoding ascii
    "fetched $($files.Count) SDK header(s) at $($SdkCommit.Substring(0, 7))"
}

$env:ZIG_GLOBAL_CACHE_DIR = Join-Path $build 'zig-cache'
$env:ZIG_LOCAL_CACHE_DIR = $env:ZIG_GLOBAL_CACHE_DIR
$dll = Join-Path $here 'verve_skip.dll'
& $Zig c++ -target x86_64-windows-gnu -std=c++23 -O2 -Wall -Wextra "-I$sdk" -shared -s -o $dll (Join-Path $here 'src\verve_skip.cpp')
if ($LASTEXITCODE -ne 0) { "build failed: exit $LASTEXITCODE"; exit $LASTEXITCODE }
Remove-Item (Join-Path $here 'verve_skip.lib') -ErrorAction SilentlyContinue
"built $dll ($((Get-Item $dll).Length) bytes)"
