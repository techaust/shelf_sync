"""SYS-08: `python -m shelfsync.uninstall --remove-data`: the Credential Manager entries ShelfSync owns, then the data
folder, never following a link. Fakes everywhere; the `windows` checks use a throwaway service name and a real
junction."""

import secrets
import subprocess
import sys
from pathlib import Path

import pytest

from shelfsync import uninstall
from shelfsync.paths import DataPaths
from shelfsync.platform.secrets import OWNED_SECRET_NAMES, MemorySecretStore, SecretStoreError
from shelfsync.secure.token import INSTALL_TOKEN_NAME


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
    assert uninstall.remove_data(paths, store) == uninstall.EXIT_OK
    assert not paths.root.exists()
    assert all(store.get(name) is None for name in OWNED_SECRET_NAMES)
    assert store.get("somebody-else") == "keep"


def test_it_works_when_nothing_was_ever_stored_or_the_folder_is_gone(tmp_path: Path) -> None:
    """SYS-08: removing what isn't there is not an error."""
    paths = DataPaths(tmp_path / "ShelfSync")
    assert uninstall.remove_data(paths, MemorySecretStore()) == uninstall.EXIT_OK


def test_a_link_in_the_data_folder_is_removed_itself_and_never_followed(tmp_path: Path) -> None:
    """SYS-08, 06 section 4: a planted junction or symlink to a folder outside leaves that folder's files alone."""
    paths = make_data(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "precious.txt").write_text("keep me", encoding="utf-8")
    if not make_link(paths.root / "tmp" / "link", outside):
        pytest.skip("this account can't make directory links")
    assert uninstall.remove_data(paths, MemorySecretStore()) == uninstall.EXIT_OK
    assert not paths.root.exists()
    assert (outside / "precious.txt").read_text(encoding="utf-8") == "keep me"


def test_a_data_folder_that_is_itself_a_link_is_unlinked_not_emptied(tmp_path: Path) -> None:
    """SYS-08: SHELFSYNC_DATA_DIR pointing at a link: only the link goes."""
    real = tmp_path / "ShelfSync-real"
    real.mkdir()
    (real / "file.txt").write_text("x", encoding="utf-8")
    link = tmp_path / "ShelfSync"
    if not make_link(link, real):
        pytest.skip("this account can't make directory links")
    assert uninstall.remove_data(DataPaths(link), MemorySecretStore()) == uninstall.EXIT_OK
    assert not link.exists()
    assert (real / "file.txt").exists()


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
    assert uninstall.remove_data(paths, store) == uninstall.EXIT_INCOMPLETE
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
    assert uninstall.remove_data(paths, MemorySecretStore()) == uninstall.EXIT_INCOMPLETE
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
    assert uninstall.remove_data(DataPaths(other), store) == uninstall.EXIT_REFUSED
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
        uninstall.main([], store=MemorySecretStore())
    assert stop.value.code == 2
    data_paths.root.mkdir(parents=True)
    (data_paths.root / "shelfsync.db").write_text("db", encoding="utf-8")
    assert uninstall.main(["--remove-data"], store=MemorySecretStore()) == 0
    assert not data_paths.root.exists()


def test_main_refuses_when_no_data_folder_is_known(monkeypatch: pytest.MonkeyPatch) -> None:
    """SYS-08."""
    monkeypatch.delenv("SHELFSYNC_DATA_DIR", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    assert uninstall.main(["--remove-data"], store=MemorySecretStore()) == uninstall.EXIT_REFUSED


def test_a_store_that_cant_even_be_opened_is_an_incomplete_removal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SYS-08: no Credential Manager (off Windows, or it fails): every entry is reported, the data still goes."""

    def broken() -> MemorySecretStore:
        raise SecretStoreError("Credential Manager is available on Windows only")

    monkeypatch.setattr(uninstall, "default_secret_store", broken)
    paths = make_data(tmp_path)
    assert uninstall.remove_data(paths) == uninstall.EXIT_INCOMPLETE
    assert not paths.root.exists()


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
        assert uninstall.remove_data(paths, store) == uninstall.EXIT_OK
        assert store.get(INSTALL_TOKEN_NAME) is None
    finally:
        store.delete(INSTALL_TOKEN_NAME)
    assert not paths.root.exists()
    assert (outside / "precious.txt").read_text(encoding="utf-8") == "keep me"
