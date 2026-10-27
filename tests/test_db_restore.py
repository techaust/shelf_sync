"""BAK-01: the restore command."""

import os
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from shelfsync.db import restore as restore_module
from shelfsync.db.backup import check_backup, latest_schema
from shelfsync.db.connection import connect
from shelfsync.db.daily import DailyBackups, LocalTime, daily_name
from shelfsync.db.migrate import migrate
from shelfsync.db.restore import (
    BAD_NAME,
    DONE,
    EXIT_FAILED,
    EXIT_NO_FOLDER,
    EXIT_OK,
    EXIT_REFUSED,
    EXIT_RUNNING,
    INVALID,
    NEWER,
    NOT_FOUND,
    RUNNING,
    USAGE,
    is_bare_name,
    main,
)
from shelfsync.paths import DataPaths
from shelfsync.tray.instance import FakeInstanceLock
from tests.update_support import data_paths

NOW = datetime(2026, 3, 10, 14, 0, 0, tzinfo=UTC)
UTC_ZONE = LocalTime(
    to_local=lambda moment: moment.replace(tzinfo=None), to_utc=lambda naive: naive.replace(tzinfo=UTC)
)


class Run:
    def __init__(self, tmp_path: Path) -> None:
        self.paths: DataPaths = data_paths(tmp_path)
        connection = connect(self.paths.database)
        migrate(connection)
        connection.execute("INSERT INTO setting (key, value_json) VALUES ('theme', '\"light\"')")
        connection.close()
        self.said: list[str] = []
        self.lock = FakeInstanceLock()

    def go(self, *args: str, lock: FakeInstanceLock | None = None) -> int:
        return main(list(args), paths=self.paths, lock=lock or self.lock, out=self.said.append, now=lambda: NOW)

    def daily(self) -> Path:
        scheduler = DailyBackups(self.paths, lambda: connect(self.paths.database), lambda: NOW, UTC_ZONE)
        assert scheduler.run_once()
        return self.paths.backups / daily_name(NOW)

    def theme(self) -> str:
        connection = connect(self.paths.database)
        try:
            return str(connection.execute("SELECT value_json FROM setting WHERE key = 'theme'").fetchone()[0])
        finally:
            connection.close()

    def change_theme(self, value: str) -> None:
        connection = connect(self.paths.database)
        connection.execute("UPDATE setting SET value_json = ? WHERE key = 'theme'", (f'"{value}"',))
        connection.close()


@pytest.fixture
def run(tmp_path: Path) -> Run:
    return Run(tmp_path)


def test_a_successful_restore_takes_a_snapshot_first_and_passes_the_check(run: Run) -> None:
    backup = run.daily()
    run.change_theme("dark")
    assert run.go(backup.name) == EXIT_OK
    assert run.theme() == '"light"'  # the backup's data is back
    assert check_backup(run.paths.database, latest_schema())
    snapshots = list(run.paths.backups.glob("pre-rollback-restore-*.db"))
    assert len(snapshots) == 1
    assert check_backup(snapshots[0])
    kept = sqlite3.connect(snapshots[0])
    assert kept.execute("SELECT value_json FROM setting WHERE key = 'theme'").fetchone()[0] == '"dark"'  # undo possible
    kept.close()
    assert run.said == [DONE.format(name=backup.name, safety=snapshots[0].name)]
    assert not run.lock._held  # the lock was let go
    assert not list(run.paths.root.glob("shelfsync.db.*"))  # no -wal, -shm, .restore or .aside left


def test_a_pre_migration_and_a_pre_rollback_copy_can_be_restored_too(run: Run) -> None:
    backup = run.daily()
    for prefix in ("pre-migration-0001-to-0002-20260101T000000Z.db", "pre-rollback-0.1.0-20260101T000000Z.db"):
        shutil.copy(backup, run.paths.backups / prefix)
        assert run.go(prefix) == EXIT_OK, run.said


def test_it_refuses_while_shelfsync_is_running_and_changes_nothing(run: Run) -> None:
    backup = run.daily()
    run.change_theme("dark")
    other = FakeInstanceLock(run.lock._taken)
    assert run.lock.acquire()  # "ShelfSync" is running
    assert run.go(backup.name, lock=other) == EXIT_RUNNING
    assert run.said == [RUNNING]
    assert run.theme() == '"dark"'
    assert not list(run.paths.backups.glob("pre-rollback-*"))


def test_a_lock_that_cannot_be_used_is_a_data_folder_problem(run: Run) -> None:
    class Broken(FakeInstanceLock):
        def acquire(self) -> bool:
            raise OSError("no")

    assert run.go("daily-20260310T140000Z.db", lock=Broken()) == EXIT_NO_FOLDER


@pytest.mark.parametrize(
    "name",
    [
        "..\\shelfsync.db",
        "../shelfsync.db",
        "..",
        ".",
        "",
        "backups\\daily-20260310T140000Z.db",
        "backups/daily-20260310T140000Z.db",
        "C:\\x\\daily-20260310T140000Z.db",
        "C:daily-20260310T140000Z.db",
        "daily-20260310T140000Z.db:stream",
        "daily-20260310T140000Z.db.",
        " daily-20260310T140000Z.db",
        "shelfsync.db",
        "other-20260310T140000Z.db",
        "daily-20260310T140000Z.txt",
        "pre-migration*.db",
    ],
)
def test_names_that_are_not_a_bare_backup_file_name_are_refused(run: Run, name: str) -> None:
    run.daily()
    before = run.paths.database.read_bytes()
    assert run.go(name) == EXIT_REFUSED
    assert run.said in ([BAD_NAME], [USAGE])
    assert run.paths.database.read_bytes() == before
    assert not list(run.paths.backups.glob("pre-rollback-*"))


def test_an_absolute_path_to_a_real_backup_is_refused(run: Run) -> None:
    backup = run.daily()
    assert run.go(str(backup)) == EXIT_REFUSED
    assert run.said == [BAD_NAME]


def test_a_missing_file_is_refused(run: Run) -> None:
    assert run.go("daily-20260310T140000Z.db") == EXIT_REFUSED
    assert run.said == [NOT_FOUND]


def test_a_link_in_place_of_a_backup_is_refused(run: Run, tmp_path: Path) -> None:
    backup = run.daily()
    outside = tmp_path / "outside.db"
    shutil.copy(backup, outside)
    link = run.paths.backups / "daily-20250101T000000Z.db"
    try:
        os.symlink(outside, link)
    except OSError, NotImplementedError:
        pytest.skip("this PC can't make a symlink without extra privilege")
    assert run.go(link.name) == EXIT_REFUSED
    assert run.said == [NOT_FOUND]


def test_a_file_with_two_names_is_refused(run: Run, tmp_path: Path) -> None:
    backup = run.daily()
    os.link(backup, tmp_path / "second-name.db")
    assert run.go(backup.name) == EXIT_REFUSED
    assert run.said == [NOT_FOUND]


def test_a_backup_from_a_newer_schema_is_refused(run: Run) -> None:
    backup = run.daily()
    connection = sqlite3.connect(backup)
    connection.execute("INSERT INTO schema_migration VALUES (999, '2026-01-01T00:00:00.000000Z')")
    connection.commit()
    connection.close()
    before = run.paths.database.read_bytes()
    assert run.go(backup.name) == EXIT_REFUSED
    assert run.said == [NEWER]
    assert run.paths.database.read_bytes() == before
    assert not list(run.paths.backups.glob("pre-rollback-*"))


def test_a_damaged_backup_is_refused_and_nothing_changes(run: Run) -> None:
    damaged = run.paths.backups / "daily-20260101T000000Z.db"
    damaged.write_bytes(b"not a database" * 50)
    before = run.paths.database.read_bytes()
    assert run.go(damaged.name) == EXIT_REFUSED
    assert run.said == [INVALID]
    assert run.paths.database.read_bytes() == before


def test_a_backup_that_fails_its_check_after_the_snapshot_leaves_the_database_alone(
    run: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    backup = run.daily()
    run.change_theme("dark")
    monkeypatch.setattr(
        restore_module,
        "restore_backup",
        lambda record, paths: (_ for _ in ()).throw(restore_module.BackupError("restore_failed")),
    )
    assert run.go(backup.name) == EXIT_FAILED
    assert run.theme() == '"dark"'


def test_with_no_database_there_is_nothing_to_save_first(run: Run) -> None:
    backup = run.daily()
    run.paths.database.unlink()
    for suffix in ("-wal", "-shm"):
        run.paths.database.with_name(run.paths.database.name + suffix).unlink(missing_ok=True)
    assert run.go(backup.name) == EXIT_OK
    assert run.theme() == '"light"'
    assert not list(run.paths.backups.glob("pre-rollback-*"))


def test_a_damaged_current_database_is_kept_as_a_plain_copy_and_replaced(run: Run) -> None:
    backup = run.daily()
    run.paths.database.write_bytes(b"garbage" * 100)
    for suffix in ("-wal", "-shm"):
        run.paths.database.with_name(run.paths.database.name + suffix).unlink(missing_ok=True)
    assert run.go(backup.name) == EXIT_OK
    assert run.theme() == '"light"'
    kept = list(run.paths.backups.glob("pre-rollback-damaged-*.db"))
    assert len(kept) == 1
    assert kept[0].read_bytes() == b"garbage" * 100


def test_list_shows_the_restorable_files_and_ignores_the_rest(run: Run) -> None:
    backup = run.daily()
    (run.paths.backups / "notes.txt").write_text("x")
    (run.paths.backups / "daily-20260310T140000Z.db.part").write_bytes(b"x")
    assert run.go("--list") == EXIT_OK
    assert len(run.said) == 1
    assert run.said[0].startswith(backup.name)
    assert f"schema {latest_schema()}" in run.said[0]
    assert "notes" not in run.said[0]
    assert "part" not in run.said[0]


def test_list_works_while_shelfsync_runs_and_says_so_when_empty(run: Run) -> None:
    assert run.lock.acquire()
    assert run.go("--list", lock=FakeInstanceLock(run.lock._taken)) == EXIT_OK
    assert run.said == [restore_module.NONE_LISTED]


@pytest.mark.parametrize("args", [[], ["a", "b"], ["--list", "x"]])
def test_wrong_use_prints_the_usage(run: Run, args: list[str]) -> None:
    assert run.go(*args) == EXIT_REFUSED
    assert run.said == [USAGE]


def test_help_prints_the_usage_and_succeeds(run: Run) -> None:
    assert run.go("--help") == EXIT_OK
    assert run.said == [USAGE]


def test_is_bare_name() -> None:
    assert is_bare_name("daily-20260310T140000Z.db")
    assert not is_bare_name("a/b.db")
    assert not is_bare_name("a\\b.db")
    assert not is_bare_name("..")
    assert not is_bare_name("a.db.")
    assert not is_bare_name("a\x00.db")


def test_an_unknown_data_folder_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SHELFSYNC_DATA_DIR", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    said: list[str] = []
    assert main(["--list"], out=said.append) == EXIT_NO_FOLDER


def test_the_module_runs_as_a_command_and_lists(run: Run) -> None:
    """`python -m shelfsync.db.restore --list` with a throwaway data folder (no lock is taken to list)."""
    import subprocess
    import sys

    backup = run.daily()
    env = {
        **os.environ,
        "SHELFSYNC_DATA_DIR": str(run.paths.root),
        "PYTHONPATH": str(Path(restore_module.__file__).parents[2]),  # the source layout, as in development
    }
    result = subprocess.run(
        [sys.executable, "-m", "shelfsync.db.restore", "--list"], env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert backup.name in result.stdout
