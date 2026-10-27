"""BAK-01: the m2.2 re-review fixes (N1-N6 and the lifespan)."""

import os
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from shelfsync.api.backup_settings import BACKUP_SETTINGS_PATH
from shelfsync.db import daily as daily_module
from shelfsync.db import restore as restore_module
from shelfsync.db.connection import connect
from shelfsync.db.daily import daily_backups, daily_name
from shelfsync.db.restore import EXIT_OK
from tests.support import make_harness
from tests.test_backup_settings_api import Rig as ApiRig
from tests.test_db_daily import Rig, at, plant
from tests.test_db_restore import Run

FUTURE = datetime(2030, 1, 1, 2, 0, 0, tzinfo=UTC)


def test_n1_a_future_stamp_never_pushes_out_a_real_backup_and_no_loop_of_copies(tmp_path: Path) -> None:
    rig = Rig(tmp_path, at(20))
    future = plant(rig.paths, daily_name(FUTURE))
    rig.keep(1)
    assert rig.daily.run_once()
    assert (rig.paths.backups / daily_name(at(20))).exists()
    assert not future.exists()
    assert not rig.daily.is_due()  # not a copy made and deleted every minute


def test_n1_several_future_stamps_all_go_before_a_real_one(tmp_path: Path) -> None:
    rig = Rig(tmp_path, at(20))
    futures = [plant(rig.paths, daily_name(FUTURE.replace(day=day))) for day in (1, 2, 3)]
    rig.keep(2)
    assert rig.daily.run_once()
    assert [path.exists() for path in futures] == [False, False, True]
    assert (rig.paths.backups / daily_name(at(20))).exists()
    assert len(daily_backups(rig.paths)) == 2


def test_n2_a_setting_lowered_during_the_copy_applies_in_that_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = Rig(tmp_path, at(20))
    for day in range(1, 6):
        plant(rig.paths, daily_name(at(day)))
    real = daily_module.write_checked_copy

    def lowering(connection: sqlite3.Connection, destination: Path, schema: int) -> None:
        real(connection, destination, schema)
        rig.keep(2)  # the owner saves a lower number while the copy runs

    monkeypatch.setattr(daily_module, "write_checked_copy", lowering)
    assert rig.daily.run_once()
    assert len(daily_backups(rig.paths)) == 2


def test_n3_a_failed_cleanup_of_the_part_never_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = Rig(tmp_path, at(20))

    def explodes(connection: sqlite3.Connection, destination: Path, schema: int) -> None:
        destination.write_bytes(b"half")
        raise ValueError("x")

    real_unlink = Path.unlink

    def locked(self: Path, missing_ok: bool = False) -> None:
        if ".part" in self.name:
            raise PermissionError("locked")
        real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(daily_module, "write_checked_copy", explodes)
    monkeypatch.setattr(Path, "unlink", locked)
    assert rig.daily.run_once() is False


def test_n4_a_second_start_calls_off_a_stop_that_timed_out(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = Rig(tmp_path, at(5))
    release = threading.Event()
    monkeypatch.setattr(rig.daily, "is_due", lambda: bool(release.wait(10)) and False)
    rig.daily.start()
    try:
        rig.daily._stop.set()  # a stop that timed out
        rig.daily.start()
        assert not rig.daily._stop.is_set()
    finally:
        release.set()
        rig.daily.stop()


def test_n5_the_api_reports_the_newest_real_backup(tmp_path: Path) -> None:
    rig = ApiRig(tmp_path)
    assert rig.daily.run_once()
    plant(rig.paths, daily_name(FUTURE))
    body = rig.client.get(BACKUP_SETTINGS_PATH).json()
    assert body["last_backup_at"] == "2026-03-10T14:00:00.000000Z"
    assert body["daily_count"] == 2


def test_n6_the_raw_copy_is_made_before_the_database_is_opened(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run = Run(tmp_path)
    backup = run.daily()
    database = run.paths.database
    database.write_bytes(b"garbage" * 100)
    shm = database.with_name(database.name + "-shm")
    shm.write_bytes(b"shm-content")
    database.with_name(database.name + "-wal").write_bytes(b"wal-content")
    real = restore_module.take_snapshot

    def touching(paths: object, label: str, now: object) -> object:
        shm.write_bytes(b"changed by opening")  # what SQLite may do when it opens the database
        return real(paths, label, now)  # type: ignore[arg-type]

    monkeypatch.setattr(restore_module, "take_snapshot", touching)
    assert run.go(backup.name) == EXIT_OK
    kept = next(run.paths.backups.glob("pre-rollback-damaged-*.db"))
    assert kept.with_name(kept.name + "-shm").read_bytes() == b"shm-content"


def test_n6_a_readable_database_leaves_only_its_proper_snapshot(tmp_path: Path) -> None:
    run = Run(tmp_path)
    backup = run.daily()
    assert run.go(backup.name) == EXIT_OK
    assert len(list(run.paths.backups.glob("pre-rollback-restore-*"))) == 1
    assert not list(run.paths.backups.glob("pre-rollback-damaged-*"))


def test_lifespan_a_failing_scheduler_start_still_runs_the_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = ApiRig(tmp_path)
    calls: list[str] = []

    def failing() -> None:
        raise RuntimeError("no thread")

    monkeypatch.setattr(rig.daily, "start", failing)
    monkeypatch.setattr(rig.daily, "stop", lambda: calls.append("stop"))
    harness = make_harness(backups=rig.service)
    with pytest.raises(RuntimeError), TestClient(harness.app):
        pass
    assert calls == ["stop"]
    assert os.path.isdir(rig.paths.backups)
    connect(rig.paths.database).close()
