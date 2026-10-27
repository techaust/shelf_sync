"""The reviewer's follow-ups on m1b.2 (run file section 5), one group per item."""

import importlib
import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from shelfsync import __version__
from shelfsync.update import release_key
from shelfsync.update.layout import UpdatePaths, installed_root, resolve_install_layout
from shelfsync.update.manifest import verify_and_parse
from shelfsync.update.state import CHECK_OUTCOMES, PendingUpdate, State, StateStore, state_from_json, state_to_json
from shelfsync.update.switch import run_switch
from tests.support import WRITE_HEADERS  # noqa: F401  (kept for readers of the API test below)
from tests.test_update_api import development_harness
from tests.test_update_service import make_rig as make_service_rig
from tests.test_update_switch import KEYS, make_rig
from tests.update_support import build_release, data_paths, make_install, make_keys

TOOLS = Path(__file__).resolve().parents[1] / "tools" / "release"


# ---- 3. a roll back keeps a pending download; a pending one with nothing behind it is dropped -----


def test_a_rollback_keeps_the_folder_and_manifest_of_a_pending_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.1", "0.0.2"), "0.0.2", previous="0.0.1")
    make_install(rig.layout.root, KEYS, {"0.0.3": None})  # downloaded and verified, waiting for the owner's go-ahead
    pending = PendingUpdate("0.0.3", str(rig.layout.version_dir("0.0.3")), "2026-10-27T12:00:00.000000Z")
    rig.store.update(lambda s: replace(s, pending=pending))
    assert run_switch(rig.plan("rollback", "0.0.2", "0.0.1"), rig.env).outcome == "rolled_back"
    assert rig.layout.version_dir("0.0.3").is_dir() and rig.layout.manifest_path("0.0.3").is_file()
    assert rig.layout.signature_path("0.0.3").is_file()
    assert rig.store.load().pending == pending  # and it is still offered


def test_an_install_still_prunes_everything_but_the_two_versions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch, ("0.0.0", "0.0.1", "0.0.2"), "0.0.1")
    run_switch(rig.plan("install", "0.0.1", "0.0.2"), rig.env)
    assert sorted(p.name for p in rig.layout.versions.iterdir()) == ["0.0.1", "0.0.2"]


@pytest.mark.parametrize("missing", ["folder", "manifest", "signature"])
def test_a_pending_update_whose_files_are_gone_is_dropped_at_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    rig = make_service_rig(tmp_path, monkeypatch, latest=None, extra_versions=("0.0.2",))
    pending = PendingUpdate("0.0.2", str(rig.layout.version_dir("0.0.2")), "t")
    rig.store.update(lambda s: replace(s, pending=pending))
    rig.service.start()
    rig.service.stop()
    assert rig.store.load().pending == pending  # all three are there: kept
    if missing == "folder":
        import shutil

        shutil.rmtree(rig.layout.version_dir("0.0.2"))
    elif missing == "manifest":
        rig.layout.manifest_path("0.0.2").unlink()
    else:
        rig.layout.signature_path("0.0.2").unlink()
    rig.service.start()
    rig.service.stop()
    assert rig.store.load().pending is None
    assert rig.service.status().available is None


# ---- 4. sign.py signs the bytes it showed ---------------------------------------------------------


@pytest.fixture
def tools(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(TOOLS))
    loaded = {name: importlib.import_module(name) for name in ("keyfile", "keygen", "sign")}
    yield loaded
    for name in loaded:
        sys.modules.pop(name, None)


def test_sign_signs_exactly_the_bytes_the_owner_was_shown(
    tools, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key_path = tmp_path / "key.pem"
    public, _ = tools["keygen"].generate(key_path, "correct horse battery staple 42")
    monkeypatch.setattr(release_key, "PUBLIC_KEY", bytes.fromhex(public))
    release = build_release("0.1.2", make_keys(1))
    manifest = tmp_path / "manifest.json"
    manifest.write_bytes(release.manifest_bytes)

    def swapped_while_the_prompt_is_open(prompt: str = "") -> str:
        other = build_release("0.1.3", make_keys(1))
        manifest.write_bytes(other.manifest_bytes)  # the file changes after it was shown
        return "y"

    monkeypatch.setattr("builtins.input", swapped_while_the_prompt_is_open)
    monkeypatch.setattr(tools["sign"].getpass, "getpass", lambda prompt="": "correct horse battery staple 42")
    assert tools["sign"].main([str(manifest), str(key_path)]) == 0
    signature = (tmp_path / "manifest.json.sig").read_bytes()
    assert verify_and_parse(release.manifest_bytes, signature).version == "0.1.2"  # what was shown
    from shelfsync.update.manifest import ManifestError

    with pytest.raises(ManifestError):
        verify_and_parse(manifest.read_bytes(), signature)  # not the file that is on disk now


# ---- 5. a damaged last_check can never make GET /api/updates fail ---------------------------------


@pytest.mark.parametrize("outcome", ["exploded", "", 5, None, ["ok"], "OK"])
def test_an_unknown_last_check_outcome_is_dropped_not_a_500(tmp_path: Path, outcome: object) -> None:
    paths = UpdatePaths(data_paths(tmp_path))
    document = state_to_json(State(installed="0.0.2"))
    document["last_check"] = {"at": "2026-10-27T12:00:00.000000Z", "outcome": outcome, "detail": None}
    paths.root.mkdir(parents=True, exist_ok=True)
    paths.state_json.write_text(json.dumps(document), encoding="utf-8")
    state = StateStore(paths).load()
    assert state.last_check is None and state.installed == "0.0.2"  # the rest of the file is trusted as before
    assert paths.state_json.exists()  # and nothing was set aside for this
    assert state_from_json(document).last_check is None


def test_every_known_outcome_survives_a_round_trip() -> None:
    for outcome in CHECK_OUTCOMES:
        document = state_to_json(State())
        document["last_check"] = {"at": "t", "outcome": outcome, "detail": None}
        assert state_from_json(document).last_check is not None


def test_get_updates_answers_200_with_a_damaged_state_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.support import make_harness

    rig = make_service_rig(tmp_path, monkeypatch, latest=None)
    document = state_to_json(State(installed="0.0.1"))
    document["last_check"] = {"at": "t", "outcome": "exploded", "detail": None}
    UpdatePaths(rig.paths).root.mkdir(parents=True, exist_ok=True)
    UpdatePaths(rig.paths).state_json.write_text(json.dumps(document), encoding="utf-8")
    response = make_harness(updates=rig.service).signed_in_client().get("/api/updates")
    assert response.status_code == 200 and response.json()["last_check"] is None


# ---- 6. an installed copy's folder is named for its own version -----------------------------------


def test_a_copy_in_a_versions_folder_with_another_name_is_not_installed(tmp_path: Path) -> None:
    right = tmp_path / "Programs" / "ShelfSync" / "versions" / __version__
    wrong = tmp_path / "Programs" / "ShelfSync" / "versions" / "9.9.9"
    for folder in (right, wrong):
        folder.mkdir(parents=True)
        (folder / "pythonw.exe").write_bytes(b"x")
    root = tmp_path / "Programs" / "ShelfSync"
    assert installed_root(str(right / "pythonw.exe")) == root
    assert installed_root(str(wrong / "pythonw.exe")) is None
    # not installed means SHELFSYNC_INSTALL_DIR is honoured (a rehearsal) and otherwise updates are off
    other = tmp_path / "elsewhere"
    assert resolve_install_layout(str(wrong / "pythonw.exe"), {"SHELFSYNC_INSTALL_DIR": str(other)}).root == other  # type: ignore[union-attr]
    assert resolve_install_layout(str(wrong / "pythonw.exe"), {}) is None
    assert resolve_install_layout(str(right / "pythonw.exe"), {"SHELFSYNC_INSTALL_DIR": str(other)}).root == root  # type: ignore[union-attr]


def test_the_development_api_fixture_is_still_development() -> None:
    harness, _, _ = development_harness()
    assert harness.app.state.updates.is_development
