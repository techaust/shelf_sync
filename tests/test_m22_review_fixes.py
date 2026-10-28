"""BAK-01: the m2.2 review fixes (M1, M2, L1-L7), each with its test."""

import logging
import os
import shutil
import sqlite3
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from shelfsync.db import daily as daily_module
from shelfsync.db import restore as restore_module
from shelfsync.db.connection import connect
from shelfsync.db.daily import daily_backups, daily_name, prune
from shelfsync.db.restore import EXIT_FAILED, EXIT_OK
from shelfsync.paths import DataPaths
from shelfsync.update.layout import UpdatePaths
from tests.test_backup_settings_api import GOOD
from tests.test_backup_settings_api import Rig as ApiRig
from tests.test_backup_settings_api import put as api_put
from tests.test_db_daily import Rig, at, plant
from tests.test_db_restore import Run
from tests.update_support import data_paths


def _parts(rig: Rig) -> list[str]:
    return [name for name in rig.names() if ".part" in name]


# ---- daily ---------------------------------------------------------------------------------------------------------


def test_m1_a_malformed_stored_count_gives_the_default_and_leaves_no_part(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    rig = Rig(tmp_path, at(20))
    for day in range(1, 11):
        plant(rig.paths, daily_name(at(day)))
    connection = connect(rig.paths.database)
    connection.execute("INSERT INTO setting (key, value_json) VALUES ('db_backups_kept', '{broken')")
    connection.close()
    with caplog.at_level("WARNING", logger="shelfsync.db"):
        assert rig.daily.run_once()
    assert "db_backups_kept" in caplog.text
    assert _parts(rig) == []
    assert len(daily_backups(rig.paths)) == 7  # the default


def test_m1_an_unexpected_error_mid_run_leaves_no_part_or_side_file_and_waits_for_the_next_slot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = Rig(tmp_path, at(20))

    def explodes(connection: sqlite3.Connection, destination: Path, schema: int) -> None:
        destination.write_bytes(b"half")
        destination.with_name(destination.name + "-journal").write_bytes(b"j")
        raise ValueError("unexpected")

    monkeypatch.setattr(daily_module, "write_checked_copy", explodes)
    assert rig.daily.run_once() is False
    assert _parts(rig) == []
    assert not rig.daily.is_due()  # not a new full-size copy every minute


def test_l4_a_daily_stamp_in_the_future_is_no_backup_made_but_still_counts_for_retention(tmp_path: Path) -> None:
    rig = Rig(tmp_path, at(20))
    future = plant(rig.paths, daily_name(datetime(2030, 1, 1, 2, 0, 0, tzinfo=UTC)))
    assert rig.daily.is_due()
    assert rig.daily.run_once()
    rig.keep(1)
    rig.daily.prune_now()
    assert not future.exists()  # a wrong clock's stamp ranks oldest (N1): it goes first
    assert (rig.paths.backups / daily_name(at(20))).exists()


def test_l4_a_stamp_within_the_margin_counts_as_made(tmp_path: Path) -> None:
    rig = Rig(tmp_path, at(20))
    plant(rig.paths, daily_name(at(20, 3)))
    assert not rig.daily.is_due()


def test_l5_a_malformed_state_json_is_left_exactly_as_it_is_and_protects_nothing(tmp_path: Path) -> None:
    paths = data_paths(tmp_path)
    state = UpdatePaths(paths).state_json
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_bytes(b"{not json")
    files = [plant(paths, daily_name(at(day))) for day in (1, 2, 3)]
    assert prune(paths, 1) == [files[0].name, files[1].name]
    assert state.read_bytes() == b"{not json"
    assert [entry.name for entry in state.parent.iterdir()] == ["state.json"]


def test_l5_a_state_json_with_two_names_is_not_touched(tmp_path: Path) -> None:
    paths = data_paths(tmp_path)
    state = UpdatePaths(paths).state_json
    state.parent.mkdir(parents=True, exist_ok=True)
    other = tmp_path / "other.json"
    other.write_bytes(b"{}")
    os.link(other, state)
    plant(paths, daily_name(at(1)))
    plant(paths, daily_name(at(2)))
    assert len(prune(paths, 1)) == 1
    assert state.exists()
    assert other.read_bytes() == b"{}"


def test_l6_stray_side_files_of_a_part_are_cleaned(tmp_path: Path) -> None:
    rig = Rig(tmp_path, at(5))
    stray = [plant(rig.paths, f"daily-20200101T000000Z.db.part{suffix}") for suffix in ("", "-journal", "-wal", "-shm")]
    keep = plant(rig.paths, "daily-20200101T000000Z.db.part-other")
    rig.daily.clean_parts()
    assert not any(path.exists() for path in stray)
    assert keep.exists()


def test_l6_start_twice_does_not_start_a_second_loop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = Rig(tmp_path, at(5))
    release = threading.Event()
    monkeypatch.setattr(rig.daily, "is_due", lambda: bool(release.wait(10)) and False)
    rig.daily.start()
    try:
        first = rig.daily._thread
        rig.daily.start()
        assert rig.daily._thread is first
    finally:
        release.set()
        rig.daily.stop()


def test_l3_prune_now_skips_while_a_backup_runs_instead_of_waiting(tmp_path: Path) -> None:
    rig = Rig(tmp_path, at(20))
    for day in range(1, 6):
        plant(rig.paths, daily_name(at(day)))
    rig.keep(1)
    with rig.daily._lock:
        began = time.monotonic()
        assert rig.daily.prune_now() == []
        assert time.monotonic() - began < 1
    assert len(daily_backups(rig.paths)) == 5
    assert len(rig.daily.prune_now()) == 4


def test_l3_a_prune_that_fails_after_the_save_still_answers_what_was_saved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    rig = ApiRig(tmp_path)

    def boom() -> list[str]:
        raise RuntimeError("disk")

    monkeypatch.setattr(rig.daily, "prune_now", boom)
    with caplog.at_level("WARNING", logger="shelfsync.api.settings"):
        response = api_put(rig, {**GOOD, "db_backups_kept": 2})
    assert response.status_code == 200
    assert response.json()["db_backups_kept"] == 2
    assert rig.stored()["db_backups_kept"] == 2
    assert "Pruning after the setting was lowered failed" in caplog.text


# ---- restore -------------------------------------------------------------------------------------------------------


def test_m2_a_damaged_database_keeps_its_wal_and_shm_beside_the_copy(tmp_path: Path) -> None:
    run = Run(tmp_path)
    backup = run.daily()
    database = run.paths.database
    database.write_bytes(b"garbage" * 100)
    wal = database.with_name(database.name + "-wal")
    wal.write_bytes(b"wal-content" * 50)
    database.with_name(database.name + "-shm").write_bytes(b"shm-content")
    assert run.go(backup.name) == EXIT_OK
    kept = next(run.paths.backups.glob("pre-rollback-damaged-*.db"))
    assert kept.read_bytes() == b"garbage" * 100
    assert kept.with_name(kept.name + "-wal").read_bytes() == b"wal-content" * 50
    assert kept.with_name(kept.name + "-shm").exists()  # SQLite may touch it on opening; it only indexes the -wal
    assert not wal.exists()
    assert run.go("--list") == EXIT_OK
    assert all("-wal" not in line and "-shm" not in line for line in run.said)  # the side copies aren't listed


def test_m2_a_failed_copy_of_the_wal_stops_the_restore_and_removes_the_partial_copies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = Run(tmp_path)
    backup = run.daily()
    database = run.paths.database
    database.write_bytes(b"garbage" * 100)
    database.with_name(database.name + "-wal").write_bytes(b"wal")
    real = shutil.copyfile

    def copy(source: str | os.PathLike[str], destination: str | os.PathLike[str]) -> str | os.PathLike[str]:
        if str(destination).endswith("-wal"):
            raise OSError("disk full")
        return real(source, destination)

    monkeypatch.setattr(restore_module.shutil, "copyfile", copy)
    assert run.go(backup.name) == EXIT_FAILED
    assert run.said == [restore_module.SNAPSHOT_FAILED]
    assert database.read_bytes() == b"garbage" * 100
    assert not list(run.paths.backups.glob("pre-rollback-*"))


def test_l1_an_os_error_while_saving_the_current_database_is_a_clean_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = Run(tmp_path)
    backup = run.daily()
    run.change_theme("dark")

    def broken(paths: DataPaths, label: str, now: object) -> object:
        (paths.backups / f"pre-rollback-{label}-20260310T140000Z.db").write_bytes(b"partial")
        raise PermissionError("locked")

    monkeypatch.setattr(restore_module, "take_snapshot", broken)
    assert run.go(backup.name) == EXIT_FAILED
    assert run.said == [restore_module.SNAPSHOT_FAILED]
    assert not list(run.paths.backups.glob("pre-rollback-*"))
    assert run.theme() == '"dark"'


def test_l2_the_reason_for_a_failure_is_in_the_log_and_the_handler_is_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = Run(tmp_path)
    backup = run.daily()

    def fails(record: object, paths: object) -> None:
        raise restore_module.BackupError("restore_failed")

    monkeypatch.setattr(restore_module, "restore_backup", fails)
    handlers = list(logging.getLogger().handlers)
    assert run.go(backup.name) == EXIT_FAILED
    assert logging.getLogger().handlers == handlers
    text = (run.paths.logs / "shelfsync.log").read_text(encoding="utf-8")
    assert "restore_failed" in text
    assert backup.name in text


def test_l7_the_list_skips_a_file_that_cannot_be_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run = Run(tmp_path)
    good = run.daily()
    bad = run.paths.backups / "daily-20250101T000000Z.db"
    shutil.copy(good, bad)
    real = Path.stat

    def stat(self: Path, **kwargs: bool) -> os.stat_result:
        if self.name == bad.name:
            raise OSError("gone")
        return real(self, **kwargs)

    monkeypatch.setattr(Path, "stat", stat)
    assert run.go("--list") == EXIT_OK
    assert len(run.said) == 1
    assert run.said[0].startswith(good.name)
