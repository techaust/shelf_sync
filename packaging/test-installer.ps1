# Silent install, checks, then silent uninstall of a built ShelfSync Setup (SYS-01, SYS-08, 04-A V39, V40).
# Used by release.yml (a throwaway runner, real names) and for the local rehearsal (a throwaway -Suffix and -Root; the
# Setup was built with the same /DSUFFIX). Never touches %LOCALAPPDATA%\Programs\ShelfSync: everything is under -Root.
#
#   powershell -File packaging\test-installer.ps1 -Setup <Setup.exe> -Version 0.1.0 -Root <empty throwaway folder> [-Suffix -rehearsal] [-RemoveData]
#
# -RemoveData also installs again and uninstalls with /REMOVEDATA against a throwaway data folder (SHELFSYNC_DATA_DIR);
# that run asks Credential Manager to delete ShelfSync's own entries, so only use it on a throwaway account or runner.
param(
    [Parameter(Mandatory = $true)][string]$Setup,
    [Parameter(Mandatory = $true)][string]$Version,
    [Parameter(Mandatory = $true)][string]$Root,
    [string]$Suffix = "",
    [switch]$RemoveData
)
$ErrorActionPreference = "Stop"
$failures = New-Object System.Collections.Generic.List[string]
function Check([bool]$ok, [string]$what) {
    if ($ok) { Write-Host "ok   $what" } else { Write-Host "FAIL $what"; $failures.Add($what) }
}

if ((Test-Path $Root) -and (Get-ChildItem $Root -Force | Select-Object -First 1)) { throw "$Root isn't empty; use a new throwaway folder" }
New-Item -ItemType Directory -Force $Root | Out-Null
$Root = (Resolve-Path $Root).Path
$install = Join-Path $Root "Programs\ShelfSync"
$data = Join-Path $Root "data\ShelfSync"
$outside = Join-Path $Root "outside"
$env:SHELFSYNC_DATA_DIR = $data   # the installer's "is it running" check and the uninstaller use the same data folder
$uninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\ShelfSync$Suffix"
$aumidKey = "HKCU:\Software\Classes\AppUserModelId\TecHaust.ShelfSync$Suffix"
$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$startMenu = Join-Path ([Environment]::GetFolderPath("Programs")) "ShelfSync$Suffix.lnk"
$desktop = Join-Path ([Environment]::GetFolderPath("Desktop")) "ShelfSync$Suffix.lnk"

function Install([string]$exe) {
    $p = Start-Process -FilePath $exe -ArgumentList "/S", "/D=$install" -Wait -PassThru
    return $p.ExitCode
}

# ---- install --------------------------------------------------------------------------------------------------
Check ((Install $Setup) -eq 0) "silent install exits 0"
$current = Join-Path $install "current"
$item = Get-Item $current -Force
Check ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) "current is a junction (a reparse point)"
Check ($item.Target -and (@($item.Target)[0] -like "*versions\$Version")) "current points at versions\$Version"
Check (Test-Path (Join-Path $current "pythonw.exe")) "current\pythonw.exe exists"
Check (Test-Path (Join-Path $install "versions\$Version\shelfsync\__init__.py")) "the package is in versions\$Version"
Check (Test-Path (Join-Path $install "versions\$Version\ui\index.html")) "the UI is in versions\$Version"
Check (Test-Path (Join-Path $install "uninstall.exe")) "uninstall.exe is at the root"
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
Check ($u.UninstallString -eq ('"' + (Join-Path $install "uninstall.exe") + '"')) "uninstall key UninstallString"
Check ($u.InstallLocation -eq $install) "uninstall key InstallLocation"
Check ($u.DisplayIcon -like "*current\shelfsync.ico") "uninstall key DisplayIcon"
Check (($u.NoModify -eq 1) -and ($u.NoRepair -eq 1)) "uninstall key NoModify and NoRepair"
$a = Get-ItemProperty $aumidKey
Check ($a.DisplayName -eq "ShelfSync" -and $a.IconUri -like "*current\shelfsync.ico") "AUMID key DisplayName and IconUri"
$ver = & (Join-Path $current "python.exe") -c "import shelfsync; print(shelfsync.__version__)"
Check ($ver -eq $Version) "the installed Python imports shelfsync $Version (got '$ver')"

# ---- "ShelfSync is running": the lock file held open with no sharing blocks a second Setup -----------------------
New-Item -ItemType Directory -Force $data | Out-Null
$lock = [IO.File]::Open((Join-Path $data "instance.lock"), "OpenOrCreate", "ReadWrite", "None")
try { $code = Install $Setup } finally { $lock.Close() }
Check ($code -ne 0) "Setup refuses while instance.lock is held (exit $code)"
Remove-Item (Join-Path $data "instance.lock") -Force

# ---- the sentinel: a junction inside versions\<v> to a folder outside $INSTDIR ---------------------------------
New-Item -ItemType Directory -Force $outside | Out-Null
Set-Content (Join-Path $outside "keep.txt") "must survive"
cmd /c mklink /J "`"$(Join-Path $install "versions\$Version\sentinel-link")`"" "`"$outside`"" | Out-Null
Check (Test-Path (Join-Path $install "versions\$Version\sentinel-link\keep.txt")) "the sentinel junction is in place"
Set-ItemProperty -Path $runKey -Name "ShelfSync$Suffix" -Value "planted"

# ---- uninstall (the _?= rule: the uninstaller runs in place and this waits for it to end) ------------------------
$un = Start-Process -FilePath (Join-Path $install "uninstall.exe") -ArgumentList "/S", "_?=$install" -Wait -PassThru
Check ($un.ExitCode -eq 0) "silent uninstall exits 0"
$left = @(Get-ChildItem $install -Force | ForEach-Object { $_.Name })
Check (($left.Count -eq 1) -and ($left[0] -eq "uninstall.exe")) "only uninstall.exe is left in the program folder (left: $($left -join ', '))"
Check (Test-Path (Join-Path $outside "keep.txt")) "the sentinel file outside survived (RMDir did not follow the junction)"
Check (-not (Test-Path $startMenu) -and -not (Test-Path $desktop)) "both shortcuts are gone"
Check (-not (Test-Path $uninstallKey)) "the uninstall key is gone"
Check (-not (Test-Path $aumidKey)) "the AUMID key is gone"
Check ($null -eq (Get-ItemProperty $runKey -Name "ShelfSync$Suffix" -ErrorAction SilentlyContinue)) "the Run value is gone"
Remove-Item (Join-Path $install "uninstall.exe") -Force   # held by the _?= run; nothing else is left
Remove-Item $install -Force
Check (-not (Test-Path $install)) "the program folder is gone"

# ---- "Remove my data" -------------------------------------------------------------------------------------------
if ($RemoveData) {
    Check ((Install $Setup) -eq 0) "second silent install exits 0"
    New-Item -ItemType Directory -Force (Join-Path $data "logs") | Out-Null
    Set-Content (Join-Path $data "shelfsync.db") "db"
    cmd /c mklink /J "`"$(Join-Path $data "logs\data-link")`"" "`"$outside`"" | Out-Null
    $un = Start-Process -FilePath (Join-Path $install "uninstall.exe") -ArgumentList "/S", "/REMOVEDATA", "_?=$install" -Wait -PassThru
    Check ($un.ExitCode -eq 0) "uninstall with /REMOVEDATA exits 0"
    Check (-not (Test-Path $data)) "the data folder is gone"
    Check (Test-Path (Join-Path $outside "keep.txt")) "the file behind a junction in the data folder survived"
    Remove-Item (Join-Path $install "uninstall.exe") -Force -ErrorAction SilentlyContinue
    Remove-Item $install -Force -ErrorAction SilentlyContinue
}

Remove-Item $Root -Recurse -Force -ErrorAction SilentlyContinue
if ($failures.Count -gt 0) { Write-Host "`n$($failures.Count) check(s) failed"; exit 1 }
Write-Host "`nAll installer checks passed"
