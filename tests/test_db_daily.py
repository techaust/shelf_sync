"""BAK-01: the daily database backup, its schedule and its retention."""

import os
import sqlite3
import subprocess
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from shelfsync.db import daily as daily_module
from shelfsync.db.backup import BackupError, check_backup
from shelfsync.db.connection import connect
from shelfsync.db.daily import (
    DailyBackups,
    LocalTime,
    daily_backups,
    daily_name,
    latest_slot,
    name_time,
    next_slot,
    prune,
)
from shelfsync.db.migrate import migrate
from shelfsync.db.settings import set_setting
from shelfsync.paths import DataPaths
from shelfsync.update.layout import UpdatePaths
from shelfsync.update.state import BackupRecord, State, StateStore
from tests.update_support import data_paths

UTC_ZONE = LocalTime(
    to_local=lambda moment: moment.replace(tzinfo=None), to_utc=lambda naive: naive.replace(tzinfo=UTC)
)


class Clock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now


def at(day: int, hour: int = 2, minute: int = 0, second: int = 30, month: int = 3) -> datetime:
    return datetime(2026, month, day, hour, minute, second, tzinfo=UTC)


class Rig:
    def __init__(self, tmp_path: Path, start: datetime, local: LocalTime = UTC_ZONE) -> None:
        self.paths = data_paths(tmp_path)
        setup = connect(self.paths.database)
        migrate(setup)
        setup.close()
        self.clock = Clock(start)
        self.daily = DailyBackups(self.paths, lambda: connect(self.paths.database), self.clock, local, interval=0.05)

    def names(self) -> list[str]:
        return sorted(entry.name for entry in self.paths.backups.iterdir())

    def keep(self, count: int) -> None:
        connection = connect(self.paths.database)
        try:
            set_setting(connection, "db_backups_kept", count)
        finally:
            connection.close()


def plant(paths: DataPaths, name: str, content: bytes = b"x") -> Path:
    target = paths.backups / name
    target.write_bytes(content)
    return target


def test_eight_days_leave_exactly_seven_daily_files_and_a_restored_copy_passes_the_check(tmp_path: Path) -> None:
    """BAK-01 Accept: seven files after eight days; a restore from one passes the integrity check."""
    rig = Rig(tmp_path, at(1))
    for day in range(1, 9):
        rig.clock.now = at(day)
        assert rig.daily.is_due()
        assert rig.daily.run_once()
        assert not rig.daily.is_due()  # made for this slot: not again until the next 02:00
    stamps = [name for name in rig.names() if name.startswith("daily-")]
    assert len(stamps) == 7
    assert stamps[0] == daily_name(at(2))  # the oldest one, day 1, is gone
    assert not (rig.paths.backups / daily_name(at(1))).exists()
    assert all(check_backup(rig.paths.backups / name) for name in stamps)
    assert not [name for name in rig.names() if name.endswith(".part")]


def test_a_missed_run_is_caught_up_at_the_next_check(tmp_path: Path) -> None:
    """BAK-01: the PC was off at 02:00; the first check after the start or the wake makes the backup."""
    rig = Rig(tmp_path, at(1))
    assert rig.daily.run_once()
    rig.clock.now = at(2, 1, 59, 59)
    assert not rig.daily.is_due()
    rig.clock.now = at(2, 2, 0, 0)
    assert rig.daily.is_due()
    rig.clock.now = at(2, 9, 0, 0)  # woke up at 09:00
    assert rig.daily.is_due()
    assert rig.daily.run_once()
    assert not rig.daily.is_due()
    rig.clock.now = at(3, 1, 0, 0)
    assert not rig.daily.is_due()
    rig.clock.now = at(3, 2, 0, 1)
    assert rig.daily.is_due()


def test_a_database_with_no_daily_backup_is_due_at_once(tmp_path: Path) -> None:
    rig = Rig(tmp_path, at(1, 14))
    assert rig.daily.is_due()
    assert rig.daily.last_backup() is None
    assert rig.daily.next_run() == rig.clock.now


def test_next_run_is_the_next_02_00_local_when_nothing_is_due(tmp_path: Path) -> None:
    rig = Rig(tmp_path, at(1, 14))
    assert rig.daily.run_once()
    assert rig.daily.next_run() == datetime(2026, 3, 2, 2, 0, tzinfo=UTC)


# A fake New York: UTC-4 (daylight time) before 2026-11-01 06:00 UTC, UTC-5 after it: the clocks go back.
FALL = datetime(2026, 11, 1, 6, 0, tzinfo=UTC)


def _fake_to_local(moment: datetime) -> datetime:
    return (moment + timedelta(hours=-4 if moment < FALL else -5)).replace(tzinfo=None)


def _fake_to_utc(naive: datetime) -> datetime:
    summer = (naive + timedelta(hours=4)).replace(tzinfo=UTC)
    return summer if summer < FALL else (naive + timedelta(hours=5)).replace(tzinfo=UTC)


FAKE_NEW_YORK = LocalTime(_fake_to_local, _fake_to_utc)


def test_the_slot_follows_local_time_across_a_daylight_saving_change() -> None:
    """BAK-01: 02:00 local is 06:00 UTC before the clocks go back and 07:00 UTC after."""
    assert latest_slot(datetime(2026, 10, 31, 12, 0, tzinfo=UTC), FAKE_NEW_YORK) == datetime(
        2026, 10, 31, 6, 0, tzinfo=UTC
    )
    assert next_slot(datetime(2026, 10, 31, 12, 0, tzinfo=UTC), FAKE_NEW_YORK) == datetime(
        2026, 11, 1, 7, 0, tzinfo=UTC
    )
    assert latest_slot(datetime(2026, 11, 1, 12, 0, tzinfo=UTC), FAKE_NEW_YORK) == datetime(
        2026, 11, 1, 7, 0, tzinfo=UTC
    )
    assert next_slot(datetime(2026, 11, 1, 12, 0, tzinfo=UTC), FAKE_NEW_YORK) == datetime(2026, 11, 2, 7, 0, tzinfo=UTC)


def test_a_daylight_saving_change_neither_skips_nor_repeats_a_backup(tmp_path: Path) -> None:
    rig = Rig(tmp_path, datetime(2026, 10, 31, 6, 0, 10, tzinfo=UTC), FAKE_NEW_YORK)
    assert rig.daily.run_once()  # 02:00:10 EDT
    rig.clock.now = datetime(2026, 11, 1, 6, 59, 0, tzinfo=UTC)  # 01:59 EST, the repeated hour: still yesterday's slot
    assert not rig.daily.is_due()
    rig.clock.now = datetime(2026, 11, 1, 7, 0, 0, tzinfo=UTC)  # 02:00 EST
    assert rig.daily.is_due()
    assert rig.daily.run_once()
    rig.clock.now = datetime(2026, 11, 2, 6, 59, 0, tzinfo=UTC)  # 01:59 EST next day
    assert not rig.daily.is_due()
    rig.clock.now = datetime(2026, 11, 2, 7, 0, 0, tzinfo=UTC)
    assert rig.daily.is_due()


def test_the_default_local_time_is_the_system_zone() -> None:
    """The real clock path runs (`astimezone()`): a slot is never in the future or more than 26 hours old."""
    now = datetime.now(UTC)
    slot = latest_slot(now, LocalTime())
    assert slot <= now
    assert now - slot < timedelta(hours=26)
    assert next_slot(now, LocalTime()) > now


def test_names_hold_the_utc_time_and_only_exact_names_count() -> None:
    moment = datetime(2026, 3, 4, 2, 0, 5, tzinfo=UTC)
    assert daily_name(moment) == "daily-20260304T020005Z.db"
    assert name_time("daily-20260304T020005Z.db") == moment
    for foreign in (
        "daily-20260304T020005Z.db.part",
        "daily-20260304T020005Z.db.bak",
        "daily-20261304T020005Z.db",  # month 13
        "daily-2026030T020005Z.db",
        "Daily-20260304T020005Z.db",
        "xdaily-20260304T020005Z.db",
        "daily-20260304T020005Z.db ",
        "pre-migration-0001-to-0002-20260304T020005Z.db",
    ):
        assert name_time(foreign) is None, foreign


# ---- retention ----------------------------------------------------------------------------------------------------


def _link(link: Path, target: Path) -> bool:
    """A symlink if this PC lets the test make one, else a Windows junction; False if neither can be made."""
    try:
        os.symlink(target, link, target_is_directory=target.is_dir())
        return True
    except OSError, NotImplementedError:
        pass
    if os.name == "nt" and target.is_dir():
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, check=False)
        return result.returncode == 0
    return False


def test_retention_deletes_only_plain_daily_files_beyond_the_newest_kept(tmp_path: Path) -> None:
    """BAK-01: pre-migration, pre-rollback, the file state.json names, links and foreign names all survive."""
    rig = Rig(tmp_path, at(20))
    rig.keep(2)
    backups = rig.paths.backups
    old = [plant(rig.paths, daily_name(at(day))) for day in (1, 2, 3)]
    premigration = plant(rig.paths, "pre-migration-0001-to-0002-20200101T000000Z.db")
    prerollback = plant(rig.paths, "pre-rollback-0.1.0-20200101T000000Z.db")
    named = plant(rig.paths, "daily-20190101T000000Z.db")  # old enough to go, but state.json names it
    StateStore(UpdatePaths(rig.paths)).save(State(backup=BackupRecord(str(named), 1, 2, "2026-03-01T00:00:00Z")))
    foreign = [
        plant(rig.paths, "daily-notes.db"),
        plant(rig.paths, "daily-20200101T000000Z.db.bak"),
        plant(rig.paths, "other.db"),
        plant(rig.paths, "daily-20201301T000000Z.db"),  # not a real date
    ]
    linked: list[Path] = []
    target_file = tmp_path / "outside.db"
    target_file.write_bytes(b"precious")
    file_link = backups / "daily-20180101T000000Z.db"
    if _link(file_link, target_file):
        linked.append(file_link)
    folder = tmp_path / "outside-folder"
    folder.mkdir()
    (folder / "keep.txt").write_text("kept")
    folder_link = backups / "daily-20180102T000000Z.db"
    if _link(folder_link, folder):
        linked.append(folder_link)
    hard = backups / "daily-20180103T000000Z.db"
    shared = tmp_path / "shared.db"
    shared.write_bytes(b"shared")
    os.link(shared, hard)  # two names for one file: never touched (`is_plain_file`)
    assert rig.daily.run_once()
    newest = rig.paths.backups / daily_name(at(20))
    assert newest.exists()
    assert [path.exists() for path in old] == [False, False, True]  # kept=2: the new one and the newest old one
    assert not (backups / daily_name(at(20))).is_symlink()
    for survivor in [premigration, prerollback, named, hard, *foreign, *linked]:
        assert os.path.lexists(survivor), survivor.name
    assert target_file.read_bytes() == b"precious"
    assert (folder / "keep.txt").read_text() == "kept"
    assert len(daily_backups(rig.paths)) == 3  # the two kept, and `named`, which state.json protects
    if not linked:
        pytest.skip("this PC can make neither a symlink nor a junction, so no link was planted")


def test_retention_by_the_resolved_path_of_what_state_json_names(tmp_path: Path) -> None:
    paths = data_paths(tmp_path)
    protected = plant(paths, "daily-20190101T000000Z.db")
    newer = [plant(paths, daily_name(at(day))) for day in (1, 2)]
    # state.json names the file through a different spelling of the same path
    spelled = paths.backups / ".." / "backups" / protected.name
    StateStore(UpdatePaths(paths)).save(State(backup=BackupRecord(str(spelled), 1, 2, "2026-03-01T00:00:00Z")))
    assert prune(paths, 1) == [newer[0].name]
    assert protected.exists()
    assert not newer[0].exists()
    assert newer[1].exists()


def test_a_failed_backup_prunes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """BAK-01: retention runs only after a new backup passed its check."""
    rig = Rig(tmp_path, at(20))
    rig.keep(1)
    files = [plant(rig.paths, daily_name(at(day))) for day in (1, 2, 3)]

    def fails(connection: sqlite3.Connection, destination: Path, schema: int) -> None:
        destination.write_bytes(b"half")
        raise BackupError("backup_failed")

    monkeypatch.setattr(daily_module, "write_checked_copy", fails)
    assert rig.daily.run_once() is False
    assert all(path.exists() for path in files)
    assert not [name for name in rig.names() if name.endswith(".part")]
    assert len(daily_backups(rig.paths)) == 3


def test_a_failure_is_retried_at_the_next_due_time_not_every_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    rig = Rig(tmp_path, at(20))
    calls: list[int] = []

    def fails(connection: sqlite3.Connection, destination: Path, schema: int) -> None:
        calls.append(1)
        raise BackupError("backup_failed")

    monkeypatch.setattr(daily_module, "write_checked_copy", fails)
    with caplog.at_level("ERROR", logger="shelfsync.db"):
        assert rig.daily.run_once() is False
    assert "backup_failed" in caplog.text
    assert not rig.daily.is_due()  # not retried at the next minute
    rig.clock.now = at(20, 9)
    assert not rig.daily.is_due()
    rig.clock.now = at(21, 2, 0, 1)  # the next 02:00
    assert rig.daily.is_due()
    monkeypatch.undo()
    assert rig.daily.run_once()
    assert len(calls) == 1


def test_a_database_that_cannot_be_opened_fails_softly(tmp_path: Path) -> None:
    paths = data_paths(tmp_path)

    def broken() -> sqlite3.Connection:
        raise sqlite3.OperationalError("unable to open")

    daily = DailyBackups(paths, broken, Clock(at(1)), UTC_ZONE)
    assert daily.run_once() is False
    assert daily_backups(paths) == []


def test_lowering_the_setting_prunes_at_once(tmp_path: Path) -> None:
    rig = Rig(tmp_path, at(20))
    files = [plant(rig.paths, daily_name(at(day))) for day in range(1, 6)]
    rig.keep(2)
    removed = rig.daily.prune_now()
    assert sorted(removed) == sorted(path.name for path in files[:3])
    assert [path.exists() for path in files] == [False, False, False, True, True]


def test_a_stored_count_out_of_range_means_the_default_seven(tmp_path: Path) -> None:
    rig = Rig(tmp_path, at(20))
    for day in range(1, 11):
        plant(rig.paths, daily_name(at(day)))
    connection = connect(rig.paths.database)
    connection.execute("INSERT INTO setting (key, value_json) VALUES ('db_backups_kept', '0')")
    connection.close()
    rig.daily.prune_now()
    assert len(daily_backups(rig.paths)) == 7


# ---- start and stop -----------------------------------------------------------------------------------------------


def test_a_part_file_is_cleaned_at_start_and_the_scheduler_backs_up_and_stops(tmp_path: Path) -> None:
    rig = Rig(tmp_path, at(5))
    part = plant(rig.paths, "daily-20200101T000000Z.db.part")
    other_part = plant(rig.paths, "pre-migration-x.db.part")  # not ours: left alone
    rig.daily.start()
    try:
        deadline = time.monotonic() + 10
        while not daily_backups(rig.paths) and time.monotonic() < deadline:
            time.sleep(0.02)
        assert len(daily_backups(rig.paths)) == 1  # a new database is due at once
    finally:
        rig.daily.stop()
    assert not part.exists()
    assert other_part.exists()
    assert rig.daily._thread is not None
    rig.daily._thread.join(timeout=2)
    assert not rig.daily._thread.is_alive()


def test_the_scheduler_stops_within_a_bounded_wait_even_in_the_middle_of_a_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = Rig(tmp_path, at(5))
    entered = threading.Event()
    release = threading.Event()

    def slow(connection: sqlite3.Connection, destination: Path, schema: int) -> None:
        entered.set()
        release.wait(30)
        raise BackupError("backup_failed")

    monkeypatch.setattr(daily_module, "STOP_WAIT_SECONDS", 0.3)
    monkeypatch.setattr(daily_module, "write_checked_copy", slow)
    rig.daily.start()
    try:
        assert entered.wait(10)
        began = time.monotonic()
        rig.daily.stop()
        assert time.monotonic() - began < 3
    finally:
        release.set()
        if rig.daily._thread is not None:
            rig.daily._thread.join(timeout=5)
    assert daily_backups(rig.paths) == []


def test_an_error_in_the_check_does_not_end_the_loop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = Rig(tmp_path, at(5))
    calls = {"n": 0}
    real = rig.daily.is_due

    def flaky() -> bool:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return real()

    monkeypatch.setattr(rig.daily, "is_due", flaky)
    rig.daily.start()
    try:
        deadline = time.monotonic() + 10
        while not daily_backups(rig.paths) and time.monotonic() < deadline:
            time.sleep(0.02)
        assert len(daily_backups(rig.paths)) == 1
    finally:
        rig.daily.stop()
