"""Re-check round 2 of the m1b.2 review (run file section 5), one group per item."""

from pathlib import Path
from typing import get_args

import pytest

from shelfsync.api.updates import CheckOutcome
from shelfsync.paths import DataPaths, write_runtime_json
from shelfsync.update import switch
from shelfsync.update.state import CHECK_OUTCOMES
from shelfsync.update.switch import run_switch, version_images
from tests.test_update_switch import OLD_PID, make_rig

# ---- 1. an old copy that matches but hangs --------------------------------------------------------


def test_an_old_copy_that_matches_but_stays_up_with_the_lock_free_is_hung_and_is_restarted_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.1")
    rig.procs.running.add(OLD_PID)  # its image is `<from>`'s own Python (the rig's default) and it never ends
    result = run_switch(rig.plan("install", "0.0.1", "0.0.2"), rig.env)
    assert (result.outcome, result.reason) == ("not_switched", "old_copy_hung")
    assert rig.clock.now - 1000.0 >= switch.WAIT_FOR_QUIT_SECONDS
    assert rig.links.log == [] and rig.current == "0.0.1"  # no switch
    assert rig.launches() == [("0.0.1", True), ("0.0.1", False)]  # one restart, and the tab
    assert rig.uninstall.display_version is None


# ---- 2. nothing touched and `current` isn't a link into versions ----------------------------------


@pytest.mark.parametrize("where", ["outside", "gone"])
def test_a_current_that_is_not_a_link_into_versions_starts_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, where: str
) -> None:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.1")
    if where == "outside":
        rig.links.table[str(rig.layout.current)] = tmp_path / "somewhere" / "else"
    else:
        del rig.links.table[str(rig.layout.current)]
    result = run_switch(rig.plan("install", "0.0.1", "0.0.2"), rig.env)
    assert result.outcome == "failed" and result.reason == "from_mismatch+junction_error"
    assert rig.procs.spawned == []  # nothing is spawned for a path that isn't a version
    assert rig.lock.released == rig.lock.acquired  # the lock was let go


# ---- 3. a second launch that found a healthy copy already running ---------------------------------


def runtime_names(rig: object, pid: int) -> object:
    paths: DataPaths = rig.paths  # type: ignore[attr-defined]

    def hook() -> None:
        write_runtime_json(paths, 47615, pid)

    return hook


def test_a_child_that_exits_as_a_second_launch_beside_a_healthy_trusted_copy_counts_as_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.1")
    rig.exit_codes["0.0.2"] = 0  # the child found a copy running and left: a second launch
    rig.on_start["0.0.2"] = runtime_names(rig, 777)  # the owner's shortcut started this copy in the gap
    result = run_switch(rig.plan("install", "0.0.1", "0.0.2"), rig.env)
    assert (result.outcome, result.reason) == ("updated", None)
    assert rig.current == "0.0.2"
    assert rig.procs.terminated_pids == [] and not rig.procs.spawned[0][2].terminated  # nothing was ended
    assert (
        next(pid for _, pid, _ in rig.health.calls) == 777
    )  # the other copy was the one checked, with the same checks
    assert all(images == version_images(rig.layout, "0.0.2") for _, _, images in rig.health.calls)


def test_a_second_launch_beside_a_copy_that_is_not_healthy_is_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.1")
    rig.exit_codes["0.0.2"] = 0
    rig.on_start["0.0.2"] = runtime_names(rig, 777)

    class OnlyOthersAreFine(type(rig.health)):  # type: ignore[misc]
        def probe(self, paths: DataPaths, pid: int, version: str, images: frozenset[str]) -> str | None:
            return "untrusted_listener" if pid == 777 else None

    rig.health = OnlyOthersAreFine()
    result = run_switch(rig.plan("install", "0.0.1", "0.0.2"), rig.env)
    assert (result.outcome, result.reason) == ("kept_old", "exited")
    assert rig.current == "0.0.1"


def test_a_child_that_exits_2_is_a_failure_even_if_a_healthy_copy_answers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.1")
    rig.exit_codes["0.0.2"] = 2
    rig.on_start["0.0.2"] = runtime_names(rig, 777)
    result = run_switch(rig.plan("install", "0.0.1", "0.0.2"), rig.env)
    assert (result.outcome, result.reason) == ("kept_old", "migration_failed")


def test_a_copy_that_was_adopted_is_never_ended_even_if_it_fails_later(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.1")
    rig.exit_codes["0.0.2"] = 0
    rig.on_start["0.0.2"] = runtime_names(rig, 777)

    class FailsLater(type(rig.health)):  # type: ignore[misc]
        calls_for_777 = 0

        def probe(self, paths: DataPaths, pid: int, version: str, images: frozenset[str]) -> str | None:
            if pid != 777:
                return None
            self.calls_for_777 += 1
            return None if self.calls_for_777 == 1 else "no_answer"  # healthy at first, gone during the stable wait

    rig.health = FailsLater()
    env = rig.env
    env.image_of = lambda pid: str(rig.layout.interpreter("0.0.2")) if pid == 777 else None  # it looks like the target
    rig.procs.running.add(777)
    result = run_switch(rig.plan("install", "0.0.1", "0.0.2"), env)
    assert result.outcome in ("kept_old", "failed")
    assert rig.procs.terminated_pids == []  # the copy someone else started is not ours to end


# ---- 4. the check outcomes stay in step -----------------------------------------------------------


def test_the_state_files_check_outcomes_are_the_apis(tmp_path: Path) -> None:
    assert set(CHECK_OUTCOMES) == set(get_args(CheckOutcome))
