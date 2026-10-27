# Silent install, checks, then silent uninstall of a built ShelfSync Setup (SYS-01, SYS-08, 04-A V39, V40).
# Used by release.yml (a throwaway runner, real names) and for the local rehearsal (a throwaway -Suffix and -Root; the
# Setups were built with the same /DSUFFIX). Never touches %LOCALAPPDATA%\Programs\ShelfSync: everything is under -Root.
#
#   powershell -File packaging\test-installer.ps1 -Setup <Setup.exe> -Version 0.1.0 -Root <new throwaway folder> `
#       [-Suffix -rehearsal] [-OlderSetup <Setup built as a lower X.Y.Z>] [-NewerSetup <Setup built as a higher X.Y.Z>
#       -NewerVersion <that version>] [-RemoveData]
#
# The scenarios: the plain install and uninstall with a sentinel junction (V40); "ShelfSync is running" (exit 5); and,
# with -NewerSetup / -OlderSetup, the upgrade and its prune, links in the way of every delete (a version folder that is a
# junction, `versions` itself a junction, a junction that can't be removed, a link inside a junction's target), the older
# Setup refused (exit 6, also by the version folders alone). -RemoveData also uninstalls with /REMOVEDATA against a
# throwaway data folder; a build with a -Suffix passes `--service ShelfSync<suffix>`, so it never touches the real
# Credential Manager service, but a build with no suffix does (only on a throwaway runner).
param(
    [Parameter(Mandatory = $true)][string]$Setup,
    [Parameter(Mandatory = $true)][string]$Version,
    [Parameter(Mandatory = $true)][string]$Root,
    [string]$Suffix = "",
    [string]$OlderSetup = "",
    [string]$NewerSetup = "",
    [string]$NewerVersion = "",
    [switch]$RemoveData
)
$ErrorActionPreference = "Stop"
$failures = New-Object System.Collections.Generic.List[string]
function Check([bool]$ok, [string]$what) {
    if ($ok) { Write-Host "ok   $what" } else { Write-Host "FAIL $what"; $failures.Add($what) }
}
# True once none of the paths exists, waiting up to 10 s: a Desktop synced by OneDrive (this PC) can show a deleted
# shortcut for a moment after the uninstaller removed it (a local run failed on it once; the next check passed).
function Gone([string[]]$paths) {
    for ($i = 0; $i -lt 20; $i++) {
        if (-not ($paths | Where-Object { Test-Path $_ })) { return $true }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

if ((Test-Path $Root) -and (Get-ChildItem $Root -Force | Select-Object -First 1)) { throw "$Root isn't empty; use a new throwaway folder" }
New-Item -ItemType Directory -Force $Root | Out-Null
$Root = (Resolve-Path $Root).Path
$uninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\ShelfSync$Suffix"
$aumidKey = "HKCU:\Software\Classes\AppUserModelId\TecHaust.ShelfSync$Suffix"
$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$startMenu = Join-Path ([Environment]::GetFolderPath("Programs")) "ShelfSync$Suffix.lnk"
$desktop = Join-Path ([Environment]::GetFolderPath("Desktop")) "ShelfSync$Suffix.lnk"

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
public static class LinkHold {
    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    public static extern SafeFileHandle CreateFileW(string name, uint access, uint share, IntPtr security, uint disposition, uint flags, IntPtr template);
    // Opens the folder or link itself (backup semantics + open reparse point) with no sharing: it can't be removed while held.
    public static SafeFileHandle Hold(string path) {
        return CreateFileW(path, 0x80000000, 0, IntPtr.Zero, 3, 0x02000000 | 0x00200000, IntPtr.Zero);
    }
}
"@

# One scenario = one fresh program folder and data folder under $Root.
function New-Scenario([string]$name) {
    $script:scenario = $name
    $script:install = Join-Path $Root "$name\Programs\ShelfSync"
    $script:data = Join-Path $Root "$name\data\ShelfSync"
    $script:outside = Join-Path $Root "$name\outside"
    $env:SHELFSYNC_DATA_DIR = $script:data
    New-Item -ItemType Directory -Force $script:outside | Out-Null
    Write-Host "`n== $name"
}
function Install([string]$exe) {
    $p = Start-Process -FilePath $exe -ArgumentList "/S", "/D=$script:install" -Wait -PassThru
    return $p.ExitCode
}
function Uninstall([string[]]$more = @()) {
    $p = Start-Process -FilePath (Join-Path $script:install "uninstall.exe") -ArgumentList (@("/S") + $more + @("_?=$script:install")) -Wait -PassThru
    return $p.ExitCode
}
function New-Junction([string]$link, [string]$target) {
    $parent = Split-Path $link
    if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Force $parent | Out-Null }
    cmd /c mklink /J "`"$link`"" "`"$target`"" | Out-Null
}
function Is-Link([string]$path) {
    $i = Get-Item $path -Force -ErrorAction SilentlyContinue
    return ($null -ne $i) -and [bool]($i.Attributes -band [IO.FileAttributes]::ReparsePoint)
}
function Versions { return ((Get-ChildItem (Join-Path $script:install "versions") -Directory -Force -ErrorAction SilentlyContinue | ForEach-Object { $_.Name } | Sort-Object) -join ",") }
function Finish-Uninstalled {
    Remove-Item (Join-Path $script:install "uninstall.exe") -Force -ErrorAction SilentlyContinue
    Remove-Item $script:install -Force -ErrorAction SilentlyContinue
}

# ---- 1. install, the contract, the running refusal, the sentinel, uninstall ---------------------------------------------
New-Scenario "plain"
Check ((Install $Setup) -eq 0) "silent install exits 0"
$current = Join-Path $script:install "current"
$item = Get-Item $current -Force
Check ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) "current is a junction (a reparse point)"
Check ($item.Target -and (@($item.Target)[0] -like "*versions\$Version")) "current points at versions\$Version"
Check (-not (Test-Path (Join-Path $script:install "current.next")) -and -not (Test-Path (Join-Path $script:install "current.old"))) "no current.next or current.old is left"
Check (Test-Path (Join-Path $current "pythonw.exe")) "current\pythonw.exe exists"
Check (Test-Path (Join-Path $script:install "versions\$Version\shelfsync\__init__.py")) "the package is in versions\$Version"
Check (Test-Path (Join-Path $script:install "versions\$Version\ui\index.html")) "the UI is in versions\$Version"
Check (Test-Path (Join-Path $script:install "uninstall.exe")) "uninstall.exe is at the root"
$shell = New-Object -ComObject WScript.Shell
foreach ($lnk in @($startMenu, $desktop)) {
    Check (Test-Path $lnk) "shortcut exists: $lnk"
    if (Test-Path $lnk) {
        $s = $shell.CreateShortcut($lnk)
        Check ($s.TargetPath -eq (Join-Path $current "pythonw.exe")) "shortcut target is current\pythonw.exe"
        Check ($s.Arguments -eq "-m shelfsync.launcher") "shortcut arguments are -m shelfsync.launcher"
        Check ($s.IconLocation -like "*current\shelfsync.ico*") "shortcut icon is current\shelfsync.ico"
    }
}
$u = Get-ItemProperty $uninstallKey
Check ($u.DisplayName -eq "ShelfSync") "uninstall key DisplayName"
Check ($u.DisplayVersion -eq $Version) "uninstall key DisplayVersion"
Check ($u.Publisher -eq "TecHaust Technologies") "uninstall key Publisher"
Check ($u.UninstallString -eq ('"' + (Join-Path $script:install "uninstall.exe") + '"')) "uninstall key UninstallString"
Check ($u.InstallLocation -eq $script:install) "uninstall key InstallLocation"
Check ($u.DisplayIcon -like "*current\shelfsync.ico") "uninstall key DisplayIcon"
Check (($u.NoModify -eq 1) -and ($u.NoRepair -eq 1)) "uninstall key NoModify and NoRepair"
$a = Get-ItemProperty $aumidKey
Check ($a.DisplayName -eq "ShelfSync" -and $a.IconUri -like "*current\shelfsync.ico") "AUMID key DisplayName and IconUri"
$ver = & (Join-Path $current "python.exe") -c "import shelfsync; print(shelfsync.__version__)"
Check ($ver -eq $Version) "the installed Python imports shelfsync $Version (got '$ver')"

# "ShelfSync is running": the lock file held open with no sharing blocks a second Setup (exit 5) and the uninstaller (exit 5).
New-Item -ItemType Directory -Force $script:data | Out-Null
$lock = [IO.File]::Open((Join-Path $script:data "instance.lock"), "OpenOrCreate", "ReadWrite", "None")
try { $code = Install $Setup; $ucode = Uninstall } finally { $lock.Close() }
Check ($code -eq 5) "Setup refuses while instance.lock is held (exit $code, expected 5)"
Check ($ucode -eq 5) "the uninstaller refuses while instance.lock is held (exit $ucode, expected 5)"
Check (Test-Path (Join-Path $script:install "current\python.exe")) "nothing was removed by the refused uninstall"
Remove-Item (Join-Path $script:data "instance.lock") -Force

# The sentinel: a junction inside versions\<v> to a folder outside the program folder (V40).
Set-Content (Join-Path $script:outside "keep.txt") "must survive"
New-Junction (Join-Path $script:install "versions\$Version\sentinel-link") $script:outside
Check (Test-Path (Join-Path $script:install "versions\$Version\sentinel-link\keep.txt")) "the sentinel junction is in place"
Set-ItemProperty -Path $runKey -Name "ShelfSync$Suffix" -Value "planted"
Check ((Uninstall) -eq 0) "silent uninstall exits 0"
$left = @(Get-ChildItem $script:install -Force | ForEach-Object { $_.Name })
Check (($left.Count -eq 1) -and ($left[0] -eq "uninstall.exe")) "only uninstall.exe is left in the program folder (left: $($left -join ', '))"
Check (Test-Path (Join-Path $script:outside "keep.txt")) "the sentinel file outside survived (the delete did not follow the junction)"
Check (Gone @($startMenu, $desktop)) "both shortcuts are gone"
Check (-not (Test-Path $uninstallKey)) "the uninstall key is gone"
Check (-not (Test-Path $aumidKey)) "the AUMID key is gone"
Check ($null -eq (Get-ItemProperty $runKey -Name "ShelfSync$Suffix" -ErrorAction SilentlyContinue)) "the Run value is gone"
Finish-Uninstalled
Check (-not (Test-Path $script:install)) "the program folder is gone"

# ---- 2. links in the way of a delete -----------------------------------------------------------------------------
# A version folder that is a junction, met by the installer's pre-clean of versions\<v>.
New-Scenario "preclean-link"
Set-Content (Join-Path $script:outside "keep.txt") "must survive"
New-Item -ItemType Directory -Force (Join-Path $script:install "versions") | Out-Null
New-Junction (Join-Path $script:install "versions\$Version") $script:outside
Check ((Install $Setup) -eq 0) "install over a versions\$Version that is a junction exits 0"
Check (Test-Path (Join-Path $script:outside "keep.txt")) "the file behind that junction survived the pre-clean"
Check (-not (Is-Link (Join-Path $script:install "versions\$Version"))) "versions\$Version is a real folder now"
Check (Test-Path (Join-Path $script:install "versions\$Version\python.exe")) "the version was installed into the real folder"
Check ((Uninstall) -eq 0) "uninstall exits 0"
Finish-Uninstalled

# `versions` itself a junction, met by the uninstaller.
New-Scenario "versions-link"
Check ((Install $Setup) -eq 0) "install exits 0"
Rename-Item (Join-Path $script:install "versions") "versions-real"
New-Junction (Join-Path $script:install "versions") (Join-Path $script:install "versions-real")
Check ((Uninstall) -eq 0) "uninstall exits 0 with versions as a junction"
Check (-not (Test-Path (Join-Path $script:install "versions"))) "the versions junction itself is gone"
Check (Test-Path (Join-Path $script:install "versions-real\$Version\python.exe")) "what it pointed at was not deleted through the link"
Remove-Item $script:install -Recurse -Force

# A link inside a junction's target, and a junction that can't be removed.
New-Scenario "stuck-link"
Check ((Install $Setup) -eq 0) "install exits 0"
$behind = Join-Path $Root "stuck-link\behind"
$deeper = Join-Path $Root "stuck-link\deeper"
New-Item -ItemType Directory -Force $behind, $deeper | Out-Null
Set-Content (Join-Path $behind "keep-a.txt") "must survive"
Set-Content (Join-Path $deeper "keep-b.txt") "must survive"
New-Junction (Join-Path $behind "inner") $deeper                     # a link inside the target of ...
New-Junction (Join-Path $script:install "versions\0.0.5") $behind    # ... this junction (a stale version folder)
$held = [LinkHold]::Hold((Join-Path $script:install "versions\0.0.5"))
Check (-not $held.IsInvalid) "the junction versions\0.0.5 is held open (it can't be removed)"
$code = Uninstall
Check ($code -eq 8) "uninstall stops with exit 8 when a link can't be removed (exit $code)"
Check ((Test-Path (Join-Path $behind "keep-a.txt")) -and (Test-Path (Join-Path $deeper "keep-b.txt"))) "nothing behind the held junction was deleted"
Check (Test-Path $uninstallKey) "the uninstall key is still there (the uninstall didn't pretend to finish)"
$held.Close()
$code = Uninstall
Check ($code -eq 0) "uninstall exits 0 once the junction can be removed (exit $code)"
Check ((Test-Path (Join-Path $behind "keep-a.txt")) -and (Test-Path (Join-Path $deeper "keep-b.txt"))) "the link inside the junction's target and both targets survived"
Check (Is-Link (Join-Path $behind "inner")) "the link inside the target is untouched"
Finish-Uninstalled

# ---- 2b. a switch killed between its two renames: `current` is missing, `current.old` and `current.next` are left over ----
# `current.old` is the version that was running; `current.next` points at the NEW version's folder (which exists, as it
# does when a real switch is killed).
function Plant-KilledSwitch([string]$old, [string]$next) {
    $cur = Join-Path $script:install "current"
    if (Test-Path $cur) { cmd /c rmdir "`"$cur`"" | Out-Null }   # removes the junction only
    if (-not (Test-Path $next)) { New-Item -ItemType Directory -Force $next | Out-Null; Set-Content (Join-Path $next "marker.txt") "new" }
    New-Junction (Join-Path $script:install "current.old") $old
    New-Junction (Join-Path $script:install "current.next") $next
}
New-Scenario "recover"
Check ((Install $Setup) -eq 0) "install exits 0"
Plant-KilledSwitch (Join-Path $script:install "versions\$Version") (Join-Path $script:install "versions\0.0.7")
Check (-not (Test-Path (Join-Path $script:install "current"))) "current is missing and current.old and current.next are planted"
Check ((Install $Setup) -eq 0) "running Setup again recovers (exit 0)"
$cur = Join-Path $script:install "current"
Check ((Is-Link $cur) -and (@((Get-Item $cur -Force).Target)[0] -like "*versions\$Version")) "current is a junction to versions\$Version again"
Check (-not (Test-Path (Join-Path $script:install "current.old")) -and -not (Test-Path (Join-Path $script:install "current.next"))) "the leftover junctions are gone"
Check (Test-Path (Join-Path $script:install "versions\$Version\python.exe")) "the version folder behind them was not deleted"
# The uninstaller removes a leftover current.old too (without following it).
Set-Content (Join-Path $script:outside "keep.txt") "must survive"
New-Junction (Join-Path $script:install "current.old") $script:outside
Check ((Uninstall) -eq 0) "uninstall exits 0 with a leftover current.old"
$left = @(Get-ChildItem $script:install -Force | ForEach-Object { $_.Name })
Check (($left.Count -eq 1) -and ($left[0] -eq "uninstall.exe")) "only uninstall.exe is left (left: $($left -join ', '))"
Check (Test-Path (Join-Path $script:outside "keep.txt")) "the file behind current.old survived"
Finish-Uninstalled

# ---- 3. upgrade, prune, older refused -------------------------------------------------------------------------------
if ($NewerSetup -ne "") {
    New-Scenario "upgrade"
    Check ((Install $Setup) -eq 0) "install $Version exits 0"
    $stale = Join-Path $Root "upgrade\stale-target"
    $stale2 = Join-Path $Root "upgrade\stale-inner"
    New-Item -ItemType Directory -Force $stale, $stale2 | Out-Null
    Set-Content (Join-Path $stale "keep-a.txt") "must survive"
    Set-Content (Join-Path $stale2 "keep-b.txt") "must survive"
    New-Junction (Join-Path $stale "inner") $stale2
    New-Junction (Join-Path $script:install "versions\0.0.5") $stale   # an old version folder that is a junction
    Check ((Install $NewerSetup) -eq 0) "upgrade to $NewerVersion exits 0"
    $expected = (($Version, $NewerVersion) | Sort-Object) -join ","
    Check ((Versions) -eq $expected) "the upgrade keeps the running version and the new one, and prunes the rest (got: $(Versions))"
    Check ((Test-Path (Join-Path $stale "keep-a.txt")) -and (Test-Path (Join-Path $stale2 "keep-b.txt"))) "the prune unlinked the old junction without deleting what was behind it"
    $cur = Get-Item (Join-Path $script:install "current") -Force
    Check (@($cur.Target)[0] -like "*versions\$NewerVersion") "current points at $NewerVersion"
    Check ((Get-ItemProperty $uninstallKey).DisplayVersion -eq $NewerVersion) "DisplayVersion is $NewerVersion"
    Check ((Install $NewerSetup) -eq 0) "a repair of $NewerVersion exits 0"
    Check ((Versions) -eq $expected) "a repair removes nothing (the rollback copy stays)"
    if ($OlderSetup -ne "") {
        $code = Install $OlderSetup
        Check ($code -eq 6) "an older Setup is refused with exit 6 (exit $code)"
        Check ((Get-ItemProperty $uninstallKey).DisplayVersion -eq $NewerVersion) "the refused Setup changed nothing"
        # The registry can be out of step with the folders: the version folders alone must refuse it too.
        Set-ItemProperty $uninstallKey -Name DisplayVersion -Value "0.0.0"
        $code = Install $OlderSetup
        Check ($code -eq 6) "an older Setup is refused by the version folders alone (exit $code)"
        Set-ItemProperty $uninstallKey -Name DisplayVersion -Value $NewerVersion
    }
    Check ((Uninstall) -eq 0) "uninstall exits 0"
    Finish-Uninstalled

    # The prune keeps the version `current` really points at, even when the registry says something else.
    New-Scenario "keep-current"
    Check ((Install $Setup) -eq 0) "install $Version exits 0"
    Set-ItemProperty $uninstallKey -Name DisplayVersion -Value "0.0.3"
    foreach ($d in "0.0.3", "0.0.4") {
        New-Item -ItemType Directory -Force (Join-Path $script:install "versions\$d") | Out-Null
        Set-Content (Join-Path $script:install "versions\$d\x.txt") "x"
    }
    Check ((Install $NewerSetup) -eq 0) "upgrade to $NewerVersion exits 0"
    $expected = (($Version, $NewerVersion, "0.0.3") | Sort-Object) -join ","
    Check ((Versions) -eq $expected) "the prune kept what current pointed at ($Version), the registry's 0.0.3 and the new one, and removed 0.0.4 (got: $(Versions))"
    Check ((Uninstall) -eq 0) "uninstall exits 0"
    Finish-Uninstalled

    # A killed switch plus an upgrade: the version a leftover current.old points at is kept, and current is made again.
    New-Scenario "recover-upgrade"
    Check ((Install $Setup) -eq 0) "install $Version exits 0"
    Set-ItemProperty $uninstallKey -Name DisplayVersion -Value "0.0.0"
    Plant-KilledSwitch (Join-Path $script:install "versions\$Version") (Join-Path $script:install "versions\$NewerVersion")
    Check ((Install $NewerSetup) -eq 0) "upgrade over a killed switch exits 0"
    $cur = Get-Item (Join-Path $script:install "current") -Force
    Check ((Is-Link $cur.FullName) -and (@($cur.Target)[0] -like "*versions\$NewerVersion")) "current points at $NewerVersion"
    Check (-not (Test-Path (Join-Path $script:install "current.old")) -and -not (Test-Path (Join-Path $script:install "current.next"))) "the leftover junctions are gone"
    Check ((Versions) -eq ((($Version, $NewerVersion) | Sort-Object) -join ",")) "the version current.old pointed at was kept (got: $(Versions))"
    Check ((Uninstall) -eq 0) "uninstall exits 0"
    Finish-Uninstalled
}

# ---- 4. "Remove my data" -------------------------------------------------------------------------------------------
if ($RemoveData) {
    New-Scenario "remove-data"
    Check ((Install $Setup) -eq 0) "install exits 0"
    New-Item -ItemType Directory -Force (Join-Path $script:data "logs") | Out-Null
    Set-Content (Join-Path $script:data "shelfsync.db") "db"
    Set-Content (Join-Path $script:outside "keep.txt") "must survive"
    New-Junction (Join-Path $script:data "logs\data-link") $script:outside
    Check ((Uninstall @("/REMOVEDATA")) -eq 0) "uninstall with /REMOVEDATA exits 0"
    Check (-not (Test-Path $script:data)) "the data folder is gone"
    Check (Test-Path (Join-Path $script:outside "keep.txt")) "the file behind a junction in the data folder survived"
    Finish-Uninstalled

    # "Remove my data" after a killed switch: `current` is missing, so the data is removed with current.old's Python.
    New-Scenario "remove-data-killed-switch"
    Check ((Install $Setup) -eq 0) "install exits 0"
    New-Item -ItemType Directory -Force (Join-Path $script:data "logs") | Out-Null
    Set-Content (Join-Path $script:data "shelfsync.db") "db"
    Plant-KilledSwitch (Join-Path $script:install "versions\$Version") (Join-Path $script:install "versions\0.0.7")
    Check (-not (Test-Path (Join-Path $script:install "current"))) "current is missing"
    Check ((Uninstall @("/REMOVEDATA")) -eq 0) "uninstall with /REMOVEDATA exits 0"
    Check (-not (Test-Path $script:data)) "the data folder was removed through current.old's Python"
    Finish-Uninstalled

    # No Python at all (current, current.old and current.next are gone): nothing is removed, and the data stays.
    New-Scenario "remove-data-no-python"
    Check ((Install $Setup) -eq 0) "install exits 0"
    New-Item -ItemType Directory -Force (Join-Path $script:data "logs") | Out-Null
    Set-Content (Join-Path $script:data "shelfsync.db") "db"
    $cur = Join-Path $script:install "current"
    cmd /c rmdir "`"$cur`"" | Out-Null
    Check ((Uninstall @("/REMOVEDATA")) -eq 0) "uninstall exits 0 (the notice says nothing was removed)"
    Check (Test-Path (Join-Path $script:data "shelfsync.db")) "the data is still there: nothing was removed"
    Check (-not (Test-Path (Join-Path $script:install "versions"))) "the program was still removed"
    Finish-Uninstalled
    Remove-Item $script:data -Recurse -Force -ErrorAction SilentlyContinue
}

Remove-Item Env:SHELFSYNC_DATA_DIR -ErrorAction SilentlyContinue
Remove-Item $Root -Recurse -Force -ErrorAction SilentlyContinue
if ($failures.Count -gt 0) { Write-Host "`n$($failures.Count) check(s) failed"; exit 1 }
Write-Host "`nAll installer checks passed"
