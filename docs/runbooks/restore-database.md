# Restore the database from a backup

ShelfSync keeps backups of its database in `%LOCALAPPDATA%\ShelfSync\backups` (BAK-01):
- `daily-<date>T<time>Z.db`: one a day at 02:00 (or at the next start if the PC was off); the newest 7 are kept unless you change **Settings › Backup › Database backups to keep** (1 to 30);
- `pre-migration-…db`: taken just before an update changed the database; never deleted automatically;
- `pre-rollback-…db`: the copy taken just before a restore or a roll back; never deleted automatically.

The times in the names are UTC (India Standard Time is 5 h 30 min ahead).

Restoring replaces the current database with the backup. ShelfSync first saves the current one as a `pre-rollback-restore-…db`, so a restore can be undone by restoring that file. If the current database is too damaged to save that way, it's kept as a plain copy, `pre-rollback-damaged-…db`: that one can't be restored, but nothing is lost.

The same steps are in the app: **Settings › Backup › How to restore a backup** opens the Help guide **Restore the database from a backup**, with both commands and a **Copy** button.

**Run these in Windows PowerShell, outside the Claude app.** Each block is one command.

1. Quit ShelfSync: right-click its tray icon › **Quit**.
2. List the backups:
   ```powershell
   & "$env:LOCALAPPDATA\Programs\ShelfSync\current\python.exe" -I -m shelfsync.db.restore --list
   ```
3. Pick one name from the list (newest first) and restore it. Replace `daily-20261028T020000Z.db` with that name:
   ```powershell
   & "$env:LOCALAPPDATA\Programs\ShelfSync\current\python.exe" -I -m shelfsync.db.restore daily-20261028T020000Z.db
   ```
4. It must end with "Done. The database was restored from …". Then start ShelfSync from the Start menu.

If it says ShelfSync is running, quit it from the tray icon and run step 3 again. Any other message says what to do, and "Nothing was changed" means your database is as it was. If it says the reason is in the log, send Claude the last 30 lines of `%LOCALAPPDATA%\ShelfSync\logs\shelfsync.log`.

## Once, for the M2 exit test
Run step 3 once **with ShelfSync still running**: it must say "ShelfSync is running…" and change nothing. Then quit ShelfSync and run it again: it must restore. Tell Claude both results.
