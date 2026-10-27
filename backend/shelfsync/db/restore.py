"""The restore command (BAK-01): `python -m shelfsync.db.restore [--list | <file name>]`.

Run from a terminal while ShelfSync is closed (the runbook `restore-database.md` has the click-by-click steps).

    --list        show the backups that can be restored, newest first (ShelfSync may be running)
    <file name>   put that backup back as the database

Rules, in this order:
1. It refuses while ShelfSync is running (the single-instance lock is taken for the whole restore).
2. The name is a bare file name: no folder, no `..`, no drive. The file must be directly inside `backups\\`, a plain
   file (not a link), named `daily-`, `pre-migration-` or `pre-rollback-` ... `.db`.
3. A backup made by a newer ShelfSync (a schema this version doesn't know) is refused.
4. The current database is copied first, as `pre-rollback-restore-<UTC>.db`, so the restore can be undone. A database
   too damaged to copy that way is kept as a plain file copy, `pre-rollback-damaged-<UTC>.db` (it can't be restored
   again, but nothing is lost).
5. `restore_backup` does the replace: the copy is checked (`integrity_check` and its schema) before the database is
   touched, and the old files are only deleted once the replace has worked.

Exit codes: 0 done (or the list shown), 1 the command was used wrongly or the file was refused, 2 ShelfSync is running,
3 the restore failed (the database is as it was), 4 the data folder or its lock couldn't be used.
"""

import shutil
import sqlite3
import sys
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path

from shelfsync.clock import to_iso, utc_now
from shelfsync.db.backup import (
    RESTORABLE_PREFIXES,
    BackupError,
    database_schema,
    latest_schema,
    restore_backup,
    take_snapshot,
)
from shelfsync.paths import DataPaths, is_plain_file, resolve_data_paths
from shelfsync.tray.instance import InstanceLock, default_instance_lock
from shelfsync.update.state import BackupRecord

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_RUNNING = 2
EXIT_FAILED = 3
EXIT_NO_FOLDER = 4

# Proposed wording (docs/13 section 3 gets it from the lead). Plain, no file content, no paths that hold secrets.
USAGE = (
    "Usage: python -m shelfsync.db.restore --list\n"
    "       python -m shelfsync.db.restore <backup file name>\n"
    r"The backups are in %LOCALAPPDATA%\ShelfSync\backups. Close ShelfSync before restoring."
)
RUNNING = "ShelfSync is running. Quit it from the tray icon, then run this again. Nothing was changed."
NO_FOLDER = "ShelfSync couldn't use its data folder, so nothing was changed."
BAD_NAME = (
    "That isn't a backup file name. Give only the file name, for example daily-20261028T020000Z.db, "
    "with no folder. Use --list to see the backups. Nothing was changed."
)
NOT_FOUND = "There is no such backup in the backups folder. Use --list to see them. Nothing was changed."
NEWER = "That backup was made by a newer ShelfSync than this one, so it can't be restored here. Nothing was changed."
INVALID = "That backup is damaged or isn't a ShelfSync database, so it was not restored. Nothing was changed."
SNAPSHOT_FAILED = "The current database couldn't be saved first, so nothing was changed."
FAILED = "The restore failed. Your database is as it was before. The reason is in the log."
NONE_LISTED = "There are no backups to restore yet."
DONE = "Done. The database was restored from {name}. The copy of the database from before is {safety}. Start ShelfSync."
DONE_NO_SAFETY = "Done. The database was restored from {name}. There was no database to save first. Start ShelfSync."


def is_bare_name(name: str) -> bool:
    """A single file name: no folder part, no drive or stream (`:`), no `..`, not hidden by a trailing dot or space."""
    if not name or name in (".", "..") or name != name.strip() or name.endswith("."):
        return False
    if any(char in name for char in '/\\:*?"<>|') or any(ord(char) < 32 for char in name):
        return False
    return Path(name).name == name


def restorable_files(paths: DataPaths) -> list[Path]:
    """The plain files in backups\\ that the restore accepts by name, newest first."""
    try:
        entries = list(paths.backups.iterdir())
    except OSError:
        return []
    chosen = [
        entry
        for entry in entries
        if entry.name.startswith(RESTORABLE_PREFIXES) and entry.name.endswith(".db") and is_plain_file(entry)
    ]
    chosen.sort(key=lambda entry: (entry.stat().st_mtime, entry.name), reverse=True)
    return chosen


def _list(paths: DataPaths, out: Callable[[str], None]) -> int:
    files = restorable_files(paths)
    if not files:
        out(NONE_LISTED)
        return EXIT_OK
    for entry in files:
        schema = database_schema(entry)
        known = f"schema {schema}" if schema is not None else "not readable"
        out(f"{entry.name}  ({known}, {entry.stat().st_size // 1024} KB)")
    return EXIT_OK


def _safety_copy(paths: DataPaths, moment: datetime) -> str | None:
    """A copy of the current database, so the restore can be undone. Its name, or None if there is no database.
    BackupError if the copy can't be made."""
    database = paths.database
    if not database.exists():
        return None
    try:
        return Path(take_snapshot(paths, "restore", lambda: moment).path).name
    except BackupError:
        pass
    # Unreadable as a database (the very case a restore is for): keep the raw file, so nothing is lost.
    stamp = moment.strftime("%Y%m%dT%H%M%SZ")
    target = paths.backups / f"pre-rollback-damaged-{stamp}.db"
    try:
        shutil.copyfile(database, target)
    except OSError:
        raise BackupError("backup_failed") from None
    return target.name


def restore_command(
    name: str,
    paths: DataPaths,
    out: Callable[[str], None],
    now: Callable[[], datetime] = utc_now,
) -> int:
    """Steps 2 to 5 of the module text, with the lock already held."""
    if not is_bare_name(name) or not name.startswith(RESTORABLE_PREFIXES) or not name.endswith(".db"):
        out(BAD_NAME)
        return EXIT_REFUSED
    source = paths.backups / name
    if not is_plain_file(source):
        out(NOT_FOUND)
        return EXIT_REFUSED
    schema = database_schema(source)
    if schema is None:
        out(INVALID)
        return EXIT_REFUSED
    if schema > latest_schema():
        out(NEWER)
        return EXIT_REFUSED
    moment = now()
    try:
        safety = _safety_copy(paths, moment)
    except BackupError, sqlite3.Error:
        out(SNAPSHOT_FAILED)
        return EXIT_FAILED
    try:
        restore_backup(BackupRecord(str(source), schema, schema, to_iso(moment)), paths)
    except BackupError as error:
        out(INVALID if error.code in ("backup_invalid", "backup_missing") else FAILED)
        return EXIT_REFUSED if error.code in ("backup_invalid", "backup_missing") else EXIT_FAILED
    out(DONE.format(name=name, safety=safety) if safety is not None else DONE_NO_SAFETY.format(name=name))
    return EXIT_OK


def main(
    argv: Sequence[str] | None = None,
    *,
    paths: DataPaths | None = None,
    lock: InstanceLock | None = None,
    out: Callable[[str], None] = print,
    now: Callable[[], datetime] = utc_now,
) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1 or args[0] in ("-h", "--help"):
        out(USAGE)
        return EXIT_OK if args in (["-h"], ["--help"]) else EXIT_REFUSED
    try:
        data = paths if paths is not None else resolve_data_paths()
    except RuntimeError:
        out(NO_FOLDER)
        return EXIT_NO_FOLDER
    if args[0] == "--list":
        return _list(data, out)
    try:
        instance = lock if lock is not None else default_instance_lock(data)
        if not instance.acquire():
            out(RUNNING)
            return EXIT_RUNNING
    except OSError:
        out(NO_FOLDER)
        return EXIT_NO_FOLDER
    try:
        return restore_command(args[0], data, out, now)
    finally:
        instance.release()


if __name__ == "__main__":
    raise SystemExit(main())
