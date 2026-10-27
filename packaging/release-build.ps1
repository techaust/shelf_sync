# Every release step after the UI build, in one script, so release.yml and a local run do exactly the same thing
# (SYS-01, 06 section 6). release.yml calls it on a throwaway runner; the lead runs it on this PC before any push that
# touches packaging, with -Suffix (throwaway installer names and Credential Manager service) and without -RealSecrets.
#
#   powershell -File packaging\release-build.ps1 -Python <python 3.14.8> -Makensis <makensis.exe> -Work <new empty folder>
#       [-Tag v<X.Y.Z>] [-SourceCommit <40 hex>] [-Suffix -rehearsal] [-RealSecrets]
#
# Steps: build.py (folder, zip, files.txt) -> smoke.py -> makensis (the Setup, plus two fast test Setups 0.0.1 and
# 99.0.0 that are never released) -> test-installer.ps1 (install, upgrade, prune, refusals, sentinels, uninstall with
# Remove my data) -> manifest.json (unsigned, written by the built folder's own Python). Run from anywhere: it works
# from the repo root, and every path below is absolute or relative to it, so the result can't depend on the caller's
# folder. It runs under Windows PowerShell 5.1 (this PC) and PowerShell 7 (GitHub's `shell: pwsh`).
param(
    [Parameter(Mandatory = $true)][string]$Python,
    [Parameter(Mandatory = $true)][string]$Makensis,
    [Parameter(Mandatory = $true)][string]$Work,
    [string]$Tag = "",
    [string]$SourceCommit = "",
    [string]$Suffix = "",
    [switch]$RealSecrets
)
$ErrorActionPreference = "Stop"

function Step([string]$what) { Write-Host ""; Write-Host "== $what" }
function Run([string]$what, [scriptblock]$block) {
    & $block
    if ($LASTEXITCODE -ne 0) { throw "$what failed (exit $LASTEXITCODE)" }
}

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repo

if ((Test-Path $Work) -and (Get-ChildItem $Work -Force | Select-Object -First 1)) { throw "$Work isn't empty; use a new folder" }
New-Item -ItemType Directory -Force $Work | Out-Null
$Work = (Resolve-Path $Work).Path
# The installer test nests installs under $Work, and the deepest built file is about 120 characters long: a long $Work
# goes past Windows' 260-character path limit and Windows PowerShell can't clean up (the first local run, from the
# scratchpad, did). GitHub's $env:RUNNER_TEMP is short.
if ($Work.Length -gt 60) { throw "-Work is $($Work.Length) characters; use a folder of at most 60, e.g. $env:TEMP\ssrb" }

Step "Version"
$version = (& $Python -I -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])").Trim()
if ($LASTEXITCODE -ne 0) { throw "couldn't read the version" }
if ($version -notmatch '^\d+\.\d+\.\d+$') { throw "pyproject.toml's version '$version' isn't X.Y.Z" }
if ($Tag -and $Tag -ne "v$version") { throw "The tag $Tag doesn't match the version v$version" }
if (-not $SourceCommit) { $SourceCommit = (git rev-parse HEAD).Trim() }
if ($SourceCommit -notmatch '^[0-9a-f]{40}$') { throw "source commit '$SourceCommit' isn't 40 hex" }
Write-Host "ShelfSync $version from $SourceCommit"
$built = Join-Path $repo "build\ShelfSync-$version"
$setup = Join-Path $repo "build\ShelfSync-Setup-$version.exe"
$zip = Join-Path $repo "build\shelfsync-$version-win64.zip"
$nsi = "packaging\ShelfSync.nsi"

Step "Build the folder, the zip and files.txt"
if ($Tag) { Run "build.py" { & $Python -I packaging/build.py --tag $Tag } } else { Run "build.py" { & $Python -I packaging/build.py } }

Step "Smoke-test the built folder"
if ($RealSecrets) {
    Run "smoke.py" { & $Python -I packaging/smoke.py $built --version $version --real-secrets }
} else {
    Run "smoke.py" { & $Python -I packaging/smoke.py $built --version $version }
}

Step "Compile the installer and the two test Setups"
Run "makensis" { & $Makensis "/DVERSION=$version" "/DSUFFIX=$Suffix" "/DBUILD_DIR=$built" "/DOUTFILE=$setup" $nsi }
foreach ($extra in "0.0.1", "99.0.0") {
    Run "makensis ($extra test Setup)" {
        & $Makensis /DFAST "/DVERSION=$extra" "/DSUFFIX=$Suffix" "/DBUILD_DIR=$built" "/DOUTFILE=$Work\Setup-$extra.exe" $nsi
    }
}

Step "Install, check, plant the sentinels, upgrade, uninstall"
$tester = Join-Path $repo "packaging\test-installer.ps1"
Run "the installer checks" {
    & $tester -Setup $setup -Version $version -Root (Join-Path $Work "installtest") -Suffix $Suffix `
        -OlderSetup "$Work\Setup-0.0.1.exe" -NewerSetup "$Work\Setup-99.0.0.exe" -NewerVersion 99.0.0 -RemoveData
}

Step "Write the unsigned manifest"
# -I isolated, -B so nothing is written into the folder the Setup and zip were made from. Nothing is signed here.
$builtAt = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
Run "the manifest" {
    & "$built\python.exe" -I -B -m shelfsync.update.manifest --version $version --source-commit $SourceCommit `
        --built-at $builtAt --files-txt (Join-Path $repo "build\files.txt") --setup $setup --zip $zip `
        --out (Join-Path $repo "build\manifest.json")
}

Write-Host ""
Write-Host "Release build passed: ShelfSync $version (Setup, zip, files.txt, manifest.json in build\)"
