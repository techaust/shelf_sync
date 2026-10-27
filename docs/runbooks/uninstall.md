# Uninstall ShelfSync

1. Quit ShelfSync: right-click its tray icon › **Quit**. (The uninstaller refuses while it runs.)
2. Press **Windows key**, type `Installed apps`, open it.
3. Find **ShelfSync**, click **⋯ › Uninstall**, confirm.
4. On the **Remove my data** page:
   - leave the box **unticked** to keep your database, backups, logs and stored sign-in token, so a later install picks up where you left off;
   - tick it to remove them too. **This can't be undone.**
5. Click **Uninstall**, then **Close**. If a notice says something couldn't be removed, it names what and where; follow its line.

## Check it's gone (Windows PowerShell)
```powershell
Test-Path "$env:LOCALAPPDATA\Programs\ShelfSync"
```
It must print **False**.
```powershell
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\ShelfSync"
```
It must say it **was unable to find** the key.

With **Remove my data** ticked, this must print **False** too:
```powershell
Test-Path "$env:LOCALAPPDATA\ShelfSync"
```
