"""04 section 8: the updater's state.json and result.json (atomic writes, nothing unreadable is trusted)."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from shelfsync.update.layout import UpdatePaths
from shelfsync.update.state import (
    BackupRecord,
    LastCheck,
    PendingUpdate,
    ResultStore,
    State,
    StateStore,
    SwitchIntent,
    SwitchResult,
    state_from_json,
    state_to_json,
)
from tests.update_support import data_paths, make_dir_link


def full_state() -> State:
    return State(
        installed="0.0.2",
        previous="0.0.1",
        switched_at="2026-10-27T11:00:00.000000Z",
        pending=PendingUpdate("0.0.3", r"C:\x\versions\0.0.3", "2026-10-27T12:00:00.000000Z"),
        last_check=LastCheck("2026-10-27T12:00:00.000000Z", "update_refused", "bad_signature"),
        backup=BackupRecord(r"C:\x\backups\pre-migration-0001-to-0002-x.db", 1, 2, "2026-10-27T11:00:01.000000Z"),
        switch=SwitchIntent("install", "0.0.1", "0.0.2", "2026-10-27T11:00:00.000000Z"),
        token_expires_at="2026-11-30T10:00:00.000000Z",
    )


def test_the_state_round_trips(tmp_path: Path) -> None:
    store = StateStore(UpdatePaths(data_paths(tmp_path)))
    assert store.load() == State()  # nothing written yet
    store.save(full_state())
    assert store.load() == full_state()
    assert state_from_json(state_to_json(full_state())) == full_state()


def test_update_is_read_modify_write(tmp_path: Path) -> None:
    store = StateStore(UpdatePaths(data_paths(tmp_path)))
    store.save(full_state())
    store.update(lambda s: replace(s, pending=None))
    loaded = store.load()
    assert loaded.pending is None and loaded.installed == "0.0.2" and loaded.backup is not None


def test_a_write_leaves_no_temporary_file(tmp_path: Path) -> None:
    paths = UpdatePaths(data_paths(tmp_path))
    StateStore(paths).save(full_state())
    assert sorted(p.name for p in paths.root.iterdir()) == ["state.json"]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d.update(format=2),
        lambda d: d.update(installed="1.2"),
        lambda d: d.update(previous=5),
        lambda d: d.update(switched_at=["x"]),
        lambda d: d.update(pending="x"),
        lambda d: d["pending"].update(version="bad"),
        lambda d: d["backup"].update(from_schema=-1),
        lambda d: d["backup"].update(to_schema=True),
        lambda d: d["backup"].update(path=None),
        lambda d: d["switch"].update(mode="sideways"),
        lambda d: d.update(installed="9" * 2000),
    ],
)
def test_a_state_of_the_wrong_shape_is_set_aside_and_never_trusted(
    tmp_path: Path, mutation: object, caplog: pytest.LogCaptureFixture
) -> None:
    paths = UpdatePaths(data_paths(tmp_path))
    document = state_to_json(full_state())
    assert callable(mutation)
    mutation(document)
    paths.root.mkdir(parents=True, exist_ok=True)
    paths.state_json.write_text(json.dumps(document), encoding="utf-8")
    assert StateStore(paths).load() == State()
    assert not paths.state_json.exists()
    assert [p.name for p in paths.root.iterdir() if ".bad-" in p.name]
    assert "set aside" in caplog.text


@pytest.mark.parametrize("content", [b"not json", b"\xff\xfe\x00", b"[]", b"", "big"])
def test_an_unreadable_state_is_set_aside(tmp_path: Path, content: bytes | str) -> None:
    paths = UpdatePaths(data_paths(tmp_path))
    paths.root.mkdir(parents=True, exist_ok=True)
    paths.state_json.write_bytes(b"x" * (300 * 1024) if content == "big" else content)  # type: ignore[arg-type]
    assert StateStore(paths).load() == State()
    assert not paths.state_json.exists()


def test_a_link_in_place_of_the_state_is_removed_unread(tmp_path: Path) -> None:
    paths = UpdatePaths(data_paths(tmp_path))
    paths.root.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "state.json").write_text(json.dumps(state_to_json(full_state())), encoding="utf-8")
    make_dir_link(paths.state_json, outside)  # a directory link where the file belongs
    assert StateStore(paths).load() == State()
    assert (outside / "state.json").exists()  # what it pointed at is untouched
    assert not paths.state_json.exists()


def test_a_file_with_two_names_is_not_trusted(tmp_path: Path) -> None:
    paths = UpdatePaths(data_paths(tmp_path))
    paths.root.mkdir(parents=True, exist_ok=True)
    paths.state_json.write_text(json.dumps(state_to_json(full_state())), encoding="utf-8")
    try:
        (paths.root / "second-name").hardlink_to(paths.state_json)
    except OSError:
        pytest.skip("hard links aren't available here")
    assert StateStore(paths).load() == State()


def test_the_result_round_trips_and_a_bad_one_is_set_aside(tmp_path: Path) -> None:
    paths = UpdatePaths(data_paths(tmp_path))
    store = ResultStore(paths)
    assert store.load() is None
    result = SwitchResult("rollback", "0.0.2", "0.0.1", "rolled_back", None, "2026-10-27T12:00:00.000000Z")
    store.save(result)
    assert store.load() == result
    document = json.loads(paths.result_json.read_text(encoding="utf-8"))
    document["outcome"] = "exploded"
    paths.result_json.write_text(json.dumps(document), encoding="utf-8")
    assert store.load() is None and not paths.result_json.exists()
    paths.result_json.write_text("garbage", encoding="utf-8")
    assert store.load() is None
    paths.result_json.write_text(json.dumps({"format": 9}), encoding="utf-8")
    assert store.load() is None
