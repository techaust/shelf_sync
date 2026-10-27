; ShelfSync per-user installer (04 section 8, SYS-01, SYS-04, SYS-08). Built-in NSIS 3.13 parts only: MUI2, nsDialogs,
; nsExec, LogicLib, FileFunc, WordFunc. No plugin is added.
;
; Build (packaging/build.py has made build\ShelfSync-<v>\ first):
;   makensis /DVERSION=0.1.0 /DBUILD_DIR=..\build\ShelfSync-0.1.0 /DOUTFILE=..\build\ShelfSync-Setup-0.1.0.exe packaging\ShelfSync.nsi
; /DSUFFIX=-rehearsal makes a throwaway variant: its uninstall key, AUMID, Run value and shortcuts carry the suffix, so a
; local rehearsal never touches the real names. Install with /S /D=<folder> (silent, /D last and unquoted);
; uninstall with <folder>\uninstall.exe /S [/REMOVEDATA] [_?=<folder>].
;
; Layout: $INSTDIR\versions\<v>\ (the whole build folder), $INSTDIR\current (a junction to the active version, made with
; mklink /J: no admin), $INSTDIR\uninstall.exe. Data lives in %LOCALAPPDATA%\ShelfSync (or SHELFSYNC_DATA_DIR, which
; the app itself honours) and is kept unless "Remove my data" is ticked.

Unicode true
RequestExecutionLevel user
ManifestDPIAware true
SetCompressor /SOLID lzma

!ifndef VERSION
  !error "Pass /DVERSION=<X.Y.Z>"
!endif
!ifndef BUILD_DIR
  !error "Pass /DBUILD_DIR=<the build\ShelfSync-<v> folder>"
!endif
!ifndef OUTFILE
  !define OUTFILE "ShelfSync-Setup-${VERSION}.exe"
!endif
!ifndef SUFFIX
  !define SUFFIX ""
!endif

!define APP_NAME "ShelfSync"
!define PUBLISHER "TecHaust Technologies"
!define UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\ShelfSync${SUFFIX}"
!define RUN_KEY "Software\Microsoft\Windows\CurrentVersion\Run"
!define RUN_VALUE "ShelfSync${SUFFIX}"
!define AUMID "TecHaust.ShelfSync${SUFFIX}"
!define AUMID_KEY "Software\Classes\AppUserModelId\${AUMID}"
!define SHORTCUT "ShelfSync${SUFFIX}.lnk"

; ---- owner-facing strings (proposed wording for docs/13; the lead approves) ----------------------------------------
!define STR_RUNNING_SETUP "ShelfSync is running. Quit it from its tray icon, then run this installer again."
!define STR_RUNNING_UNINSTALL "ShelfSync is running. Quit it from its tray icon, then run the uninstaller again."
!define STR_OLDER "This installer is ShelfSync ${VERSION}, but a newer ShelfSync is already installed. Installing an older version could damage your data, so the installer stopped. Download the newest installer, or uninstall ShelfSync first."
!define STR_LINK_FAILED "The installer couldn't switch ShelfSync to the new version. Nothing else was changed. Close any window showing the ShelfSync folder and run the installer again."
!define STR_FINISH_RUN "Open ShelfSync"
!define STR_DATA_TITLE "Remove my data"
!define STR_DATA_TEXT "ShelfSync keeps your database, backups and logs, and the sign-in token it stored for you, even after it is removed, so a later install picks up where you left off."
!define STR_DATA_CHECK "Remove my data too (the database, backups, logs and the stored token). This can't be undone."
!define STR_DATA_PARTIAL "ShelfSync couldn't remove all of your data. Delete what is left of this folder yourself:"

Name "${APP_NAME}"
OutFile "${OUTFILE}"
InstallDir "$LOCALAPPDATA\Programs\ShelfSync"
BrandingText "ShelfSync by TecHaust"
ShowInstDetails nevershow
ShowUninstDetails nevershow

VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "ShelfSync"
VIAddVersionKey "CompanyName" "${PUBLISHER}"
VIAddVersionKey "FileDescription" "ShelfSync by TecHaust installer"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "ProductVersion" "${VERSION}"
VIAddVersionKey "LegalCopyright" "${PUBLISHER}"

!include MUI2.nsh
!include LogicLib.nsh
!include nsDialogs.nsh
!include FileFunc.nsh
!include WordFunc.nsh

!insertmacro GetParameters
!insertmacro GetOptions
!insertmacro un.GetParameters
!insertmacro un.GetOptions
!insertmacro VersionCompare

Var PreviousVersion
Var RemoveData
Var RemoveDataBox

; ---- MUI -----------------------------------------------------------------------------------------------------------
!define MUI_ICON "${__FILEDIR__}\..\brand\assets\app\shelfsync.ico"
!define MUI_UNICON "${__FILEDIR__}\..\brand\assets\app\shelfsync.ico"
!define MUI_ABORTWARNING
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_BITMAP "${__FILEDIR__}\..\brand\assets\installer\installer-header.bmp"
!define MUI_HEADERIMAGE_UNBITMAP "${__FILEDIR__}\..\brand\assets\installer\installer-header.bmp"
!define MUI_WELCOMEFINISHPAGE_BITMAP "${__FILEDIR__}\..\brand\assets\installer\installer-panel.bmp"
!define MUI_UNWELCOMEFINISHPAGE_BITMAP "${__FILEDIR__}\..\brand\assets\installer\installer-panel.bmp"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_INSTFILES
; "Open ShelfSync" is ticked: it runs the shortcut's own command (SYS-01: the wizard is the app's first screen).
!define MUI_FINISHPAGE_RUN "$INSTDIR\current\pythonw.exe"
!define MUI_FINISHPAGE_RUN_PARAMETERS "-m shelfsync.launcher"
!define MUI_FINISHPAGE_RUN_TEXT "${STR_FINISH_RUN}"
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
UninstPage custom un.DataPageCreate un.DataPageLeave
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

; ---- shared helpers ------------------------------------------------------------------------------------------------
; The data folder: SHELFSYNC_DATA_DIR if set (as the app does), otherwise %LOCALAPPDATA%\ShelfSync. Result in $0.
!macro DefineGetDataDir un
  Function ${un}GetDataDir
    ReadEnvStr $0 SHELFSYNC_DATA_DIR
    ${If} $0 == ""
      StrCpy $0 "$LOCALAPPDATA\ShelfSync"
    ${EndIf}
  FunctionEnd
!macroend
!insertmacro DefineGetDataDir ""
!insertmacro DefineGetDataDir "un."

; ShelfSync runs while instance.lock in the data folder can't be opened: the running copy holds it open with no
; sharing for the life of the process (a crash frees it). $0 = 1 if it runs.
!macro DefineIsRunning un
  Function ${un}IsRunning
    Call ${un}GetDataDir
    StrCpy $2 0
    ${If} ${FileExists} "$0\instance.lock"
      ClearErrors
      FileOpen $1 "$0\instance.lock" r
      ${If} ${Errors}
        StrCpy $2 1
      ${Else}
        FileClose $1
      ${EndIf}
    ${EndIf}
    StrCpy $0 $2
  FunctionEnd
!macroend
!insertmacro DefineIsRunning ""
!insertmacro DefineIsRunning "un."

; Remove every link (junction or symlink) inside a folder, the link itself only, so no later recursive delete can
; follow one out of the folder (04-A V40). `dir /AL` lists reparse points; `rmdir` on a link removes only the link.
!macro DefineUnlinkAll un
  Function ${un}UnlinkAll
    Exch $R0
    ${If} ${FileExists} "$R0\*.*"
      nsExec::Exec `cmd /c for /f "delims=" %i in ('dir /AL /S /B "$R0" 2^>nul') do @rmdir "%i" 2>nul`
      Pop $R1
    ${EndIf}
    Pop $R0
  FunctionEnd
!macroend
!insertmacro DefineUnlinkAll ""
!insertmacro DefineUnlinkAll "un."

!macro RemoveTreeSafely un FOLDER
  Push "${FOLDER}"
  Call ${un}UnlinkAll
  RMDir /r "${FOLDER}"
!macroend

; ---- installer -----------------------------------------------------------------------------------------------------
Function .onInit
  Call IsRunning
  ${If} $0 == 1
    MessageBox MB_OK|MB_ICONSTOP "${STR_RUNNING_SETUP}" /SD IDOK
    SetErrorLevel 5
    Abort
  ${EndIf}

  ; An older Setup must not run over a newer install (the database may be newer; db/migrate.py would refuse it).
  ; The same version reinstalls (repair).
  ReadRegStr $PreviousVersion HKCU "${UNINSTALL_KEY}" "DisplayVersion"
  ${If} $PreviousVersion != ""
    ${VersionCompare} "$PreviousVersion" "${VERSION}" $0
    ${If} $0 == 1
      MessageBox MB_OK|MB_ICONSTOP "${STR_OLDER}" /SD IDOK
      SetErrorLevel 6
      Abort
    ${EndIf}
  ${EndIf}
FunctionEnd

Section "ShelfSync" SecMain
  SetShellVarContext current
  SetOutPath "$INSTDIR"

  ; The new version goes into its own folder first; `current` still points at the old one until the last moment.
  !insertmacro RemoveTreeSafely "" "$INSTDIR\versions\${VERSION}"
  SetOutPath "$INSTDIR\versions\${VERSION}"
  SetOverwrite on
  File /r "${BUILD_DIR}\*.*"
  SetOutPath "$INSTDIR"

  ; Re-point `current`. RMDir (no /r) on a junction removes the link only, never its target.
  RMDir "$INSTDIR\current"
  nsExec::ExecToLog `cmd /c mklink /J "$INSTDIR\current" "$INSTDIR\versions\${VERSION}"`
  Pop $0
  ${If} $0 != 0
    MessageBox MB_OK|MB_ICONSTOP "${STR_LINK_FAILED}" /SD IDOK
    SetErrorLevel 7
    Abort
  ${EndIf}

  ; Keep the data, the version that was running (the one `current` pointed at, for "Roll back app") and the new one;
  ; remove every other version folder. A repair (the same version again) removes nothing: the rollback copy stays.
  ${If} $PreviousVersion != "${VERSION}"
    FindFirst $0 $1 "$INSTDIR\versions\*.*"
    ${DoWhile} $1 != ""
      ${If} $1 != "."
      ${AndIf} $1 != ".."
      ${AndIf} $1 != "${VERSION}"
      ${AndIf} $1 != $PreviousVersion
        !insertmacro RemoveTreeSafely "" "$INSTDIR\versions\$1"
      ${EndIf}
      FindNext $0 $1
    ${Loop}
    FindClose $0
  ${EndIf}

  ; Shortcuts: the same command everywhere, a path that never changes.
  CreateShortcut "$SMPROGRAMS\${SHORTCUT}" "$INSTDIR\current\pythonw.exe" "-m shelfsync.launcher" "$INSTDIR\current\shelfsync.ico" 0 SW_SHOWNORMAL "" "ShelfSync by TecHaust"
  CreateShortcut "$DESKTOP\${SHORTCUT}" "$INSTDIR\current\pythonw.exe" "-m shelfsync.launcher" "$INSTDIR\current\shelfsync.ico" 0 SW_SHOWNORMAL "" "ShelfSync by TecHaust"

  ; The toast name and icon (04-A V41).
  WriteRegStr HKCU "${AUMID_KEY}" "DisplayName" "ShelfSync"
  WriteRegStr HKCU "${AUMID_KEY}" "IconUri" "$INSTDIR\current\shelfsync.ico"

  ; Apps & features: exactly the keys m1b.2's contract names. The updater rewrites DisplayVersion after each switch.
  WriteUninstaller "$INSTDIR\uninstall.exe"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayName" "ShelfSync"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "Publisher" "${PUBLISHER}"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayIcon" "$INSTDIR\current\shelfsync.ico"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegStr HKCU "${UNINSTALL_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoRepair" 1
SectionEnd

; ---- uninstaller ---------------------------------------------------------------------------------------------------
Function un.onInit
  Call un.IsRunning
  ${If} $0 == 1
    MessageBox MB_OK|MB_ICONSTOP "${STR_RUNNING_UNINSTALL}" /SD IDOK
    SetErrorLevel 5
    Abort
  ${EndIf}
  ; Silent uninstall has no page to tick: /REMOVEDATA is the same choice.
  StrCpy $RemoveData 0
  ${un.GetParameters} $R0
  ClearErrors
  ${un.GetOptions} $R0 "/REMOVEDATA" $R1
  ${IfNot} ${Errors}
    StrCpy $RemoveData 1
  ${EndIf}
FunctionEnd

Function un.DataPageCreate
  !insertmacro MUI_HEADER_TEXT "${STR_DATA_TITLE}" ""
  nsDialogs::Create 1018
  Pop $0
  ${NSD_CreateLabel} 0 0 100% 36u "${STR_DATA_TEXT}"
  Pop $0
  ${NSD_CreateCheckbox} 0 44u 100% 30u "${STR_DATA_CHECK}"
  Pop $RemoveDataBox
  ; Off by default: data is kept unless the owner ticks it.
  ${NSD_SetState} $RemoveDataBox ${BST_UNCHECKED}
  nsDialogs::Show
FunctionEnd

Function un.DataPageLeave
  ${NSD_GetState} $RemoveDataBox $0
  ${If} $0 == ${BST_CHECKED}
    StrCpy $RemoveData 1
  ${Else}
    StrCpy $RemoveData 0
  ${EndIf}
FunctionEnd

Section "Uninstall"
  SetShellVarContext current
  SetOutPath "$TEMP"

  ; 1. (refused in un.onInit while ShelfSync runs.)
  ; 2. "Remove my data": the app's own module removes the Credential Manager entries it owns and the data folder, from
  ;    the installed Python and before any program file goes. A failure is reported; the program is still removed.
  ${If} $RemoveData == 1
    StrCpy $3 1
    ${If} ${FileExists} "$INSTDIR\current\python.exe"
      nsExec::ExecToLog `"$INSTDIR\current\python.exe" -m shelfsync.uninstall --remove-data`
      Pop $3
    ${EndIf}
    ${If} $3 != 0
      Call un.GetDataDir
      MessageBox MB_OK|MB_ICONEXCLAMATION "${STR_DATA_PARTIAL}$\r$\n$0" /SD IDOK
    ${EndIf}
  ${EndIf}

  ; 3. The `current` junction first, itself only (and the updater's `current.next`, if one was left).
  RMDir "$INSTDIR\current"
  RMDir "$INSTDIR\current.next"

  ; 4. versions\: every link inside is removed itself first, so the recursive delete can't follow one out.
  !insertmacro RemoveTreeSafely "un." "$INSTDIR\versions"

  ; 5. Shortcuts, the Run value, the AUMID key, the uninstall key, the uninstaller and the folder (only if empty:
  ;    nothing else in it is ours to delete).
  Delete "$SMPROGRAMS\${SHORTCUT}"
  Delete "$DESKTOP\${SHORTCUT}"
  DeleteRegValue HKCU "${RUN_KEY}" "${RUN_VALUE}"
  DeleteRegKey HKCU "${AUMID_KEY}"
  DeleteRegKey HKCU "${UNINSTALL_KEY}"
  Delete "$INSTDIR\uninstall.exe"
  RMDir "$INSTDIR"
SectionEnd
