"""The backup before a migration, and its restore (SYS-07).

`migrate_with_backup` runs at every start, not only after an update. When migrations are pending **and** the database
already has a version, it takes an online backup (the sqlite3 backup API) to
`backups\\pre-migration-<from>-to-<to>-<UTC>.db`, checks it with `PRAGMA integrity_check`, and records it in
`update\\state.json` **before** migrating. If any migration fails, the backup is restored (and the start-up exits with
code 2 as before). The updater restores the same backup when a new version's start-up fails its health check or the
owner rolls the app back after a database change (04 section 8).

Nothing here deletes a backup. BAK-01 (M2, daily backups) must never delete a pre-migration backup that a kept
version still needs: the one `update\\state.json` names.
"""

import dataclasses
import logging
import os
import shutil
import sqlite3
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from shelfsync.clock import to_iso, utc_now
from shelfsync.db.migrate import DEFAULT_MIGRATIONS_DIR, MigrationError, applied_versions, discover, migrate
from shelfsync.paths import DataPaths, is_plain_file
from shelfsync.update.layout import UpdatePaths
from shelfsync.update.state import BackupRecord, StateStore

_log = logging.getLogger("shelfsync.db")

BACKUP_PREFIX = "pre-migration-"
SNAPSHOT_PREFIX = "pre-rollback-"  # the safety copy taken before a roll back restores an older backup


class BackupError(Exception):
    """A backup couldn't be made or restored. `code`: `backup_failed`, `backup_missing`, `backup_invalid`,
    `restore_failed`. The message never holds database content."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def backup_name(from_schema: int, to_schema: int, now: datetime) -> str:
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    return f"{BACKUP_PREFIX}{from_schema:04d}-to-{to_schema:04d}-{stamp}.db"


def latest_schema(migrations_dir: Path = DEFAULT_MIGRATIONS_DIR) -> int:
    """The highest migration number this version of the app knows."""
    return max(migration.version for migration in discover(migrations_dir))


def snapshot_name(label: str, now: datetime) -> str:
    """`pre-rollback-<version the app is rolling back from>-<UTC>.db`."""
    return f"{SNAPSHOT_PREFIX}{label}-{now.strftime('%Y%m%dT%H%M%SZ')}.db"


def database_schema(path: Path) -> int | None:
    """The highest migration number in the database file, or None if there is no database, it can't be read, or it has
    no migrations. Opened read-only; the app that owns it may be running."""
    if not is_plain_file(path):
        return None
    try:
        connection = sqlite3.connect(f"{path.absolute().as_uri()}?mode=ro", uri=True)
    except sqlite3.Error, ValueError:
        return None
    try:
        versions = applied_versions(connection)
    except sqlite3.Error:
        return None
    finally:
        connection.close()
    return max(versions) if versions else None


def _is_ok(connection: sqlite3.Connection) -> bool:
    rows = connection.execute("PRAGMA integrity_check").fetchall()
    return len(rows) == 1 and rows[0][0] == "ok"


def check_backup(path: Path, expected_schema: int | None = None) -> bool:
    """True if `path` is a plain file that opens read-only, passes `PRAGMA integrity_check` and (when given) whose
    highest migration is `expected_schema`."""
    if not is_plain_file(path):
        return False
    try:
        connection = sqlite3.connect(f"{path.absolute().as_uri()}?mode=ro", uri=True)
    except sqlite3.Error, ValueError:
        return False
    try:
        if not _is_ok(connection):
            return False
        if expected_schema is None:
            return True
        versions = applied_versions(connection)
        return bool(versions) and max(versions) == expected_schema
    except sqlite3.Error:
        return False
    finally:
        connection.close()


def take_backup(
    connection: sqlite3.Connection,
    paths: DataPaths,
    from_schema: int,
    to_schema: int,
    now: Callable[[], datetime] = utc_now,
) -> BackupRecord:
    """An online backup of the open database into backups\\, checked before it is trusted. A copy that fails the check
    is removed and BackupError is raised."""
    moment = now()
    destination = paths.backups / backup_name(from_schema, to_schema, moment)
    _write_checked_copy(connection, destination, from_schema)
    return BackupRecord(str(destination), from_schema, to_schema, to_iso(moment))


def _write_checked_copy(connection: sqlite3.Connection, destination: Path, schema: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        target = sqlite3.connect(destination)
        try:
            with target:
                connection.backup(target)
            target.execute("PRAGMA journal_mode = DELETE")  # one standalone file, no -wal beside it
            healthy = _is_ok(target)
        finally:
            target.close()
    except sqlite3.Error:
        healthy = False
    if not healthy or not check_backup(destination, schema):
        destination.unlink(missing_ok=True)
        raise BackupError("backup_failed")


def take_snapshot(paths: DataPaths, label: str, now: Callable[[], datetime] = utc_now) -> BackupRecord:
    """A checked online copy of the CURRENT database as `backups\\pre-rollback-<label>-<UTC>.db`, taken before a roll
    back restores an older backup, so the roll back can be undone. BackupError if there is no database to copy or the
    copy fails its check; the roll back is then refused."""
    schema = database_schema(paths.database)
    if schema is None:
        raise BackupError("backup_failed")
    moment = now()
    destination = paths.backups / snapshot_name(label, moment)
    try:
        source = sqlite3.connect(paths.database)
    except sqlite3.Error:
        raise BackupError("backup_failed") from None
    try:
        _write_checked_copy(source, destination, schema)
    except sqlite3.Error:
        destination.unlink(missing_ok=True)
        raise BackupError("backup_failed") from None
    finally:
        source.close()
    return BackupRecord(str(destination), schema, schema, to_iso(moment))


def restore_backup(record: BackupRecord, paths: DataPaths) -> None:
    """Put the backup back as the database. No connection to the database may be open (the instance lock is held by
    the caller). The backup must be a plain file inside backups\\ that passes the integrity check and holds the schema
    the record says. The database and its `-wal` and `-shm` files are first moved aside (never deleted before the
    replace has worked), then the verified copy replaces the database in one `os.replace`; if that fails, the old files
    are moved back. Only a backup or a roll-back snapshot made by this app is accepted."""
    source = Path(record.path)
    if source.parent != paths.backups or not source.name.startswith((BACKUP_PREFIX, SNAPSHOT_PREFIX)):
        raise BackupError("backup_invalid")
    if not is_plain_file(source):
        raise BackupError("backup_missing")
    if not check_backup(source, record.from_schema):
        raise BackupError("backup_invalid")
    database = paths.database
    staged = database.with_name(f"{database.name}.restore")
    parts = [database.with_name(database.name + suffix) for suffix in ("", "-wal", "-shm")]
    aside = [part.with_name(part.name + ".aside") for part in parts]
    moved: list[tuple[Path, Path]] = []
    try:
        shutil.copyfile(source, staged)
        if not check_backup(staged, record.from_schema):  # the copy, not just the original
            raise BackupError("backup_invalid")
        for part, away in zip(parts, aside, strict=True):
            away.unlink(missing_ok=True)
            if part.exists():
                os.replace(part, away)
                moved.append((part, away))
        os.replace(staged, database)
    except BackupError:
        _put_back(moved)
        raise
    except OSError:
        _put_back(moved)
        raise BackupError("restore_failed") from None
    finally:
        staged.unlink(missing_ok=True)
    for _, away in moved:
        away.unlink(missing_ok=True)
    _log.info("The database was restored from %s", source.name)


def _put_back(moved: list[tuple[Path, Path]]) -> None:
    """Undo the moves of a restore that failed: the old database and its `-wal` and `-shm` come back."""
    for part, away in moved:
        try:
            os.replace(away, part)
        except OSError:
            _log.error("A file moved aside during a restore could not be put back")


def migrate_with_backup(
    connection: sqlite3.Connection,
    paths: DataPaths,
    migrations_dir: Path = DEFAULT_MIGRATIONS_DIR,
    now: Callable[[], datetime] = utc_now,
) -> list[int]:
    """`migrate`, with the backup described in the module text. Returns the versions applied.

    If a migration fails after the backup was taken, `connection` is closed (the restore needs the file free), the
    backup is restored, and MigrationError is raised as `migrate` does. A failed backup stops the start-up the same
    way, before anything is changed.
    """
    known = {migration.version for migration in discover(migrations_dir)}
    done = applied_versions(connection)
    pending = known - done
    if not pending or not done or (done - known):
        # nothing to do, a new database (nothing worth saving), or a database from a newer version, which
        # `migrate` refuses with its own message before changing anything
        return migrate(connection, migrations_dir)
    try:
        record = take_backup(connection, paths, max(done), max(known), now)
    except BackupError:
        _log.error("The database backup before the migration failed, so the migration was not started")
        raise MigrationError("The database couldn't be backed up before the update, so it was not changed.") from None
    StateStore(UpdatePaths(paths)).update(lambda state: dataclasses.replace(state, backup=record))
    try:
        return migrate(connection, migrations_dir)
    except MigrationError:
        connection.close()
        try:
            restore_backup(record, paths)
        except BackupError as error:
            _log.error("The database could not be restored after the failed migration (%s)", error.code)
            raise MigrationError("The migration failed and the database could not be restored.") from None
        _log.warning("A migration failed; the database was restored from the backup taken before it")
        raise
