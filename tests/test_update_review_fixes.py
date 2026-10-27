"""The analyst's CHANGE on the early check (M1b.2 run file section 2), one test group per item."""

import logging
import os
import sqlite3
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from shelfsync.db import backup as backup_module
from shelfsync.db.backup import BackupError, migrate_with_backup, restore_backup, take_snapshot
from shelfsync.db.connection import connect
from shelfsync.platform.junction import LinkError
from shelfsync.platform.process import RealProcesses
from shelfsync.platform.uninstall_entry import MemoryUninstallEntry, RegistryUninstallEntry
from shelfsync.update import service as service_module
from shelfsync.update import switch
from shelfsync.update.github import Outcome
from shelfsync.update.layout import InstallLayout, UpdatePaths
from shelfsync.update.state import PendingUpdate, ResultStore, SwitchResult
from shelfsync.update.switch import repoint, run_switch
from tests.test_db_backup import TWO, database_at_release_one, migrations, versions_of
from tests.test_update_service import make_rig as make_service_rig
from tests.test_update_service import rolled_state
from tests.test_update_switch import KEYS, LATE, OLD_PID, Rig, make_rig
from tests.update_support import FakeGitHub, FakeLinks, FakeLock, build_release, make_install

THREE = ("0003_more.sql", "CREATE TABLE extra (id INTEGER PRIMARY KEY);\n")


# ---- 1. the action lock does not leak -------------------------------------------------------------


def test_a_refused_second_install_does_not_leak_the_action_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_service_rig(tmp_path, monkeypatch)
    rig.service.run_check()
    rig.service.install()
    for _ in range(3):
        with pytest.raises(service_module.UpdateConflict) as caught:
            rig.service.install()
        assert caught.value.code == "busy"
        assert not rig.service._action_lock.locked()
    with pytest.raises(service_module.UpdateConflict):
        rig.service.rollback(False)
    assert not rig.service._action_lock.locked()
    # the switcher reports that nothing was switched (the old copy never quit): the owner may try again
    ResultStore(UpdatePaths(rig.paths)).save(
        SwitchResult(
            "install", "0.0.1", "0.0.2", "not_switched", "old_copy_still_running", "2026-10-27T12:00:01.000000Z"
        )
    )
    assert rig.service.status().busy is False
    rig.service.install()
    assert len(rig.procs.spawned) == 2


# ---- 2. no restore without the instance lock ------------------------------------------------------


class LockLostAfter(FakeLock):
    """The first `n` acquire calls work, every later one finds the lock taken."""

    def __init__(self, n: int) -> None:
        super().__init__()
        self.n = n
        self.calls = 0

    def acquire(self) -> bool:
        self.calls += 1
        return super().acquire() if self.calls <= self.n else False


def migrates_to(rig: Rig, folder: Path) -> object:
    def hook() -> None:
        connection = connect(rig.paths.database)
        migrate_with_backup(connection, rig.paths, folder, now=lambda: LATE)
        connection.close()

    return hook


def test_a_failed_start_with_the_lock_taken_restores_nothing_and_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.1")
    database_at_release_one(rig.paths, migrations(tmp_path))
    rig.on_start["0.0.2"] = migrates_to(rig, migrations(tmp_path, TWO))
    rig.health.script["0.0.2"] = ["no_answer"]
    rig.lock = LockLostAfter(1)  # taken once for the switch, then another copy holds it
    calls: list[object] = []
    real = switch.restore_backup
    monkeypatch.setattr(switch, "restore_backup", lambda record, paths: (calls.append(record), real(record, paths))[1])
    result = run_switch(rig.plan("install", "0.0.1", "0.0.2"), rig.env)
    assert (result.outcome, result.reason) == ("failed", "no_answer+lock_busy")
    assert calls == []  # no restore without the lock
    assert versions_of(rig.paths.database) == {1, 2}  # and the database is as the new version left it
    assert len(rig.procs.spawned) == 1  # no copy was started: one of the two stated exits that start nothing
    assert rig.procs.spawned[0][2].terminated  # the failed child was ended


# ---- 3. "database changed" from schema numbers; the right backup ----------------------------------


def three_version_rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Rig:
    """0.0.1 (schema 1), 0.0.2 (schema 2) running, 0.0.3 (schema 3) downloaded; the database is at schema 2 and
    0.0.2's start-up took the backup B1 (1 to 2) before migrating."""
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2", "0.0.3"), "0.0.2", previous="0.0.1")
    make_install(rig.layout.root, KEYS, {"0.0.2": None}, schema=2)
    make_install(rig.layout.root, KEYS, {"0.0.3": None}, schema=3)
    database_at_release_one(rig.paths, migrations(tmp_path))
    connection = connect(rig.paths.database)
    migrate_with_backup(
        connection, rig.paths, migrations(tmp_path, TWO), now=lambda: datetime(2026, 10, 27, 11, 0, tzinfo=UTC)
    )
    connection.close()
    rig.store.update(lambda s: replace(s, switched_at="2026-10-27T11:00:00.000000Z"))
    return rig


def test_a_failed_v3_install_then_a_rollback_to_v1_restores_b1_not_b2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = three_version_rig(tmp_path, monkeypatch)
    b1 = rig.store.load().backup
    assert b1 is not None and (b1.from_schema, b1.to_schema) == (1, 2)
    pending = PendingUpdate("0.0.3", str(rig.layout.version_dir("0.0.3")), "t")
    rig.store.update(lambda s: replace(s, pending=pending))
    # 1. 0.0.2 -> 0.0.3: the new version migrates to schema 3 (backup B2: 2 to 3), then fails its health check
    rig.on_start["0.0.3"] = migrates_to(rig, migrations(tmp_path, TWO, THREE))
    rig.health.script["0.0.3"] = ["no_answer"]
    env = rig.env
    env.own_schema = lambda: 2
    result = run_switch(rig.plan("install", "0.0.2", "0.0.3"), env)
    assert (result.outcome, result.reason) == ("kept_old", "no_answer")
    assert versions_of(rig.paths.database) == {1, 2}  # B2 put the database back at schema 2
    state = rig.store.load()
    assert state.backup == b1 and state.pending == pending and state.previous == "0.0.1"  # the state is reverted too
    # 2. the owner rolls back to 0.0.1: the backup that goes from 1 to 2 (B1) is the one restored, not B2 (2 to 3)
    rig.health.script.clear()
    result = run_switch(rig.plan("rollback", "0.0.2", "0.0.1", restore=True), rig.env)
    assert (result.outcome, result.reason) == ("rolled_back", None)
    assert versions_of(rig.paths.database) == {1}
    check = sqlite3.connect(rig.paths.database)
    assert check.execute("SELECT value_json FROM setting WHERE key = 'theme'").fetchone() == ('"dark"',)
    assert check.execute("SELECT name FROM sqlite_master WHERE name IN ('note', 'extra')").fetchall() == []
    check.close()


def test_a_roll_back_refuses_a_backup_that_is_not_for_this_pair_of_schemas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = three_version_rig(tmp_path, monkeypatch)
    record = rig.store.load().backup
    assert record is not None
    rig.store.update(lambda s: replace(s, backup=replace(record, from_schema=2, to_schema=3)))  # B2 took B1's place
    result = run_switch(rig.plan("rollback", "0.0.2", "0.0.1", restore=True), rig.env)
    assert (result.outcome, result.reason) == ("not_switched", "backup_mismatch")
    assert versions_of(rig.paths.database) == {1, 2} and rig.current == "0.0.2"


def test_a_roll_back_that_the_owner_was_not_told_would_lose_data_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = three_version_rig(tmp_path, monkeypatch)
    result = run_switch(rig.plan("rollback", "0.0.2", "0.0.1", restore=False), rig.env)  # the database did change
    assert (result.outcome, result.reason) == ("not_switched", "database_changed")
    assert versions_of(rig.paths.database) == {1, 2}


def test_the_switchers_decision_ignores_times(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = three_version_rig(tmp_path, monkeypatch)
    rig.store.update(lambda s: replace(s, switched_at="2099-01-01T00:00:00.000000Z"))  # later than every backup
    assert run_switch(rig.plan("rollback", "0.0.2", "0.0.1", restore=True), rig.env).outcome == "rolled_back"
    assert versions_of(rig.paths.database) == {1}


def test_the_service_decides_from_schema_numbers_too(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = make_service_rig(tmp_path, monkeypatch, installed="0.0.2", latest=None, extra_versions=("0.0.1",))
    rig.links.table[str(rig.layout.current)] = rig.layout.version_dir("0.0.2")
    rolled_state(rig, changed_database=True, tmp_path=tmp_path)
    rig.store.update(lambda s: replace(s, switched_at="2099-01-01T00:00:00.000000Z"))  # a clock that disagrees
    status = rig.service.status()
    assert status.database_changed and status.backup_available and status.backup_at is not None
    record = rig.store.load().backup
    assert record is not None
    rig.store.update(lambda s: replace(s, backup=replace(record, from_schema=2, to_schema=3)))  # the wrong backup
    status = rig.service.status()
    assert status.database_changed is True and status.backup_available is False and status.backup_at is None
    with pytest.raises(service_module.UpdateConflict) as caught:
        rig.service.rollback(True)
    assert caught.value.code == "no_backup"


def test_a_database_at_the_previous_schema_needs_no_restore_whatever_the_state_says(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_service_rig(tmp_path, monkeypatch, installed="0.0.2", latest=None, extra_versions=("0.0.1",))
    rig.links.table[str(rig.layout.current)] = rig.layout.version_dir("0.0.2")
    rolled_state(rig, changed_database=False, tmp_path=tmp_path)
    status = rig.service.status()
    assert status.can_roll_back and status.database_changed is False and status.backup_at is None
    rig.service.rollback(False)
    assert "--restore-backup" not in rig.procs.spawned[0][0]


# ---- 4. the safety snapshot before a roll back ----------------------------------------------------


def rolled_rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Rig:
    rig = three_version_rig(tmp_path, monkeypatch)
    connection = connect(rig.paths.database)  # data written since the update, which a roll back must not lose for good
    connection.execute("INSERT INTO note (id, body) VALUES (1, 'written on 0.0.2')")
    connection.close()
    return rig


def snapshot_files(rig: Rig) -> list[Path]:
    return sorted(rig.paths.backups.glob("pre-rollback-*.db"))


def has_note(rig: Rig) -> bool:
    check = sqlite3.connect(rig.paths.database)
    try:
        return check.execute("SELECT body FROM note WHERE id = 1").fetchone() == ("written on 0.0.2",)
    except sqlite3.Error:
        return False
    finally:
        check.close()


def test_a_roll_back_first_takes_a_checked_snapshot_of_the_current_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = rolled_rig(tmp_path, monkeypatch)
    assert run_switch(rig.plan("rollback", "0.0.2", "0.0.1", restore=True), rig.env).outcome == "rolled_back"
    [snapshot] = snapshot_files(rig)
    assert snapshot.name.startswith("pre-rollback-0.0.2-") and snapshot.name.endswith("Z.db")
    check = sqlite3.connect(snapshot)
    assert check.execute("SELECT body FROM note").fetchall() == [("written on 0.0.2",)]  # what the roll back replaced
    assert check.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
    check.close()
    assert versions_of(rig.paths.database) == {1}


def test_a_snapshot_that_cannot_be_made_refuses_the_roll_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = rolled_rig(tmp_path, monkeypatch)

    def refuse(paths: object, label: str, now: object = None) -> object:
        raise BackupError("backup_failed")

    monkeypatch.setattr(switch, "take_snapshot", refuse)
    result = run_switch(rig.plan("rollback", "0.0.2", "0.0.1", restore=True), rig.env)
    assert (result.outcome, result.reason) == ("not_switched", "backup_failed")
    assert versions_of(rig.paths.database) == {1, 2} and has_note(rig)  # nothing was replaced
    assert rig.current == "0.0.2" and rig.launches() == [("0.0.2", True), ("0.0.2", False)]


def test_a_failed_repoint_after_the_restore_puts_the_snapshot_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = rolled_rig(tmp_path, monkeypatch)
    rig.links.fail_at = 1  # the first link call of the re-point fails, after the database was restored
    result = run_switch(rig.plan("rollback", "0.0.2", "0.0.1", restore=True), rig.env)
    assert (result.outcome, result.reason) == ("kept_old", "junction_error")
    assert versions_of(rig.paths.database) == {1, 2} and has_note(rig)  # the snapshot's data is back
    assert rig.current == "0.0.2" and rig.launches()[0] == ("0.0.2", True)
    assert rig.store.load().previous == "0.0.1" and rig.store.load().backup is not None


def test_a_rollback_target_that_exits_2_puts_the_snapshot_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = rolled_rig(tmp_path, monkeypatch)
    rig.exit_codes["0.0.1"] = 2
    seen: list[set[int]] = []
    rig.on_start["0.0.2"] = lambda: seen.append(versions_of(rig.paths.database))  # the copy started afterwards
    result = run_switch(rig.plan("rollback", "0.0.2", "0.0.1", restore=True), rig.env)
    assert (result.outcome, result.reason) == ("kept_old", "migration_failed")
    assert versions_of(rig.paths.database) == {1, 2} and has_note(rig)
    assert seen == [{1, 2}]  # the newer version found its own database, not an older one
    assert rig.current == "0.0.2"
    state = rig.store.load()
    assert (state.installed, state.previous) == ("0.0.2", "0.0.1")


def test_a_snapshot_that_cannot_be_put_back_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = rolled_rig(tmp_path, monkeypatch)
    rig.exit_codes["0.0.1"] = 2
    real = switch.restore_backup
    calls: list[int] = []

    def flaky(record: object, paths: object) -> None:
        calls.append(1)
        if len(calls) == 2:
            raise BackupError("restore_failed")
        real(record, paths)  # type: ignore[arg-type]

    monkeypatch.setattr(switch, "restore_backup", flaky)
    result = run_switch(rig.plan("rollback", "0.0.2", "0.0.1", restore=True), rig.env)
    assert result.reason is not None and "snapshot_restore_failed" in result.reason


def test_a_restore_moves_the_database_aside_and_puts_it_back_if_the_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = rolled_rig(tmp_path, monkeypatch)
    record = rig.store.load().backup
    assert record is not None
    database = rig.paths.database
    wal = database.with_name(database.name + "-wal")
    wal.write_bytes(b"unmerged frames")
    before = database.read_bytes()
    real_replace = os.replace

    def failing(source: object, destination: object) -> None:
        if str(source).endswith(".restore"):
            raise OSError("disk full")
        real_replace(source, destination)  # type: ignore[arg-type]

    monkeypatch.setattr(backup_module.os, "replace", failing)
    with pytest.raises(BackupError) as caught:
        restore_backup(record, rig.paths)
    assert caught.value.code == "restore_failed"
    assert database.read_bytes() == before and wal.read_bytes() == b"unmerged frames"  # all put back
    assert not list(rig.paths.root.glob("*.aside")) and not list(rig.paths.root.glob("*.restore"))


def test_a_successful_restore_leaves_no_old_files_behind(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = rolled_rig(tmp_path, monkeypatch)
    record = rig.store.load().backup
    assert record is not None
    wal = rig.paths.database.with_name(rig.paths.database.name + "-wal")
    wal.write_bytes(b"stale")
    restore_backup(record, rig.paths)
    assert not wal.exists() and not list(rig.paths.root.glob("*.aside"))
    assert versions_of(rig.paths.database) == {1}


def test_take_snapshot_needs_a_database_and_checks_its_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = rolled_rig(tmp_path, monkeypatch)
    snapshot = take_snapshot(rig.paths, "0.0.2", lambda: datetime(2026, 10, 27, 12, tzinfo=UTC))
    assert (snapshot.from_schema, snapshot.to_schema) == (2, 2)
    assert Path(snapshot.path).name == "pre-rollback-0.0.2-20261027T120000Z.db"
    monkeypatch.setattr(backup_module, "check_backup", lambda path, schema=None: False)
    with pytest.raises(BackupError):
        take_snapshot(rig.paths, "0.0.2")
    rig.paths.database.unlink()
    with pytest.raises(BackupError):
        take_snapshot(rig.paths, "0.0.2")


# ---- 5. a roll back never deletes the folder the switcher runs from -------------------------------


def test_after_a_rollback_both_folders_and_their_manifests_are_still_there(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.2", previous="0.0.1")
    assert run_switch(rig.plan("rollback", "0.0.2", "0.0.1"), rig.env).outcome == "rolled_back"
    assert rig.layout.version_dir("0.0.2").is_dir() and (rig.layout.version_dir("0.0.2") / "pythonw.exe").is_file()
    assert rig.layout.manifest_path("0.0.2").is_file() and rig.layout.signature_path("0.0.2").is_file()


# ---- 6, 7. GitHub streams and the 404 follow-up ----------------------------------------------------------------------


class FailsPartWay(httpx.SyncByteStream):
    def __iter__(self):  # type: ignore[no-untyped-def]
        yield b"PK\x03\x04 half of a zip"
        raise httpx.ReadError("connection reset")


def test_a_stream_that_fails_part_way_is_update_failed_unreachable_with_no_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    rig = make_service_rig(tmp_path, monkeypatch)
    zip_id = rig.fake.asset_id("0.0.2", "shelfsync-0.0.2-win64.zip")
    rig.fake.asset_override[zip_id] = lambda r: httpx.Response(200, stream=FailsPartWay())
    caplog.set_level(logging.DEBUG)
    rig.service.run_check()
    last = rig.service.status().last_check
    assert last is not None and (last.outcome, last.detail) == ("update_failed", "unreachable")
    assert "Traceback" not in caplog.text and all(r.exc_info is None for r in caplog.records)
    assert list((tmp_path / "data" / "update" / "downloads").glob("*")) == []  # no .part left


def test_a_failing_stream_while_keeping_the_running_versions_manifest_is_survived(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_service_rig(tmp_path, monkeypatch, latest=None)
    for path in (rig.layout.manifest_path("0.0.1"), rig.layout.signature_path("0.0.1")):
        path.unlink()
    release = build_release("0.0.1", KEYS)
    rig.fake.releases[release.tag] = release
    rig.fake.latest_tag = release.tag
    rig.fake.asset_override[rig.fake.asset_id("0.0.1", "manifest.json")] = lambda r: httpx.Response(
        200, stream=FailsPartWay()
    )
    rig.service.run_check()  # must not raise
    last = rig.service.status().last_check
    assert last is not None and last.outcome == "ok"
    assert not rig.layout.manifest_path("0.0.1").exists()


@pytest.mark.parametrize(
    ("status", "headers", "outcome"),
    [
        (403, {"x-ratelimit-remaining": "0"}, Outcome.RATE_LIMITED),
        (429, {}, Outcome.RATE_LIMITED),
        (403, {}, Outcome.UNREACHABLE),
        (500, {}, Outcome.UNREACHABLE),
    ],
)
def test_the_follow_up_request_after_a_404_is_classified_like_any_other(
    status: int, headers: dict[str, str], outcome: Outcome
) -> None:
    from shelfsync.update.github import GitHubClient

    fake = FakeGitHub(repo_status=status, repo_headers=headers)  # latest answers 404; the repository check is limited
    assert GitHubClient(lambda: None, transport=fake.transport()).latest().outcome is outcome
    token_fake = FakeGitHub(repo_status=403, repo_headers={})
    assert (
        GitHubClient(lambda: "github_pat_" + "a" * 30, transport=token_fake.transport()).latest().outcome
        is Outcome.TOKEN_REFUSED
    )


# ---- 8. the start-up tidy-up cannot stop the app --------------------------------------------------------------------


def test_a_failing_tidy_up_still_starts_the_schedule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    rig = make_service_rig(tmp_path, monkeypatch)

    def boom(folder: Path) -> None:
        raise RuntimeError("secret detail that must not be logged: C:\\Users\\someone")

    monkeypatch.setattr(service_module, "clear_downloads", boom)
    caplog.set_level(logging.WARNING)
    rig.service.start()
    try:
        assert rig.service._thread is not None and rig.service._thread.is_alive()
    finally:
        rig.service.stop()
    assert "RuntimeError" in caplog.text and "secret detail" not in caplog.text


def test_a_state_that_cannot_be_reconciled_does_not_stop_the_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_service_rig(tmp_path, monkeypatch)

    def boom(layout: InstallLayout) -> None:
        raise PermissionError("denied")

    monkeypatch.setattr(rig.service, "_reconcile_state", boom)
    rig.service.start()
    assert rig.service._thread is not None
    rig.service.stop()


# ---- 9. the registry only for an installed copy ---------------------------------------------------


def test_the_real_uninstall_entry_is_used_only_by_an_installed_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.1").paths
    monkeypatch.setattr(switch, "_make_lock", lambda paths: FakeLock())  # the real mutex exists on Windows only
    monkeypatch.setattr(switch, "installed_root", lambda: None)
    env = switch.default_env(paths)
    assert isinstance(env.uninstall, MemoryUninstallEntry) and env.uninstall.set_display_version("0.0.2") is False
    monkeypatch.setattr(switch, "installed_root", lambda: tmp_path / "Programs" / "ShelfSync")
    assert isinstance(switch.default_env(paths).uninstall, RegistryUninstallEntry)


def test_the_lock_gets_the_data_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.1").paths
    seen: list[object] = []

    def with_paths(paths: object = None) -> FakeLock:
        seen.append(paths)
        return FakeLock()

    monkeypatch.setattr(switch, "default_instance_lock", with_paths)
    assert isinstance(switch._make_lock(paths), FakeLock) and seen == [paths]


# ---- 10. one handle on the old process ------------------------------------------------------------


def test_the_old_process_must_be_the_old_versions_own_python(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.1")
    rig.procs.running.add(OLD_PID)
    rig.procs.images[OLD_PID] = r"C:\Windows\System32\notepad.exe"  # the PID names something else
    result = run_switch(rig.plan("install", "0.0.1", "0.0.2"), rig.env)
    assert (result.outcome, result.reason) == ("not_switched", "old_process_mismatch")
    assert rig.links.log == [] and rig.procs.watches[0].closed  # nothing was switched, the handle was released
    # the real old copy may have quit meanwhile, so the lock decides: it was free, and what `current` names is started
    assert rig.lock.acquired == 1 and rig.launches() == [("0.0.1", True), ("0.0.1", False)]
    assert rig.clock.now - 1000.0 < switch.WAIT_FOR_QUIT_SECONDS  # the handle on the wrong process wasn't waited for


def test_a_pid_that_is_not_the_old_copy_with_the_lock_taken_means_a_copy_is_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.1")
    rig.procs.running.add(OLD_PID)
    rig.procs.images[OLD_PID] = r"C:\Windows\System32\notepad.exe"
    rig.lock.busy_for = 10**6  # the real old copy is still up, holding the lock
    result = run_switch(rig.plan("install", "0.0.1", "0.0.2"), rig.env)
    assert (result.outcome, result.reason) == ("not_switched", "lock_busy")
    assert rig.procs.spawned == [] and rig.links.log == []  # one copy is running: nothing to start
    assert rig.clock.now - 1000.0 >= switch.WAIT_FOR_QUIT_SECONDS


@pytest.mark.parametrize("which", ["pythonw.exe", "python.exe"])
def test_either_of_the_old_versions_programs_is_accepted_and_the_handle_is_released(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, which: str
) -> None:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.1")
    rig.procs.running.add(OLD_PID)
    rig.procs.images[OLD_PID] = str(rig.layout.version_dir("0.0.1") / which)
    original = rig.clock.sleep
    state = {"n": 0}

    def sleeping(seconds: float) -> None:
        original(seconds)
        state["n"] += 1
        if state["n"] == 4:
            rig.procs.running.discard(OLD_PID)

    env = rig.env
    env.sleep = sleeping
    assert run_switch(rig.plan("install", "0.0.1", "0.0.2"), env).outcome == "updated"
    assert len(rig.procs.watches) == 1 and rig.procs.watches[0].closed


def test_an_unreadable_image_of_a_process_that_stays_up_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.1")
    rig.procs.running.add(OLD_PID)
    del rig.procs.images[OLD_PID]
    result = run_switch(rig.plan("install", "0.0.1", "0.0.2"), rig.env)
    # it is waited for on the handle for the whole wait; the lock is then free, so the copy that quit is started again
    assert (result.outcome, result.reason) == ("not_switched", "old_process_mismatch")
    assert rig.clock.now - 1000.0 >= switch.WAIT_FOR_QUIT_SECONDS
    assert rig.launches() == [("0.0.1", True), ("0.0.1", False)] and rig.links.log == []


def test_an_unreadable_image_that_stays_up_with_the_lock_held_is_a_copy_still_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.1")
    rig.procs.running.add(OLD_PID)
    del rig.procs.images[OLD_PID]
    rig.lock.busy_for = 10**6
    result = run_switch(rig.plan("install", "0.0.1", "0.0.2"), rig.env)
    assert (result.outcome, result.reason) == ("not_switched", "old_copy_still_running")
    assert rig.procs.spawned == [] and rig.links.log == []


def test_an_unreadable_image_that_ends_while_waited_for_lets_the_switch_go_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.1")
    rig.procs.running.add(OLD_PID)
    del rig.procs.images[OLD_PID]
    original = rig.clock.sleep
    state = {"n": 0}

    def sleeping(seconds: float) -> None:
        original(seconds)
        state["n"] += 1
        if state["n"] == 30:  # long after the grace period, within the full wait
            rig.procs.running.discard(OLD_PID)

    env = rig.env
    env.sleep = sleeping
    assert run_switch(rig.plan("install", "0.0.1", "0.0.2"), env).outcome == "updated"


def test_a_lock_that_is_taken_after_a_refused_target_still_ends_with_a_copy_running_or_none_needed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refused target used to give the lock no time to be released by a copy on its way out; it now waits."""
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.1")
    (rig.layout.version_dir("0.0.2") / "python.exe").write_bytes(b"swapped")
    rig.lock.busy_for = 3  # the old copy releases it a moment later
    result = run_switch(rig.plan("install", "0.0.1", "0.0.2"), rig.env)
    assert (result.outcome, result.reason) == ("not_switched", "files_changed")
    assert rig.launches() == [("0.0.1", True), ("0.0.1", False)]


def test_an_old_copy_already_shutting_down_cannot_be_asked_its_image_but_is_let_go(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rehearsal found this: the app is asked to quit while the switcher is still starting, so by the time the
    switcher opens its handle the process is on its way out and Windows won't name its program."""
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.1")
    rig.procs.running.add(OLD_PID)
    del rig.procs.images[OLD_PID]
    original = rig.clock.sleep
    state = {"n": 0}

    def sleeping(seconds: float) -> None:
        original(seconds)
        state["n"] += 1
        if state["n"] == 3:
            rig.procs.running.discard(OLD_PID)  # it finishes exiting within the grace period

    env = rig.env
    env.sleep = sleeping
    assert run_switch(rig.plan("install", "0.0.1", "0.0.2"), env).outcome == "updated"


def test_an_old_process_that_is_already_gone_is_not_waited_for(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.1")
    assert run_switch(rig.plan("install", "0.0.1", "0.0.2"), rig.env).outcome == "updated"
    assert rig.procs.watches == []


def test_the_real_watch_holds_a_handle_and_names_the_image() -> None:
    watch = RealProcesses().watch(os.getpid())
    assert watch is not None
    try:
        assert watch.is_running()
        if sys.platform == "win32":
            assert watch.image is not None and Path(watch.image).name.lower() in ("python.exe", "pythonw.exe")
    finally:
        watch.close()
    assert RealProcesses().watch(0) is None


# ---- 11. a missing current after an interrupted switch --------------------------------------------


class InterruptedAt(FakeLinks):
    def __init__(self, at: int) -> None:
        super().__init__()
        self.at = at

    def _tick(self, what: str) -> None:
        self.calls += 1
        if self.calls == self.at:
            raise KeyboardInterrupt  # not a LinkError: a BaseException


@pytest.mark.parametrize("at", [1, 2, 3, 4])
def test_repoint_puts_current_back_on_any_exception_at_all(tmp_path: Path, at: int) -> None:
    layout = InstallLayout(tmp_path / "root")
    for version in ("0.0.1", "0.0.2"):
        (layout.versions / version).mkdir(parents=True)
    links = InterruptedAt(at)
    links.table[str(layout.current)] = layout.version_dir("0.0.1")
    with pytest.raises(KeyboardInterrupt):
        repoint(layout, links, "0.0.2")
    assert (
        links.exists(layout.current) and not links.exists(layout.current_old) and not links.exists(layout.current_next)
    )


def test_main_makes_one_last_attempt_to_repair_current(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    layout = InstallLayout(tmp_path / "root")
    (layout.versions / "0.0.1").mkdir(parents=True)
    links = FakeLinks()
    links.table[str(layout.current_old)] = layout.version_dir("0.0.1")  # a switch that died with `current` renamed away

    def dies(plan: object, env: object = None) -> SwitchResult:
        raise RuntimeError("killed")

    monkeypatch.setattr(switch, "run_switch", dies)
    monkeypatch.setattr(switch, "default_links", lambda: links)
    monkeypatch.setattr(switch, "installed_root", lambda: None)
    argv = [
        "--format", "1", "--mode", "install", "--from", "0.0.1", "--to", "0.0.2", "--install-root", str(layout.root),
        "--data-dir", str(tmp_path / "data"), "--old-pid", "4242",
    ]  # fmt: skip
    assert switch.main(argv) == switch.EXIT_FAILED
    assert links.exists(layout.current) and not links.exists(layout.current_old)


def test_main_survives_a_repair_that_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    layout = InstallLayout(tmp_path / "root")
    links = FakeLinks()
    links.table[str(layout.current_old)] = tmp_path / "x"
    links.fail_at = 1
    monkeypatch.setattr(
        switch, "run_switch", lambda plan, env=None: SwitchResult("install", "0.0.1", "0.0.2", "updated", None, "t")
    )
    monkeypatch.setattr(switch, "default_links", lambda: links)
    monkeypatch.setattr(switch, "installed_root", lambda: None)
    argv = [
        "--format", "1", "--mode", "install", "--from", "0.0.1", "--to", "0.0.2", "--install-root", str(layout.root),
        "--data-dir", str(tmp_path / "data"), "--old-pid", "4242",
    ]  # fmt: skip
    assert switch.main(argv) == switch.EXIT_DONE


def test_the_exit_that_starts_nothing_after_a_junction_failure_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`failed` with `junction_error`: the link couldn't be put back, so no copy was started."""
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.1")

    class Dies(FakeLinks):
        def _tick(self, what: str) -> None:
            self.calls += 1
            if self.calls >= 5:  # the swap to the new version works; putting `<from>` back does not
                raise LinkError("the link calls stop working")

    class RegistryDown(MemoryUninstallEntry):
        def set_display_version(self, version: str) -> bool:
            raise OSError("registry unavailable")  # makes the switch give up after the swap

    rig.links = Dies()
    rig.links.table[str(rig.layout.current)] = rig.layout.version_dir("0.0.1")
    rig.uninstall = RegistryDown()
    result = run_switch(rig.plan("install", "0.0.1", "0.0.2"), rig.env)
    assert result.outcome == "failed" and result.reason is not None and result.reason.endswith("junction_error")
    assert rig.procs.spawned == []  # nothing was started: a stated exit
    assert (
        rig.current == "0.0.2"
    )  # and `current` is where the failed swap left it; Setup.exe or the shortcut repairs it
