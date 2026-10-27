"""SYS-04: Start with Windows through the HKCU Run value. The real registry is only ever touched under a throwaway
value name (`ShelfSync-test-<random>`), removed in `finally`; the real `ShelfSync` value is never written."""

import logging
import secrets
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from shelfsync.platform import autostart
from shelfsync.platform.autostart import (
    FakeRunKey,
    WindowsRunKey,
    apply_start_with_windows,
    is_installed_copy,
    launcher_command,
)

COMMAND = r'"C:\Users\x\AppData\Local\Programs\ShelfSync\current\pythonw.exe" -m shelfsync.launcher --background'


def test_a_development_run_writes_nothing_and_says_so(caplog: pytest.LogCaptureFixture) -> None:
    """SYS-04: not running from the install folder, so the Run key is left alone (and the log says it was skipped)."""
    key = FakeRunKey()
    with caplog.at_level(logging.INFO, logger="shelfsync.autostart"):
        outcome = apply_start_with_windows(True, key, command=COMMAND, installed=False)
    assert outcome == "skipped"
    assert key.values == {}
    assert "skipped" in caplog.text


def test_a_development_run_also_leaves_an_existing_value_alone() -> None:
    """SYS-04: switching the setting off in development doesn't remove the installed copy's value either."""
    key = FakeRunKey()
    key.values["ShelfSync"] = COMMAND
    assert apply_start_with_windows(False, key, installed=False) == "skipped"
    assert key.values == {"ShelfSync": COMMAND}


def test_enabled_sets_the_value_and_a_second_time_changes_nothing() -> None:
    """SYS-04: default on; the value is named ShelfSync."""
    key = FakeRunKey()
    assert apply_start_with_windows(True, key, command=COMMAND, installed=True) == "set"
    assert key.values == {"ShelfSync": COMMAND}
    assert apply_start_with_windows(True, key, command=COMMAND, installed=True) == "unchanged"


def test_a_changed_path_replaces_the_value() -> None:
    """SYS-04: the value tracks the command (an old version's path, say)."""
    key = FakeRunKey()
    key.values["ShelfSync"] = "old"
    assert apply_start_with_windows(True, key, command=COMMAND, installed=True) == "set"
    assert key.values["ShelfSync"] == COMMAND


def test_turning_it_off_removes_the_value() -> None:
    """SYS-04."""
    key = FakeRunKey()
    key.values["ShelfSync"] = COMMAND
    key.values["Other app"] = "keep"
    assert apply_start_with_windows(False, key, installed=True) == "removed"
    assert key.values == {"Other app": "keep"}  # only ours
    assert apply_start_with_windows(False, key, installed=True) == "unchanged"


def test_the_command_is_the_quoted_pythonw_path_and_the_launcher_module() -> None:
    """SYS-04: the path has spaces on some PCs, so it is quoted."""
    command = launcher_command(r"C:\Users\Some One\AppData\Local\Programs\ShelfSync\current\python.exe")
    assert command.startswith('"')
    assert command.endswith('pythonw.exe" -m shelfsync.launcher')
    assert "Some One" in command


def test_the_run_value_passes_background_so_signing_in_opens_no_tab() -> None:
    """SYS-04: the Run value's command starts ShelfSync in the tray (the flag); shortcuts have no flag."""
    exe = r"C:\Users\x\AppData\Local\Programs\ShelfSync\current\python.exe"
    assert launcher_command(exe, background=True).endswith("-m shelfsync.launcher --background")
    assert "--background" not in launcher_command(exe)


def test_an_old_run_value_without_the_flag_is_rewritten() -> None:
    """SYS-04: a Run value from M1a (no flag) is replaced at the next start, so sign-in stops opening a tab."""
    key = FakeRunKey()
    key.values["ShelfSync"] = COMMAND.removesuffix(" --background")
    assert apply_start_with_windows(True, key, command=COMMAND, installed=True) == "set"
    assert key.values["ShelfSync"] == COMMAND


def test_only_a_python_under_the_install_folders_current_is_the_installed_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SYS-04: the path is compared as written (current is a junction, which must not be resolved away)."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    current = tmp_path / "Programs" / "ShelfSync" / "current"
    assert is_installed_copy(str(current / "pythonw.exe"))
    assert is_installed_copy(str(current / "Lib" / "python.exe"))
    assert not is_installed_copy(str(tmp_path / "Programs" / "ShelfSync" / "versions" / "1.0" / "python.exe"))
    assert not is_installed_copy(str(tmp_path / "Programs" / "ShelfSync" / "currentx" / "python.exe"))
    assert not is_installed_copy(sys.executable)  # this venv


def test_without_localappdata_nothing_is_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """SYS-04."""
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    assert not is_installed_copy(r"C:\anywhere\pythonw.exe")


def test_the_test_runner_is_not_an_installed_copy() -> None:
    """SYS-04: so a default apply (the one the launcher makes) can't write the owner's real Run value from here."""
    assert apply_start_with_windows(True, FakeRunKey()) == "skipped"


@pytest.mark.skipif(sys.platform == "win32", reason="the other platforms refuse")
def test_off_windows_the_real_key_refuses() -> None:
    """SYS-04."""
    with pytest.raises(autostart.AutostartError):
        WindowsRunKey().get("x")


# ---- the real registry, throwaway value only ----------------------------------------------------------------------


@contextmanager
def throwaway_value() -> Iterator[str]:
    name = f"ShelfSync-test-{secrets.token_hex(6)}"
    try:
        yield name
    finally:
        WindowsRunKey().delete(name)


@pytest.mark.windows
@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_the_real_run_key_sets_reads_replaces_and_removes_a_throwaway_value() -> None:
    """SYS-04: HKCU Run, REG_SZ; turning it off removes the value."""
    import winreg

    key = WindowsRunKey()
    with throwaway_value() as name:
        assert key.get(name) is None
        assert apply_start_with_windows(True, key, name=name, command=COMMAND, installed=True) == "set"
        assert key.get(name) == COMMAND
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, autostart.RUN_KEY) as handle:
            value, kind = winreg.QueryValueEx(handle, name)
        assert (value, kind) == (COMMAND, winreg.REG_SZ)
        assert apply_start_with_windows(True, key, name=name, command=COMMAND, installed=True) == "unchanged"
        assert apply_start_with_windows(False, key, name=name, installed=True) == "removed"
        assert key.get(name) is None
        assert apply_start_with_windows(False, key, name=name, installed=True) == "unchanged"


@pytest.mark.windows
@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_the_real_run_key_removing_a_missing_value_is_quiet() -> None:
    """SYS-04."""
    WindowsRunKey().delete(f"ShelfSync-test-{secrets.token_hex(6)}")


@pytest.mark.windows
@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_the_real_run_key_is_not_written_by_a_development_apply(monkeypatch: pytest.MonkeyPatch) -> None:
    """SYS-04: with this a development run (forced, so an installed ShelfSync on this PC can't change the answer)
    the owner's real `ShelfSync` value is read, never written: the same before and after."""
    monkeypatch.setattr(autostart, "is_installed_copy", lambda executable=None: False)
    key = WindowsRunKey()
    before = key.get("ShelfSync")
    assert apply_start_with_windows(True, key) == "skipped"
    assert apply_start_with_windows(False, key) == "skipped"
    assert key.get("ShelfSync") == before
