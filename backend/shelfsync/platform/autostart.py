"""Start with Windows (SYS-04): one value in `HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run`.

The value is named `ShelfSync` and holds the quoted path of the installed `pythonw.exe` and `-m shelfsync.launcher`.
Turning the setting off removes the value. It is written only by an installed copy (running from
`%LOCALAPPDATA%\\Programs\\ShelfSync\\current\\`): a development run never touches the owner's Run key.
"""

import logging
import os
import sys
from pathlib import Path, PureWindowsPath
from typing import Protocol

_log = logging.getLogger("shelfsync.autostart")

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "ShelfSync"
INSTALL_SUBFOLDER = Path("Programs") / "ShelfSync" / "current"


class RunKey(Protocol):
    def get(self, name: str) -> str | None: ...

    def set(self, name: str, command: str) -> None: ...

    def delete(self, name: str) -> None:
        """Remove the value. Removing one that isn't there is not an error."""
        ...


class AutostartError(Exception):
    """The Run key couldn't be read or changed. The message names the failure type only."""


class FakeRunKey:
    """In-memory Run key for tests and Linux CI."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, name: str) -> str | None:
        return self.values.get(name)

    def set(self, name: str, command: str) -> None:
        self.values[name] = command

    def delete(self, name: str) -> None:
        self.values.pop(name, None)


if sys.platform == "win32":
    import winreg

    class WindowsRunKey:
        """The current user's Run key (never HKLM)."""

        def get(self, name: str) -> str | None:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_QUERY_VALUE) as key:
                    value, _kind = winreg.QueryValueEx(key, name)
            except FileNotFoundError:
                return None
            except OSError as error:
                raise AutostartError(f"Reading the Run key failed ({type(error).__name__})") from None
            return str(value)

        def set(self, name: str, command: str) -> None:
            try:
                with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                    winreg.SetValueEx(key, name, 0, winreg.REG_SZ, command)
            except OSError as error:
                raise AutostartError(f"Writing the Run key failed ({type(error).__name__})") from None

        def delete(self, name: str) -> None:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                    winreg.DeleteValue(key, name)
            except FileNotFoundError:
                return  # no key or no value: nothing to remove
            except OSError as error:
                raise AutostartError(f"Removing the Run value failed ({type(error).__name__})") from None

else:

    class WindowsRunKey:
        """The Run key exists on Windows only."""

        def get(self, name: str) -> str | None:
            raise AutostartError("The Run key is available on Windows only")

        def set(self, name: str, command: str) -> None:
            raise AutostartError("The Run key is available on Windows only")

        def delete(self, name: str) -> None:
            raise AutostartError("The Run key is available on Windows only")


def install_folder() -> Path | None:
    """`%LOCALAPPDATA%\\Programs\\ShelfSync\\current`, or None when LOCALAPPDATA is unknown."""
    local = os.environ.get("LOCALAPPDATA")
    return Path(local) / INSTALL_SUBFOLDER if local else None


def is_installed_copy(executable: str | None = None) -> bool:
    """True when the running Python is the installed one: its path (not resolved: `current` is a junction) is inside
    `%LOCALAPPDATA%\\Programs\\ShelfSync\\current\\`."""
    folder = install_folder()
    if folder is None:
        return False
    path = os.path.normcase(os.path.abspath(executable or sys.executable))
    base = os.path.normcase(os.path.abspath(folder)) + os.sep
    return path.startswith(base)


def launcher_command(executable: str | None = None) -> str:
    """`"<...>\\pythonw.exe" -m shelfsync.launcher`, the path quoted, from the running interpreter's own folder."""
    folder = PureWindowsPath(executable or sys.executable).parent  # a Windows path on every platform (the Run value)
    return f'"{folder / "pythonw.exe"}" -m shelfsync.launcher'


def apply_start_with_windows(
    enabled: bool,
    run_key: RunKey | None = None,
    *,
    name: str = VALUE_NAME,
    command: str | None = None,
    installed: bool | None = None,
) -> str:
    """Make the Run value match the `start_with_windows` setting. Returns what happened, for the log and for tests:
    "set", "removed", "unchanged" or "skipped".

    Only an installed copy writes (`installed` defaults to `is_installed_copy()`). A development run logs that it
    skipped and touches nothing. Windows tests pass their own throwaway `name` and `command`.
    """
    is_installed = is_installed_copy() if installed is None else installed
    if not is_installed:
        _log.info("Start with Windows: skipped, this isn't the installed copy")
        return "skipped"
    key = run_key if run_key is not None else WindowsRunKey()
    current = key.get(name)
    if enabled:
        wanted = command if command is not None else launcher_command()
        if current == wanted:
            return "unchanged"
        key.set(name, wanted)
        return "set"
    if current is None:
        return "unchanged"
    key.delete(name)
    return "removed"
