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
!ifdef FAST
  SetCompressor zlib ; test builds only (release.yml's extra Setups), never the release
!else
  SetCompressor /SOLID lzma
!endif

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
!define STR_LINK_FAILED "The installer couldn't switch ShelfSync to the new version. The version you had installed was left as it was. Close any window showing the ShelfSync folder and run the installer again."
!define STR_UNSAFE "ShelfSync stopped removing files because it found a link in its program folder that it couldn't remove safely. Nothing outside the program folder was touched. This is what is left:"
!define STR_DATA_NOT_OURS "ShelfSync left this folder alone because it doesn't look like ShelfSync's own data folder:"
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

; A recursive delete that never follows a link (04-A V40: NSIS 3.13's own `RMDir /r` does, checked on this PC). Every
; entry, the top folder included, is asked for its attributes first (GetFileAttributesW does not follow a link):
; a reparse point (0x400) is removed itself with RMDir (a link to a folder) or Delete (a link to a file), never
; entered; only real folders are recursed into. If anything still exists afterwards the whole delete stops and
; reports it. In: the path on the stack. Out: "0" if it is gone, "1" if something is left.
!macro DefineDeleteTree un
  Function ${un}DeleteTree
    Exch $R0
    Push $R1
    Push $R2
    Push $R3
    Push $R4
    Push $R5
    Push $R6
    StrCpy $R3 0
    System::Call 'kernel32::GetFileAttributesW(w R0) i .R1'
    ${If} $R1 == -1
      Goto done
    ${EndIf}
    IntOp $R2 $R1 & 0x10
    IntOp $R6 $R1 & 0x400
    ${If} $R6 != 0
      ${If} $R2 != 0
        RMDir "$R0"
      ${Else}
        Delete "$R0"
      ${EndIf}
      Goto verify
    ${EndIf}
    ${If} $R2 == 0
      SetFileAttributes "$R0" NORMAL
      Delete "$R0"
      Goto verify
    ${EndIf}
    FindFirst $R4 $R5 "$R0\*.*"
    ${DoWhile} $R5 != ""
      ${If} $R5 != "."
      ${AndIf} $R5 != ".."
        Push "$R0\$R5"
        Call ${un}DeleteTree
        Pop $R6
        ${If} $R6 != 0
          StrCpy $R3 1
          ${Break}
        ${EndIf}
      ${EndIf}
      FindNext $R4 $R5
    ${Loop}
    FindClose $R4
    ${If} $R3 == 0
      RMDir "$R0"
    ${EndIf}
    verify:
    System::Call 'kernel32::GetFileAttributesW(w R0) i .R1'
    ${If} $R1 != -1
      StrCpy $R3 1
    ${EndIf}
    done:
    StrCpy $R0 $R3
    Pop $R6
    Pop $R5
    Pop $R4
    Pop $R3
    Pop $R2
    Pop $R1
    Exch $R0
  FunctionEnd
!macroend
!insertmacro DefineDeleteTree ""
!insertmacro DefineDeleteTree "un."

; Delete a tree or stop: tell the owner which path is left, and end with exit code 8. Nothing outside the tree was touched.
!macro DeleteTreeOrStop un FOLDER
  Push "${FOLDER}"
  Call ${un}DeleteTree
  Pop $R9
  ${If} $R9 != 0
    MessageBox MB_OK|MB_ICONSTOP "${STR_UNSAFE}$\r$\n${FOLDER}" /SD IDOK
    SetErrorLevel 8
    Abort
  ${EndIf}
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

  ; The registry can be out of step with the folders (the updater, a half-finished install): a version folder newer
  ; than this Setup counts too. Only names that start with a digit are versions (not `.incoming-...`).
  FindFirst $2 $3 "$INSTDIR\versions\*.*"
  ${DoWhile} $3 != ""
    StrCpy $4 $3 1
    ${If} $4 S>= "0"
    ${AndIf} $4 S<= "9"
      ${VersionCompare} "$3" "${VERSION}" $0
      ${If} $0 == 1
        FindClose $2
        MessageBox MB_OK|MB_ICONSTOP "${STR_OLDER}" /SD IDOK
        SetErrorLevel 6
        Abort
      ${EndIf}
    ${EndIf}
    FindNext $2 $3
  ${Loop}
  FindClose $2
FunctionEnd

Section "ShelfSync" SecMain
  SetShellVarContext current
  ; Checked again here: the first check was in .onInit, and ShelfSync may have been started since (while the wizard sat open).
  Call IsRunning
  ${If} $0 == 1
    MessageBox MB_OK|MB_ICONSTOP "${STR_RUNNING_SETUP}" /SD IDOK
    SetErrorLevel 5
    Abort
  ${EndIf}
  SetOutPath "$INSTDIR"

  ; The new version goes into its own folder first; `current` still points at the old one until the last moment.
  !insertmacro DeleteTreeOrStop "" "$INSTDIR\versions\${VERSION}"
  SetOutPath "$INSTDIR\versions\${VERSION}"
  SetOverwrite on
  File /r "${BUILD_DIR}\*.*"
  SetOutPath "$INSTDIR"

  ; Re-point `current` without ever leaving the install without one: make `current.next` first (a failure here leaves
  ; `current` untouched), then move `current` aside, move `current.next` into place, and put `current` back if that
  ; fails. RMDir (no /r) on a junction removes the link only, never its target.
  RMDir "$INSTDIR\current.next"
  RMDir "$INSTDIR\current.old"
  nsExec::ExecToLog `"$SYSDIR\cmd.exe" /c mklink /J "$INSTDIR\current.next" "$INSTDIR\versions\${VERSION}"`
  Pop $0
  System::Call 'kernel32::GetFileAttributesW(w "$INSTDIR\current.next") i .r1'
  ${If} $0 != 0
  ${OrIf} $1 == -1
    RMDir "$INSTDIR\current.next"
    MessageBox MB_OK|MB_ICONSTOP "${STR_LINK_FAILED}" /SD IDOK
    SetErrorLevel 7
    Abort
  ${EndIf}
  System::Call 'kernel32::GetFileAttributesW(w "$INSTDIR\current") i .r1'
  ClearErrors
  ${If} $1 != -1
    Rename "$INSTDIR\current" "$INSTDIR\current.old"
    ${If} ${Errors}
      RMDir "$INSTDIR\current.next"
      MessageBox MB_OK|MB_ICONSTOP "${STR_LINK_FAILED}" /SD IDOK
      SetErrorLevel 7
      Abort
    ${EndIf}
  ${EndIf}
  ClearErrors
  Rename "$INSTDIR\current.next" "$INSTDIR\current"
  ${If} ${Errors}
    Rename "$INSTDIR\current.old" "$INSTDIR\current"
    RMDir "$INSTDIR\current.next"
    MessageBox MB_OK|MB_ICONSTOP "${STR_LINK_FAILED}" /SD IDOK
    SetErrorLevel 7
    Abort
  ${EndIf}
  RMDir "$INSTDIR\current.old"

  ; Keep the data, the version that was running (the one `current` pointed at, for "Roll back app") and the new one;
  ; remove every other version folder. A repair (the same version again) removes nothing: the rollback copy stays.
  ${If} $PreviousVersion != "${VERSION}"
    FindFirst $0 $1 "$INSTDIR\versions\*.*"
    ${DoWhile} $1 != ""
      ${If} $1 != "."
      ${AndIf} $1 != ".."
      ${AndIf} $1 != "${VERSION}"
      ${AndIf} $1 != $PreviousVersion
        !insertmacro DeleteTreeOrStop "" "$INSTDIR\versions\$1"
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
  Call un.IsRunning
  ${If} $0 == 1
    MessageBox MB_OK|MB_ICONSTOP "${STR_RUNNING_UNINSTALL}" /SD IDOK
    SetErrorLevel 5
    Abort
  ${EndIf}

  ; 1. (refused in un.onInit while ShelfSync runs.)
  ; 2. "Remove my data": the app's own module removes the Credential Manager entries it owns and the data folder, from
  ;    the installed Python and before any program file goes. A failure is reported; the program is still removed.
  ;    --service keeps a throwaway build (SUFFIX) away from the real ShelfSync Credential Manager service.
  ;    Its exit codes: 0 done; 3 not ShelfSync's folder (left alone, nothing touched); 4 ShelfSync runs; 1 part is left.
  ${If} $RemoveData == 1
    StrCpy $3 1
    ${If} ${FileExists} "$INSTDIR\current\python.exe"
      nsExec::ExecToLog `"$INSTDIR\current\python.exe" -m shelfsync.uninstall --remove-data --service ShelfSync${SUFFIX}`
      Pop $3
    ${EndIf}
    Call un.GetDataDir
    ${If} $3 == 3
      MessageBox MB_OK|MB_ICONEXCLAMATION "${STR_DATA_NOT_OURS}$\r$\n$0" /SD IDOK
    ${ElseIf} $3 == 4
      MessageBox MB_OK|MB_ICONSTOP "${STR_RUNNING_UNINSTALL}" /SD IDOK
      SetErrorLevel 5
      Abort
    ${ElseIf} $3 != 0
      MessageBox MB_OK|MB_ICONEXCLAMATION "${STR_DATA_PARTIAL}$\r$\n$0" /SD IDOK
    ${EndIf}
  ${EndIf}

  ; 3. The `current` junction first, itself only (and the updater's `current.next`, if one was left).
  RMDir "$INSTDIR\current"
  RMDir "$INSTDIR\current.next"

  ; 4. versions\: deleted by DeleteTree, which removes every link itself and never follows one (V40).
  !insertmacro DeleteTreeOrStop "un." "$INSTDIR\versions"

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
