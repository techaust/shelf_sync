"""SYS-06, SYS-07, 04-A V39: the switch. Every fake (links, processes, lock, health, registry) is in memory; the real
junction, process and registry adapters are exercised by the `windows` tests."""

import inspect
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from shelfsync.db.backup import migrate_with_backup
from shelfsync.db.connection import connect
from shelfsync.db.migrate import migrate
from shelfsync.paths import DataPaths, write_runtime_json
from shelfsync.platform.junction import LinkError
from shelfsync.platform.sockets import Verdict
from shelfsync.platform.uninstall_entry import MemoryUninstallEntry
from shelfsync.update import switch
from shelfsync.update.layout import InstallLayout, UpdatePaths
from shelfsync.update.state import ResultStore, StateStore, SwitchResult
from shelfsync.update.switch import (
    HealthProbe,
    SwitchEnv,
    SwitchPlan,
    current_version,
    main,
    prune_versions,
    repair_current,
    repoint,
    run_switch,
    version_images,
)
from tests.test_db_backup import TWO, database_at_release_one, migrations, versions_of
from tests.update_support import (
    FakeClock,
    FakeLinks,
    FakeLock,
    FakeProc,
    FakeProcesses,
    Keys,
    data_paths,
    make_install,
    make_keys,
    use_key,
)

KEYS = make_keys(1)
OLD_PID = 4242
LATE = datetime(2026, 10, 27, 23, 0, tzinfo=UTC)  # later than anything the rig's clock reaches


class ScriptedHealth:
    """`script[version]` is the list of answers `probe` gives for that version (None = healthy); the last repeats."""

    def __init__(self) -> None:
        self.script: dict[str, list[str | None]] = {}
        self.calls: list[tuple[str, int, frozenset[str]]] = []

    def probe(self, paths: DataPaths, pid: int, version: str, images: frozenset[str]) -> str | None:
        self.calls.append((version, pid, images))
        answers = self.script.get(version, [None])
        return answers.pop(0) if len(answers) > 1 else answers[0]


@dataclass
class Rig:
    layout: InstallLayout
    paths: DataPaths
    links: FakeLinks
    procs: FakeProcesses
    lock: FakeLock
    uninstall: MemoryUninstallEntry
    health: ScriptedHealth
    clock: FakeClock
    keys: Keys
    exit_codes: dict[str, int | None] = field(default_factory=dict)
    on_start: dict[str, object] = field(default_factory=dict)
    ticks: int = 0

    def now(self) -> datetime:
        self.ticks += 1
        return datetime(2026, 10, 27, 12, 0, tzinfo=UTC) + timedelta(seconds=self.ticks)

    @property
    def env(self) -> SwitchEnv:
        return SwitchEnv(
            self.links, self.procs, self.uninstall, self.lock, self.health,
            clock=self.clock, sleep=self.clock.sleep, now=self.now, image_of=lambda pid: None,
        )  # fmt: skip

    def plan(self, mode: str, from_version: str, to_version: str, restore: bool = False) -> SwitchPlan:
        return SwitchPlan(mode, from_version, to_version, self.layout, self.paths, OLD_PID, restore)

    @property
    def store(self) -> StateStore:
        return StateStore(UpdatePaths(self.paths))

    @property
    def result(self) -> SwitchResult | None:
        return ResultStore(UpdatePaths(self.paths)).load()

    @property
    def current(self) -> str | None:
        return current_version(self.layout, self.links)

    def launches(self) -> list[tuple[str, bool]]:
        """(the version `current` pointed at, whether it was the --background start) for every spawned launcher."""
        return [(target, "--background" in argv) for argv, target in self.spawn_targets]

    spawn_targets: list[tuple[list[str], str]] = field(default_factory=list)


def make_rig(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    versions: tuple[str, ...],
    current: str,
    previous: str | None = None,
) -> Rig:
    use_key(monkeypatch, KEYS)
    layout = InstallLayout(tmp_path / "Programs" / "ShelfSync")
    make_install(layout.root, KEYS, {version: None for version in versions})
    paths = data_paths(tmp_path)
    links = FakeLinks()
    links.table[str(layout.current)] = layout.version_dir(current)
    clock = FakeClock()
    rig = Rig(layout, paths, links, FakeProcesses(), FakeLock(), MemoryUninstallEntry(), ScriptedHealth(), clock, KEYS)
    rig.spawn_targets = []

    def on_spawn(argv: list[str], cwd: Path) -> FakeProc:
        version = rig.current or "?"
        rig.spawn_targets.append((argv, version))
        hook = rig.on_start.get(version)
        if callable(hook) and "--background" in argv:
            hook()
        return FakeProc(rig.exit_codes.get(version) if "--background" in argv else None)

    rig.procs.on_spawn = on_spawn
    rig.procs.images[OLD_PID] = str(layout.interpreter(current))  # if the old copy is running, it is `<from>`'s Python
    rig.store.update(lambda state: _with(state, installed=current, previous=previous))
    return rig


def _with(state: object, **changes: object) -> object:
    from dataclasses import replace

    return replace(state, **changes)  # type: ignore[type-var]


# ---- the happy path ----------------------------------------------------------------------------------------------


def test_an_install_moves_current_starts_the_new_version_and_opens_a_tab(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.1")
    result = run_switch(rig.plan("install", "0.0.1", "0.0.2"), rig.env)
    assert (result.outcome, result.reason) == ("updated", None)
    assert rig.current == "0.0.2"
    assert rig.uninstall.display_version == "0.0.2"
    assert rig.launches() == [("0.0.2", True), ("0.0.2", False)]  # the background start, then the plain launcher
    background = rig.procs.spawned[0][0]
    assert background == [str(rig.layout.current_interpreter), "-m", "shelfsync.launcher", "--background"]
    assert rig.lock.acquired == 1 and rig.lock.released == 1 and not rig.lock.held
    state = rig.store.load()
    assert (state.installed, state.previous, state.pending) == ("0.0.2", "0.0.1", None)
    assert state.switch is not None and state.switch.to_version == "0.0.2"
    assert rig.result == result
    assert not rig.links.exists(rig.layout.current_old) and not rig.links.exists(rig.layout.current_next)


def test_both_versions_are_kept_and_older_ones_and_their_manifests_are_pruned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.0", "0.0.1", "0.0.2"), "0.0.1")
    (rig.layout.versions / ".incoming-0.0.3").mkdir()
    (rig.layout.versions / "notes").mkdir()
    run_switch(rig.plan("install", "0.0.1", "0.0.2"), rig.env)
    assert sorted(p.name for p in rig.layout.versions.iterdir()) == ["0.0.1", "0.0.2", "notes"]
    assert sorted(p.name for p in rig.layout.manifests.iterdir()) == [
        "0.0.1.json",
        "0.0.1.json.sig",
        "0.0.2.json",
        "0.0.2.json.sig",
    ]


def test_the_health_check_names_the_target_versions_own_programs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.1")
    run_switch(rig.plan("install", "0.0.1", "0.0.2"), rig.env)
    version, pid, images = rig.health.calls[0]
    assert version == "0.0.2" and pid == rig.procs.spawned[0][2].pid
    assert images == version_images(rig.layout, "0.0.2")
    assert all("0.0.2" in image for image in images) and len(images) == 2


def test_a_stable_check_runs_again_after_five_seconds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.1")
    start = rig.clock.now
    run_switch(rig.plan("install", "0.0.1", "0.0.2"), rig.env)
    assert rig.clock.now - start >= switch.STABLE_SECONDS
    assert len(rig.health.calls) == 2  # healthy once, and again at the end of the wait


def test_a_child_that_is_healthy_and_then_not_is_a_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.1")
    rig.health.script["0.0.2"] = [None, "no_answer"]
    result = run_switch(rig.plan("install", "0.0.1", "0.0.2"), rig.env)
    assert (result.outcome, result.reason) == ("kept_old", "no_answer")


# ---- each way the new version can fail ----------------------------------------------------------------------------


@pytest.mark.parametrize("reason", ["no_answer", "wrong_version", "untrusted_listener"])
def test_a_failed_health_check_switches_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reason: str) -> None:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.1")
    rig.health.script["0.0.2"] = [reason]
    result = run_switch(rig.plan("install", "0.0.1", "0.0.2"), rig.env)
    assert (result.outcome, result.reason) == ("kept_old", reason)
    assert rig.current == "0.0.1" and rig.uninstall.display_version == "0.0.1"
    new_child = rig.procs.spawned[0][2]
    assert new_child.terminated  # its own child, ended
    assert rig.launches() == [("0.0.2", True), ("0.0.1", True), ("0.0.1", False)]
    state = rig.store.load()
    assert (state.installed, state.previous, state.switch) == ("0.0.1", None, None)
    assert rig.layout.version_dir("0.0.2").is_dir()  # nothing is deleted on a failure
    assert rig.clock.now - 1000.0 >= switch.HEALTH_WITHIN_SECONDS  # it waited the full 60 s for an answer


@pytest.mark.parametrize(("code", "reason"), [(2, "migration_failed"), (1, "exited"), (0, "exited"), (-11, "exited")])
def test_a_child_that_exits_is_a_failure_without_waiting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: int, reason: str
) -> None:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.1")
    rig.exit_codes["0.0.2"] = code
    result = run_switch(rig.plan("install", "0.0.1", "0.0.2"), rig.env)
    assert (result.outcome, result.reason) == ("kept_old", reason)
    assert rig.current == "0.0.1"
    assert rig.clock.now - 1000.0 < switch.HEALTH_WITHIN_SECONDS


def test_a_child_that_dies_during_the_stable_wait_is_a_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.1")
    original = rig.clock.sleep
    state = {"n": 0}

    def sleeping(seconds: float) -> None:
        original(seconds)
        state["n"] += 1
        if state["n"] == 3 and rig.procs.spawned:
            rig.procs.spawned[0][2].exit_code = 1  # it crashes while the 5 s run

    env = rig.env
    env.sleep = sleeping
    result = run_switch(rig.plan("install", "0.0.1", "0.0.2"), env)
    assert (result.outcome, result.reason) == ("kept_old", "exited")


def test_the_old_version_failing_too_leaves_current_on_it_and_says_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.1")
    rig.health.script["0.0.2"] = ["no_answer"]
    rig.health.script["0.0.1"] = ["no_answer"]
    result = run_switch(rig.plan("install", "0.0.1", "0.0.2"), rig.env)
    assert (result.outcome, result.reason) == ("failed", "no_answer")
    assert rig.current == "0.0.1"
    assert rig.launches() == [("0.0.2", True), ("0.0.1", True)]  # no tab for a copy that doesn't answer
    assert rig.procs.spawned[1][2].terminated


def test_a_child_whose_runtime_pid_is_another_process_of_the_target_is_ended_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.1")
    rig.health.script["0.0.2"] = ["no_answer"]
    write_runtime_json(rig.paths, 47615, 777)
    images = version_images(rig.layout, "0.0.2")
    env = rig.env
    env.image_of = lambda pid: str(rig.layout.interpreter("0.0.2")) if pid == 777 else None
    rig.procs.running.add(777)
    run_switch(rig.plan("install", "0.0.1", "0.0.2"), env)
    assert rig.procs.terminated_pids == [777] and images


def test_an_unrelated_runtime_pid_is_never_ended(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.1")
    rig.health.script["0.0.2"] = ["no_answer"]
    write_runtime_json(rig.paths, 47615, 777)
    env = rig.env
    env.image_of = lambda pid: r"C:\Windows\notepad.exe"
    run_switch(rig.plan("install", "0.0.1", "0.0.2"), env)
    assert rig.procs.terminated_pids == []


# ---- the database --------------------------------------------------------------------------------------------------


def rig_with_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Rig, Path]:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.1")
    database_at_release_one(rig.paths, migrations(tmp_path))
    return rig, migrations(tmp_path, TWO)


def new_version_migrates(rig: Rig, folder: Path) -> object:
    def hook() -> None:
        connection = connect(rig.paths.database)
        migrate_with_backup(connection, rig.paths, folder, now=lambda: LATE)
        connection.close()

    return hook


def test_a_failed_start_after_a_migration_restores_the_backup_before_the_old_version_starts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig, folder = rig_with_database(tmp_path, monkeypatch)
    rig.on_start["0.0.2"] = new_version_migrates(rig, folder)
    rig.health.script["0.0.2"] = ["no_answer"]
    seen: list[set[int]] = []

    def old_starts() -> None:
        seen.append(versions_of(rig.paths.database))

    rig.on_start["0.0.1"] = old_starts
    result = run_switch(rig.plan("install", "0.0.1", "0.0.2"), rig.env)
    assert result.outcome == "kept_old"
    assert seen == [{1}]  # the old version found release 1's database, not one it would refuse
    check = sqlite3.connect(rig.paths.database)
    assert check.execute("SELECT value_json FROM setting WHERE key = 'theme'").fetchone() == ('"dark"',)
    check.close()


def test_a_start_that_exits_2_after_the_app_restored_its_own_database_needs_no_second_restore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig, _ = rig_with_database(tmp_path, monkeypatch)
    rig.exit_codes["0.0.2"] = 2  # the new version's own start-up already restored and recorded nothing newer
    result = run_switch(rig.plan("install", "0.0.1", "0.0.2"), rig.env)
    assert (result.outcome, result.reason) == ("kept_old", "migration_failed")
    assert versions_of(rig.paths.database) == {1}


def test_a_backup_that_cannot_be_restored_is_reported_and_the_old_version_is_tried_anyway(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig, folder = rig_with_database(tmp_path, monkeypatch)
    rig.on_start["0.0.2"] = new_version_migrates(rig, folder)
    rig.health.script["0.0.2"] = ["no_answer"]
    record = rig.store.load()
    # break the backup once the new version has made it
    original = rig.on_start["0.0.2"]

    def break_it() -> None:
        assert callable(original)
        original()
        saved = rig.store.load().backup
        assert saved is not None
        Path(saved.path).write_bytes(b"corrupt" * 50)

    rig.on_start["0.0.2"] = break_it
    result = run_switch(rig.plan("install", "0.0.1", "0.0.2"), rig.env)
    assert result.reason is not None and result.reason.startswith("no_answer+backup_invalid")
    assert record is not None


def test_a_rollback_without_a_database_change_keeps_the_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.2", previous="0.0.1")
    database_at_release_one(rig.paths, migrations(tmp_path))
    before = rig.paths.database.read_bytes()
    result = run_switch(rig.plan("rollback", "0.0.2", "0.0.1"), rig.env)
    assert (result.outcome, result.reason) == ("rolled_back", None)
    assert rig.current == "0.0.1" and rig.uninstall.display_version == "0.0.1"
    assert rig.paths.database.read_bytes() == before  # not touched
    state = rig.store.load()
    assert (state.installed, state.previous) == ("0.0.1", None)
    # the version the switcher ran from stays (a roll back never deletes the folder its own program is in)
    assert sorted(p.name for p in rig.layout.versions.iterdir()) == ["0.0.1", "0.0.2"]
    assert rig.layout.manifest_path("0.0.2").is_file()


def test_a_rollback_after_a_migration_restores_the_backup_before_the_old_version_starts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.2", previous="0.0.1")
    database_at_release_one(rig.paths, migrations(tmp_path))
    folder = migrations(tmp_path, TWO)
    connection = connect(rig.paths.database)
    migrate_with_backup(connection, rig.paths, folder, now=lambda: LATE)  # what 0.0.2's start-up did
    connection.close()
    assert versions_of(rig.paths.database) == {1, 2}
    seen: list[set[int]] = []
    rig.on_start["0.0.1"] = lambda: seen.append(versions_of(rig.paths.database))
    result = run_switch(rig.plan("rollback", "0.0.2", "0.0.1", restore=True), rig.env)
    assert result.outcome == "rolled_back"
    assert seen == [{1}]
    assert rig.store.load().backup is None  # used up


def test_a_rollback_that_needs_a_backup_and_has_none_changes_nothing_and_restarts_the_current_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.2", previous="0.0.1")
    database_at_release_one(rig.paths, migrations(tmp_path))
    connection = connect(rig.paths.database)
    migrate(connection, migrations(tmp_path, TWO))  # the database is at schema 2 and no backup was recorded
    connection.close()
    result = run_switch(rig.plan("rollback", "0.0.2", "0.0.1", restore=True), rig.env)
    assert (result.outcome, result.reason) == ("not_switched", "backup_missing")
    assert rig.current == "0.0.2"
    assert rig.launches() == [("0.0.2", True), ("0.0.2", False)]  # the copy that quit is started again


# ---- refusing before anything changes ------------------------------------------------------------------------------


def test_an_old_copy_that_will_not_quit_changes_nothing_and_starts_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.1")
    rig.procs.running.add(OLD_PID)
    rig.lock.busy_for = 10**6  # the old copy still holds the instance lock, as a running copy does
    result = run_switch(rig.plan("install", "0.0.1", "0.0.2"), rig.env)
    assert (result.outcome, result.reason) == ("not_switched", "old_copy_still_running")
    assert rig.current == "0.0.1" and rig.procs.spawned == [] and rig.links.log == []
    assert rig.clock.now - 1000.0 >= switch.WAIT_FOR_QUIT_SECONDS
    assert rig.lock.acquired == 0
    assert rig.uninstall.display_version is None


def test_an_old_copy_that_quits_late_is_waited_for(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.1")
    rig.procs.running.add(OLD_PID)
    original = rig.clock.sleep
    state = {"n": 0}

    def sleeping(seconds: float) -> None:
        original(seconds)
        state["n"] += 1
        if state["n"] == 40:  # about 20 s
            rig.procs.running.discard(OLD_PID)

    env = rig.env
    env.sleep = sleeping
    assert run_switch(rig.plan("install", "0.0.1", "0.0.2"), env).outcome == "updated"


def test_a_lock_that_stays_taken_aborts_and_restarts_nothing_of_its_own(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.1")
    rig.lock.busy_for = 10_000
    result = run_switch(rig.plan("install", "0.0.1", "0.0.2"), rig.env)
    assert (result.outcome, result.reason) == ("not_switched", "lock_busy")
    assert rig.procs.spawned == [] and rig.current == "0.0.1"  # another copy started in the gap: it is the one running


def test_a_lock_taken_for_a_moment_is_waited_for(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.1")
    rig.lock.busy_for = 3
    assert run_switch(rig.plan("install", "0.0.1", "0.0.2"), rig.env).outcome == "updated"


def test_a_tampered_target_is_refused_and_the_old_version_is_started_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.1")
    (rig.layout.version_dir("0.0.2") / "python.exe").write_bytes(b"malware" * 3)
    result = run_switch(rig.plan("install", "0.0.1", "0.0.2"), rig.env)
    assert (result.outcome, result.reason) == ("not_switched", "files_changed")
    assert rig.current == "0.0.1"
    assert rig.launches() == [("0.0.1", True), ("0.0.1", False)]
    assert rig.links.log == []  # no link was touched


def test_a_tampered_previous_folder_is_refused_for_a_rollback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.2", previous="0.0.1")
    (rig.layout.version_dir("0.0.1") / "shelfsync" / "__init__.py").write_text("evil", encoding="utf-8")
    result = run_switch(rig.plan("rollback", "0.0.2", "0.0.1"), rig.env)
    assert (result.outcome, result.reason) == ("not_switched", "files_changed")
    assert rig.current == "0.0.2" and rig.launches() == [("0.0.2", True), ("0.0.2", False)]


def test_a_manifest_that_is_missing_or_unsigned_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.1")
    rig.layout.manifest_path("0.0.2").unlink()
    assert run_switch(rig.plan("install", "0.0.1", "0.0.2"), rig.env).reason == "manifest_missing"
    rig = make_rig(tmp_path / "b", monkeypatch, ("0.0.1", "0.0.2"), "0.0.1")
    rig.layout.signature_path("0.0.2").write_bytes(b"\x00" * 64)
    assert run_switch(rig.plan("install", "0.0.1", "0.0.2"), rig.env).reason == "manifest_invalid"


def test_with_no_key_in_the_build_nothing_is_switched(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.1")
    use_key(monkeypatch, None)
    assert run_switch(rig.plan("install", "0.0.1", "0.0.2"), rig.env).reason == "no_key"
    assert rig.current == "0.0.1"


def test_a_downgrade_by_install_and_an_unknown_rollback_target_are_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.2", previous=None)
    assert run_switch(rig.plan("install", "0.0.2", "0.0.1"), rig.env).reason == "target_invalid"
    assert (
        run_switch(rig.plan("rollback", "0.0.2", "0.0.1"), rig.env).reason == "target_invalid"
    )  # state names no previous
    assert rig.current == "0.0.2"


def test_current_must_really_be_the_from_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2", "0.0.3"), "0.0.1")
    result = run_switch(rig.plan("install", "0.0.2", "0.0.3"), rig.env)
    assert (result.outcome, result.reason) == ("not_switched", "from_mismatch")
    assert rig.current == "0.0.1"


# ---- faults ----------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("fail_at", [1, 2, 3, 4])
def test_a_fault_at_each_step_of_the_link_swap_leaves_current_on_the_old_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fail_at: int
) -> None:
    """create `current.next`, rename `current` away, rename `current.next` into place, remove `current.old`. A fault
    after any of them is undone in the same process; the old version is started again."""
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.1")
    rig.links.fail_at = fail_at
    result = run_switch(rig.plan("install", "0.0.1", "0.0.2"), rig.env)
    # even when the swap had finished and only `current.old` couldn't be removed, the switch ends on the old version
    assert rig.current == "0.0.1"
    assert result.outcome in ("not_switched", "kept_old")
    assert rig.links.exists(rig.layout.current)
    assert not rig.links.exists(rig.layout.current_next)
    assert rig.launches() and rig.launches()[0][1]  # something was started: the owner is never left with nothing


def test_between_the_two_renames_the_next_start_repairs_current_from_the_old_link(tmp_path: Path) -> None:
    """A switch killed after `current` was renamed away and before `current.next` took its place."""
    layout = InstallLayout(tmp_path / "root")
    (layout.versions / "0.0.1").mkdir(parents=True)
    (layout.versions / "0.0.2").mkdir()
    links = FakeLinks()
    links.table[str(layout.current_old)] = layout.version_dir("0.0.1")
    links.table[str(layout.current_next)] = layout.version_dir("0.0.2")
    assert repair_current(layout, links) is True
    assert current_version(layout, links) == "0.0.1"  # the version that was running
    assert not links.exists(layout.current_next) and not links.exists(layout.current_old)


def test_repair_uses_current_next_when_that_is_all_there_is(tmp_path: Path) -> None:
    layout = InstallLayout(tmp_path / "root")
    (layout.versions / "0.0.2").mkdir(parents=True)
    links = FakeLinks()
    links.table[str(layout.current_next)] = layout.version_dir("0.0.2")
    assert repair_current(layout, links) is True and current_version(layout, links) == "0.0.2"


def test_repair_clears_leftovers_when_current_is_fine_and_does_nothing_otherwise(tmp_path: Path) -> None:
    layout = InstallLayout(tmp_path / "root")
    (layout.versions / "0.0.1").mkdir(parents=True)
    links = FakeLinks()
    assert repair_current(layout, links) is False  # nothing at all
    links.table[str(layout.current)] = layout.version_dir("0.0.1")
    assert repair_current(layout, links) is False
    links.table[str(layout.current_old)] = layout.version_dir("0.0.1")
    assert repair_current(layout, links) is True and not links.exists(layout.current_old)


def test_a_switch_repairs_a_current_left_missing_by_an_earlier_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.1")
    target = rig.links.table.pop(str(rig.layout.current))
    rig.links.table[str(rig.layout.current_old)] = target
    assert run_switch(rig.plan("install", "0.0.1", "0.0.2"), rig.env).outcome == "updated"


def test_repoint_failures_undo_themselves_and_raise(tmp_path: Path) -> None:
    layout = InstallLayout(tmp_path / "root")
    for version in ("0.0.1", "0.0.2"):
        (layout.versions / version).mkdir(parents=True)
    for fail_at in (1, 2, 3):
        links = FakeLinks()
        links.table[str(layout.current)] = layout.version_dir("0.0.1")
        links.fail_at = fail_at
        with pytest.raises(LinkError):
            repoint(layout, links, "0.0.2")
        assert current_version(layout, links) == "0.0.1", fail_at


def test_a_repair_that_also_fails_is_logged_and_the_original_error_is_raised(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    layout = InstallLayout(tmp_path / "root")
    for version in ("0.0.1", "0.0.2"):
        (layout.versions / version).mkdir(parents=True)

    class Dying(FakeLinks):
        def rename(self, source: Path, destination: Path) -> None:
            if str(destination) in (str(layout.current_old), str(layout.current)) and self.calls >= 2:
                raise LinkError("always")
            super().rename(source, destination)

    links = Dying()
    links.table[str(layout.current)] = layout.version_dir("0.0.1")
    with pytest.raises(LinkError):
        repoint(layout, links, "0.0.2")


def test_a_link_error_while_repairing_at_the_start_is_a_clean_stop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.1")
    rig.links.table[str(rig.layout.current_next)] = rig.layout.version_dir("0.0.2")  # a leftover to remove
    rig.links.fail_at = 1  # and the removal fails
    result = run_switch(rig.plan("install", "0.0.1", "0.0.2"), rig.env)
    assert (result.outcome, result.reason) == ("not_switched", "junction_error")
    # nothing was switched, but the old copy had been asked to quit: what `current` points at is started again
    assert rig.current == "0.0.1" and rig.launches() == [("0.0.1", True), ("0.0.1", False)]


def test_prune_never_touches_names_that_are_not_versions_or_links_it_cannot_follow(tmp_path: Path) -> None:
    layout = InstallLayout(tmp_path / "root")
    for name in ("0.0.1", "0.0.2", "0.0.3", ".incoming-0.0.9", "readme"):
        (layout.versions / name).mkdir(parents=True, exist_ok=True)
    layout.manifests.mkdir(parents=True)
    for name in ("0.0.1.json", "0.0.1.json.sig", "0.0.3.json", "notes.txt"):
        (layout.manifests / name).write_text("x", encoding="utf-8")
    prune_versions(layout, {"0.0.1", "0.0.2"})
    assert sorted(p.name for p in layout.versions.iterdir()) == ["0.0.1", "0.0.2", "readme"]
    assert sorted(p.name for p in layout.manifests.iterdir()) == ["0.0.1.json", "0.0.1.json.sig", "notes.txt"]
    prune_versions(InstallLayout(tmp_path / "nothing"), set())


def test_current_version_needs_a_link_into_the_versions_folder(tmp_path: Path) -> None:
    layout = InstallLayout(tmp_path / "root")
    links = FakeLinks()
    assert current_version(layout, links) is None
    links.table[str(layout.current)] = tmp_path / "elsewhere" / "0.0.1"
    assert current_version(layout, links) is None
    links.table[str(layout.current)] = layout.versions / "not-a-version"
    assert current_version(layout, links) is None


# ---- the health probe (the real one, with the owner check and the network faked) -----------------------------------


def probe_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, verdict: Verdict, health: httpx.Response | Exception
) -> tuple[HealthProbe, DataPaths]:
    paths = data_paths(tmp_path)
    write_runtime_json(paths, 47615, 99)
    monkeypatch.setattr(switch, "check_listener", lambda port, pid, expected=None, **k: verdict)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "127.0.0.1" and "authorization" not in request.headers  # never the install token
        if isinstance(health, Exception):
            raise health
        return health

    monkeypatch.setattr(
        switch, "make_client", lambda: httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)
    )
    return HealthProbe(), paths


GOOD = httpx.Response(200, json={"app": "shelfsync", "version": "0.0.2"})


def test_the_real_probe_accepts_only_the_trusted_target_that_reports_its_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe, paths = probe_setup(tmp_path, monkeypatch, Verdict.TRUSTED, GOOD)
    assert probe.probe(paths, 99, "0.0.2", frozenset()) is None
    assert probe.probe(paths, 98, "0.0.2", frozenset()) == "no_answer"  # runtime.json names another pid
    assert probe.probe(paths, 99, "0.0.3", frozenset()) == "wrong_version"


@pytest.mark.parametrize(
    ("verdict", "reason"),
    [
        (Verdict.NOBODY, "no_answer"),
        (Verdict.LOOKUP_FAILED, "no_answer"),
        (Verdict.OTHER_USER, "untrusted_listener"),
        (Verdict.OTHER_PROGRAM, "untrusted_listener"),
        (Verdict.STALE_PID, "untrusted_listener"),
    ],
)
def test_the_real_probe_maps_the_owner_checks_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, verdict: Verdict, reason: str
) -> None:
    probe, paths = probe_setup(tmp_path, monkeypatch, verdict, GOOD)
    assert probe.probe(paths, 99, "0.0.2", frozenset()) == reason


@pytest.mark.parametrize(
    "health",
    [
        httpx.ConnectError("no"),
        httpx.Response(500),
        httpx.Response(200, json={"app": "other", "version": "0.0.2"}),
        httpx.Response(200, content=b"not json"),
        httpx.Response(200, json=[1]),
    ],
)
def test_the_real_probe_needs_a_real_answer_from_shelfsync(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, health: httpx.Response | Exception
) -> None:
    probe, paths = probe_setup(tmp_path, monkeypatch, Verdict.TRUSTED, health)
    assert probe.probe(paths, 99, "0.0.2", frozenset()) == "no_answer"


def test_the_real_probe_without_a_runtime_file_has_no_answer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    probe, paths = probe_setup(tmp_path, monkeypatch, Verdict.TRUSTED, GOOD)
    paths.runtime_json.unlink()
    assert probe.probe(paths, 99, "0.0.2", frozenset()) == "no_answer"


# ---- the command line and the install token ------------------------------------------------------------------------


def test_the_switch_never_reads_or_sends_the_install_token() -> None:
    source = inspect.getsource(switch)
    for word in ("SecretStore", "INSTALL_TOKEN", "InstallToken", "Authorization", "keyring", "secrets"):
        assert word not in source.replace("shelfsync.update.state", ""), word


GOOD_ARGS = [
    "--format", "1", "--mode", "install", "--from", "0.0.1", "--to", "0.0.2",
    "--install-root", "{root}", "--data-dir", "{data}", "--old-pid", "4242",
]  # fmt: skip


def argv(tmp_path: Path, **changes: str) -> list[str]:
    values = list(GOOD_ARGS)
    for flag, value in changes.items():
        values[values.index("--" + flag.replace("_", "-")) + 1] = value
    return [v.format(root=tmp_path / "root", data=tmp_path / "data") for v in values]


@pytest.mark.parametrize(
    "changes",
    [
        {"format": "2"},
        {"mode": "sideways"},
        {"from_": "x"},
        {"to": "0.0.01"},
        {"old_pid": "0"},
        {"old_pid": "-5"},
        {"old_pid": "abc"},
        {"install_root": "relative"},
        {"data_dir": "relative"},
        {"to": "0.0.1"},
    ],
)
def test_bad_arguments_are_refused(tmp_path: Path, changes: dict[str, str]) -> None:
    arguments = argv(tmp_path, **{k.rstrip("_"): v for k, v in changes.items() if k != "from_"})
    if "from_" in changes:
        arguments = [("x" if a == "0.0.1" else a) for a in arguments]
    assert main(arguments) == switch.EXIT_BAD_ARGUMENTS


def test_a_missing_argument_is_refused(tmp_path: Path) -> None:
    assert main(argv(tmp_path)[:-2]) == switch.EXIT_BAD_ARGUMENTS
    assert main([]) == switch.EXIT_BAD_ARGUMENTS
    assert main([*argv(tmp_path), "--surprise"]) == switch.EXIT_BAD_ARGUMENTS


def test_main_runs_the_switch_and_reports_its_outcome_as_the_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    results = {"updated": 0, "rolled_back": 0, "kept_old": 1, "not_switched": 1, "failed": 2}
    for outcome, code in results.items():
        monkeypatch.setattr(
            switch,
            "run_switch",
            lambda plan, env=None, outcome=outcome: SwitchResult("install", "0.0.1", "0.0.2", outcome, None, "t"),
        )
        assert main(argv(tmp_path)) == code
    plan_seen: list[SwitchPlan] = []

    def capture(plan: SwitchPlan, env: object = None) -> SwitchResult:
        plan_seen.append(plan)
        return SwitchResult("install", "0.0.1", "0.0.2", "updated", None, "t")

    monkeypatch.setattr(switch, "run_switch", capture)
    assert main([*argv(tmp_path), "--restore-backup"]) == 0
    assert plan_seen[0].restore_backup and plan_seen[0].old_pid == 4242
    assert plan_seen[0].layout.root == tmp_path / "root" and plan_seen[0].paths.root == tmp_path / "data"


def test_an_unexpected_error_is_logged_and_exits_failed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(plan: object, env: object = None) -> SwitchResult:
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(switch, "run_switch", boom)
    assert main(argv(tmp_path)) == switch.EXIT_FAILED


def test_an_installed_switch_works_on_its_own_install_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(switch, "installed_root", lambda: tmp_path / "somewhere-else")
    assert main(argv(tmp_path)) == switch.EXIT_BAD_ARGUMENTS
    monkeypatch.setattr(
        switch, "run_switch", lambda plan, env=None: SwitchResult("install", "0.0.1", "0.0.2", "updated", None, "t")
    )
    monkeypatch.setattr(switch, "installed_root", lambda: tmp_path / "root")
    assert main(argv(tmp_path)) == 0


def test_the_result_file_is_plain_json_with_fixed_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.1")
    run_switch(rig.plan("install", "0.0.1", "0.0.2"), rig.env)
    written = json.loads(UpdatePaths(rig.paths).result_json.read_text(encoding="utf-8"))
    assert set(written) == {"format", "mode", "from_version", "to_version", "outcome", "reason", "at"}
