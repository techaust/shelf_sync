# Install ShelfSync and open it the first time

ShelfSync installs for your Windows account only: no admin rights, no changes for other accounts. Program files go to `%LOCALAPPDATA%\Programs\ShelfSync`, your data to `%LOCALAPPDATA%\ShelfSync`.

## 1. Download and check the installer
1. Open https://github.com/techaust/shelf_sync/releases/latest and click `ShelfSync-Setup-<X.Y.Z>.exe` to download it. Also click `manifest.json` and `manifest.json.sig`.
2. **Check it before running it** ([06 §6](../06-security.md)): nothing ShelfSync controls checks a hand-downloaded installer.
   - **On your own account** (it has the repo), in Windows PowerShell:
     ```powershell
     cd "D:\BUSINESS\3. CHILD PROJECTS\1. GPL PROJECTS\OTHER ASSETS\SOFTWARE\shelf_sync"
     ```
     ```powershell
     $env:UV_PYTHON_DOWNLOADS='never'; $env:PYTHONPATH='backend'; uv run python tools/release/verify_setup.py "$env:USERPROFILE\Downloads\manifest.json" "$env:USERPROFILE\Downloads\manifest.json.sig" "$env:USERPROFILE\Downloads\ShelfSync-Setup-<X.Y.Z>.exe"
     ```
     It must print a line starting **OK:** ("the signature is valid and the installer is exactly ShelfSync <X.Y.Z>"). If it prints **FAILED** or says **Do NOT run the installer**, stop and tell Claude.
   - **On the clean test account** (no repo): open `manifest.json` on the release page and find the `sha256` under `ShelfSync-Setup-<X.Y.Z>.exe`. Then in Windows PowerShell:
     ```powershell
     Get-FileHash "$env:USERPROFILE\Downloads\ShelfSync-Setup-<X.Y.Z>.exe" -Algorithm SHA256
     ```
     The **Hash** must equal that value (capital letters don't matter).

## 2. Run it
1. Double-click the Setup in **Downloads**.
2. **Windows protected your PC** (SmartScreen) appears because the installer isn't code-signed (02 §6; a paid certificate would remove it, **optional, not used**). Click **More info**, check the app name says `ShelfSync-Setup-<X.Y.Z>.exe`, then **Run anyway**.
3. If **Smart App Control** blocks it with no "Run anyway", stop: note the exact message for Claude. Don't change the setting.
4. Follow the pages. On the last page leave **Open ShelfSync** ticked and click **Finish**.

## 3. First run
- ShelfSync opens a browser tab already signed in, and a ShelfSync icon appears in the tray (click **^** at the bottom right if it's hidden).
- Later, open it from the tray icon, the desktop icon or the Start menu: each opens a signed-in tab.
- With **Start with Windows** on (Settings › App), ShelfSync starts in the tray when you sign in, without opening a tab.

If it doesn't open, see [troubleshooting.md](troubleshooting.md).
