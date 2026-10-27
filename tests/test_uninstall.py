"""SYS-08: `python -m shelfsync.uninstall --remove-data`: the Credential Manager entries ShelfSync owns, then the data
folder, never following a link. Fakes everywhere; the `windows` checks use a throwaway service name and a real
junction."""

import argparse
import secrets
import subprocess
import sys
from pathlib import Path

import pytest

from shelfsync import uninstall
from shelfsync.paths import DataPaths
from shelfsync.platform.secrets import OWNED_SECRET_NAMES, MemorySecretStore, SecretStoreError
from shelfsync.secure.token import INSTALL_TOKEN_NAME
from shelfsync.tray.instance import FakeInstanceLock


def make_data(tmp_path: Path) -> DataPaths:
    root = tmp_path / "ShelfSync"
    for folder in ("logs", "backups", "tmp"):
        (root / folder).mkdir(parents=True)
    (root / "shelfsync.db").write_text("db", encoding="utf-8")
    (root / "logs" / "shelfsync.log").write_text("log", encoding="utf-8")
    return DataPaths(root)


def make_link(link: Path, target: Path) -> bool:
    """A directory link: a junction on Windows, a symlink elsewhere. False if the account can't make one."""
    if sys.platform == "win32":
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, check=False)
        return result.returncode == 0
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        return False
    return True


def test_the_install_token_is_on_the_one_list_of_owned_entries() -> None:
    """SYS-08: one list in platform/secrets.py, which M2's secrets join."""
    assert INSTALL_TOKEN_NAME in OWNED_SECRET_NAMES


def test_every_owned_entry_and_the_data_folder_are_removed(tmp_path: Path) -> None:
    """SYS-08: exit 0; entries that aren't ours stay."""
    paths = make_data(tmp_path)
    store = MemorySecretStore()
    for name in OWNED_SECRET_NAMES:
        store.set(name, "value")
    store.set("somebody-else", "keep")
    assert uninstall.remove_data(paths, store, FakeInstanceLock(set())) == uninstall.EXIT_OK
    assert not paths.root.exists()
    assert all(store.get(name) is None for name in OWNED_SECRET_NAMES)
    assert store.get("somebody-else") == "keep"


def test_it_works_when_nothing_was_ever_stored_or_the_folder_is_gone(tmp_path: Path) -> None:
    """SYS-08: removing what isn't there is not an error."""
    paths = DataPaths(tmp_path / "ShelfSync")
    assert uninstall.remove_data(paths, MemorySecretStore(), FakeInstanceLock(set())) == uninstall.EXIT_OK


def test_a_link_in_the_data_folder_is_removed_itself_and_never_followed(tmp_path: Path) -> None:
    """SYS-08, 06 section 4: a planted junction or symlink to a folder outside leaves that folder's files alone."""
    paths = make_data(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "precious.txt").write_text("keep me", encoding="utf-8")
    if not make_link(paths.root / "tmp" / "link", outside):
        pytest.skip("this account can't make directory links")
    assert uninstall.remove_data(paths, MemorySecretStore(), FakeInstanceLock(set())) == uninstall.EXIT_OK
    assert not paths.root.exists()
    assert (outside / "precious.txt").read_text(encoding="utf-8") == "keep me"


def test_a_data_folder_that_is_itself_a_link_is_left_alone_and_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """SYS-08: SHELFSYNC_DATA_DIR pointing at a link: not followed, not removed; exit 1 and the target is named, so the
    uninstaller shows its partial notice."""
    real = tmp_path / "ShelfSync-real"
    real.mkdir()
    (real / "file.txt").write_text("x", encoding="utf-8")
    link = tmp_path / "ShelfSync"
    if not make_link(link, real):
        pytest.skip("this account can't make directory links")
    store = MemorySecretStore()
    store.set(INSTALL_TOKEN_NAME, "value")
    taken: set[str] = set()
    assert uninstall.remove_data(DataPaths(link), store, FakeInstanceLock(taken)) == uninstall.EXIT_INCOMPLETE
    assert "ShelfSync-real" in capsys.readouterr().out
    assert (real / "file.txt").exists()
    assert uninstall.is_link(link)
    assert store.get(INSTALL_TOKEN_NAME) is None  # the stored tokens go even though the data behind the link stays
    assert taken == set()  # the lock taken through the link was let go


def test_a_live_link_data_folder_still_takes_the_lock_and_refuses_while_it_runs(tmp_path: Path) -> None:
    """SYS-08: a live link takes the lock through it as before: held means exit 4 and nothing removed."""
    real = tmp_path / "ShelfSync-real"
    real.mkdir()
    link = tmp_path / "ShelfSync"
    if not make_link(link, real):
        pytest.skip("this account can't make directory links")
    store = MemorySecretStore()
    store.set(INSTALL_TOKEN_NAME, "value")
    code = uninstall.remove_data(DataPaths(link), store, FakeInstanceLock({"x"}, "x"))
    assert code == uninstall.EXIT_RUNNING
    assert store.get(INSTALL_TOKEN_NAME) == "value"


class StuckStore(MemorySecretStore):
    def delete(self, name: str) -> None:
        raise SecretStoreError("Credential Manager delete failed (OSError)")


def test_an_entry_that_cant_be_removed_gives_a_nonzero_exit_and_the_data_still_goes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """SYS-08: the uninstaller reports it and goes on; the secret's value is never printed."""
    paths = make_data(tmp_path)
    store = StuckStore()
    store.set(INSTALL_TOKEN_NAME, "SECRET-VALUE-123")
    assert uninstall.remove_data(paths, store, FakeInstanceLock(set())) == uninstall.EXIT_SECRETS
    out = capsys.readouterr().out
    assert INSTALL_TOKEN_NAME in out and "SECRET-VALUE-123" not in out
    assert not paths.root.exists()


def test_an_entry_that_cant_be_removed_from_the_data_folder_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SYS-08: a locked file: exit 1, the others are still removed, and the folder is named."""
    paths = make_data(tmp_path)
    real_remove = uninstall.remove_entry

    def remove(entry: Path) -> None:
        if entry.name == "logs":
            raise PermissionError("in use")
        real_remove(entry)

    monkeypatch.setattr(uninstall, "remove_entry", remove)
    assert uninstall.remove_data(paths, MemorySecretStore(), FakeInstanceLock(set())) == uninstall.EXIT_INCOMPLETE
    out = capsys.readouterr().out
    assert "logs" in out and str(paths.root) in out
    assert [p.name for p in paths.root.iterdir()] == ["logs"]  # the rest is gone


def test_a_folder_that_doesnt_look_like_ours_is_refused_untouched(tmp_path: Path) -> None:
    """SYS-08: deny by default: a SHELFSYNC_DATA_DIR left pointing elsewhere must not become a wide delete."""
    other = tmp_path / "Documents"
    other.mkdir()
    (other / "thesis.docx").write_text("x", encoding="utf-8")
    store = MemorySecretStore()
    store.set(INSTALL_TOKEN_NAME, "value")
    assert uninstall.remove_data(DataPaths(other), store, FakeInstanceLock(set())) == uninstall.EXIT_REFUSED
    assert (other / "thesis.docx").exists()
    assert store.get(INSTALL_TOKEN_NAME) == "value"  # refused before anything is removed


def test_a_folder_holding_the_database_counts_even_with_another_name(tmp_path: Path) -> None:
    """SYS-08."""
    other = tmp_path / "custom-data"
    other.mkdir()
    (other / "shelfsync.db").write_text("db", encoding="utf-8")
    assert uninstall.looks_like_data_folder(other)
    assert not uninstall.looks_like_data_folder(tmp_path)
    assert not uninstall.looks_like_data_folder(Path(tmp_path.anchor))


def test_main_needs_the_flag_and_uses_the_resolved_data_folder(data_paths: DataPaths) -> None:
    """SYS-08: the entry point: no flag is a usage error; with it, the data folder from the environment goes."""
    with pytest.raises(SystemExit) as stop:
        uninstall.main([], store=MemorySecretStore(), lock=FakeInstanceLock(set()))
    assert stop.value.code == 2
    data_paths.root.mkdir(parents=True)
    (data_paths.root / "shelfsync.db").write_text("db", encoding="utf-8")
    assert uninstall.main(["--remove-data"], store=MemorySecretStore(), lock=FakeInstanceLock(set())) == 0
    assert not data_paths.root.exists()


def test_main_refuses_when_no_data_folder_is_known(monkeypatch: pytest.MonkeyPatch) -> None:
    """SYS-08."""
    monkeypatch.delenv("SHELFSYNC_DATA_DIR", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    assert (
        uninstall.main(["--remove-data"], store=MemorySecretStore(), lock=FakeInstanceLock(set()))
        == uninstall.EXIT_REFUSED
    )


def test_a_store_that_cant_even_be_opened_is_an_incomplete_removal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SYS-08: no Credential Manager (off Windows, or it fails): every entry is reported, the data still goes."""

    def broken(service: str) -> MemorySecretStore:
        raise SecretStoreError("Credential Manager is available on Windows only")

    monkeypatch.setattr(uninstall, "KeyringSecretStore", broken)
    paths = make_data(tmp_path)
    assert uninstall.remove_data(paths, None, FakeInstanceLock(set())) == uninstall.EXIT_SECRETS
    assert not paths.root.exists()


def test_it_refuses_while_shelfsync_runs_and_touches_nothing(tmp_path: Path) -> None:
    """SYS-08: the lock is held for the whole job; a held lock (the app running) means exit 4 and no change."""
    paths = make_data(tmp_path)
    store = MemorySecretStore()
    store.set(INSTALL_TOKEN_NAME, "value")
    taken = {"x"}
    assert uninstall.remove_data(paths, store, FakeInstanceLock(taken, "x")) == uninstall.EXIT_RUNNING
    assert (paths.root / "shelfsync.db").exists() and store.get(INSTALL_TOKEN_NAME) == "value"
    assert taken == {"x"}  # the holder's lock isn't disturbed


def test_a_lock_that_cant_be_checked_counts_as_running(tmp_path: Path) -> None:
    """SYS-08: fail closed."""

    class Broken:
        def acquire(self) -> bool:
            raise OSError("no")

        def release(self) -> None: ...

    paths = make_data(tmp_path)
    assert uninstall.remove_data(paths, MemorySecretStore(), Broken()) == uninstall.EXIT_RUNNING
    assert paths.root.exists()


def test_the_lock_is_held_during_the_job_and_the_lock_file_goes_last(tmp_path: Path) -> None:
    """SYS-08: the lock file can't be deleted while we hold it, so it is let go first and then removed."""
    paths = make_data(tmp_path)
    paths.instance_lock.write_text("", encoding="utf-8")
    events: list[str] = []

    class Spy:
        def acquire(self) -> bool:
            events.append("acquire")
            return True

        def release(self) -> None:
            events.append(f"release (lock file present: {paths.instance_lock.exists()})")

    assert uninstall.remove_data(paths, MemorySecretStore(), Spy()) == uninstall.EXIT_OK
    assert events[0] == "acquire" and events[1] == "release (lock file present: True)"
    assert not paths.root.exists()


def test_the_service_name_must_be_shelfsyncs_own_or_a_throwaway_variant() -> None:
    """SYS-08: a rehearsal build passes `ShelfSync-rehearsal`; nothing else's Credential Manager service is accepted."""
    assert uninstall.service_name("ShelfSync") == "ShelfSync"
    assert uninstall.service_name("ShelfSync-rehearsal") == "ShelfSync-rehearsal"
    for bad in ("Chrome", "shelfsync-x ", "ShelfSync; x", "", "xShelfSync"):
        with pytest.raises(argparse.ArgumentTypeError):
            uninstall.service_name(bad)
    with pytest.raises(SystemExit):
        uninstall.main(["--remove-data", "--service", "Other"], store=MemorySecretStore())


@pytest.mark.windows
@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_remove_data_removes_a_throwaway_credential_manager_entry_and_a_real_junction(tmp_path: Path) -> None:
    """SYS-08: a throwaway service name (never the real `ShelfSync` one), a real junction in the data folder."""
    from shelfsync.platform.secrets import KeyringSecretStore

    store = KeyringSecretStore(f"ShelfSync-test-{secrets.token_hex(6)}")
    paths = make_data(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "precious.txt").write_text("keep me", encoding="utf-8")
    assert make_link(paths.root / "tmp" / "junction", outside)
    store.set(INSTALL_TOKEN_NAME, "throwaway-value")
    try:
        assert store.get(INSTALL_TOKEN_NAME) == "throwaway-value"
        assert uninstall.remove_data(paths, store, FakeInstanceLock(set())) == uninstall.EXIT_OK
        assert store.get(INSTALL_TOKEN_NAME) is None
    finally:
        store.delete(INSTALL_TOKEN_NAME)
    assert not paths.root.exists()
    assert (outside / "precious.txt").read_text(encoding="utf-8") == "keep me"


def test_a_dangling_link_as_the_data_folder_is_reported_not_called_running(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """SYS-08: the link check comes before the lock: a junction to a folder that is gone can't hold a lock file, and
    that must read as a link left alone (exit 1), never as "ShelfSync is running" (exit 4); the secrets still go."""
    gone = tmp_path / "gone"
    gone.mkdir()
    link = tmp_path / "ShelfSync"
    if not make_link(link, gone):
        pytest.skip("this account can't make directory links")
    gone.rmdir()  # now the link dangles
    broken = FakeInstanceLock({"x"}, "x")  # would say "running" if it were asked
    store = MemorySecretStore()
    store.set(INSTALL_TOKEN_NAME, "value")
    code = uninstall.remove_data(DataPaths(link), store, broken, lambda: FakeInstanceLock(set(), "mutex"))
    assert code == uninstall.EXIT_INCOMPLETE
    out = capsys.readouterr().out
    assert "link" in out and "running" not in out
    assert store.get(INSTALL_TOKEN_NAME) is None  # the stored tokens are removed even though the folder is dangling


def test_a_dangling_link_in_place_of_the_lock_file_is_still_removed(tmp_path: Path) -> None:
    """SYS-08: `lexists`, not `exists`: a dangling link named instance.lock must not stop the folder from going."""
    paths = make_data(tmp_path)
    if not make_link(paths.instance_lock, tmp_path / "nowhere"):
        pytest.skip("this account can't make links")
    assert uninstall.remove_data(paths, MemorySecretStore(), FakeInstanceLock(set())) == uninstall.EXIT_OK
    assert not paths.root.exists()


def test_a_service_whose_store_cant_be_built_never_falls_back_to_the_real_one(
    data_paths: DataPaths, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SYS-08: `--service ShelfSync-x` with a Credential Manager that can't be opened: every entry is reported, and
    no store is ever built for the real `ShelfSync` service."""
    built: list[str] = []

    def refuse(service: str) -> MemorySecretStore:
        built.append(service)
        raise SecretStoreError("Credential Manager is available on Windows only")

    monkeypatch.setattr(uninstall, "KeyringSecretStore", refuse)
    data_paths.root.mkdir(parents=True)
    (data_paths.root / "shelfsync.db").write_text("db", encoding="utf-8")
    code = uninstall.main(["--remove-data", "--service", "ShelfSync-x"], lock=FakeInstanceLock(set()))
    assert code == uninstall.EXIT_SECRETS
    assert built == ["ShelfSync-x"]
    assert "install-token" in capsys.readouterr().out
    assert not data_paths.root.exists()


def test_a_dangling_link_still_takes_the_session_mutex_and_refuses_while_it_is_held(tmp_path: Path) -> None:
    """SYS-08: no lock file through a dangling link, but a running copy's session mutex still refuses (exit 4)."""
    gone = tmp_path / "gone"
    gone.mkdir()
    link = tmp_path / "ShelfSync"
    if not make_link(link, gone):
        pytest.skip("this account can't make directory links")
    gone.rmdir()
    store = MemorySecretStore()
    store.set(INSTALL_TOKEN_NAME, "value")
    held = FakeInstanceLock({"mutex"}, "mutex")
    assert uninstall.remove_data(DataPaths(link), store, None, lambda: held) == uninstall.EXIT_RUNNING
    assert store.get(INSTALL_TOKEN_NAME) == "value"


def test_a_mutex_that_cant_be_taken_counts_as_running_for_a_dangling_link(tmp_path: Path) -> None:
    """SYS-08: fail closed (off Windows the real mutex refuses to be built)."""
    gone = tmp_path / "gone"
    gone.mkdir()
    link = tmp_path / "ShelfSync"
    if not make_link(link, gone):
        pytest.skip("this account can't make directory links")
    gone.rmdir()

    def refuse() -> FakeInstanceLock:
        raise OSError("no mutex")

    assert uninstall.remove_data(DataPaths(link), MemorySecretStore(), None, refuse) == uninstall.EXIT_RUNNING


def test_the_exit_codes_tell_data_left_from_a_token_left(tmp_path: Path) -> None:
    """SYS-08: 1 data left, 5 only the token left, 6 both, 0 neither."""
    paths = make_data(tmp_path)
    assert uninstall.remove_data(paths, StuckStore(), FakeInstanceLock(set())) == uninstall.EXIT_SECRETS == 5
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "ShelfSync2"
    if not make_link(link, real):
        pytest.skip("this account can't make directory links")
    assert uninstall.remove_data(DataPaths(link), StuckStore(), FakeInstanceLock(set())) == uninstall.EXIT_BOTH == 6
    assert (
        uninstall.remove_data(DataPaths(link), MemorySecretStore(), FakeInstanceLock(set()))
        == uninstall.EXIT_INCOMPLETE
        == 1
    )
