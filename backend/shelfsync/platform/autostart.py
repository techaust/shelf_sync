"""Start with Windows (SYS-04): one value in `HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run`.

The value is named `ShelfSync` and holds the quoted path of the installed `pythonw.exe`, `-m shelfsync.launcher` and
`--background` (sign-in starts ShelfSync in the tray with no browser tab; shortcuts have no flag and open a tab).
Turning the setting off removes the value. It is written only by an installed copy (`update.layout.installed_root`,
the one test: the Python sits in `<root>\\versions\\<v>\\`): a development run never touches the owner's Run key. The
value always names `<root>\\current\\pythonw.exe`, so an update needs no new value.
"""

import logging
import sys
from pathlib import PureWindowsPath
from typing import Protocol

from shelfsync.update.layout import installed_root

_log = logging.getLogger("shelfsync.autostart")

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "ShelfSync"
CURRENT_FOLDER_NAME = "current"


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


def is_installed_copy(executable: str | None = None) -> bool:
    """True when the running Python is the installed one (`installed_root`: in `<root>\\versions\\<v>\\`, `<v>` this
    code's own version). Reached through the `current` junction or not makes no difference."""
    return installed_root(executable) is not None


BACKGROUND_FLAG = "--background"


def launcher_command(executable: str | None = None, *, background: bool = False) -> str:
    """`"<...>\\pythonw.exe" -m shelfsync.launcher`, the path quoted, from the running interpreter's own folder.
    The Run value passes `background=True`: signing in to Windows starts ShelfSync in the tray with no browser tab.
    An installed copy (and no `executable` given) names `<root>\\current`, never the version folder it runs from."""
    root = installed_root() if executable is None else None
    # a Windows path on every platform (the Run value)
    folder = (
        PureWindowsPath(root) / CURRENT_FOLDER_NAME if root is not None else PureWindowsPath(executable or sys.executable).parent
    )
    command = f'"{folder / "pythonw.exe"}" -m shelfsync.launcher'
    return f"{command} {BACKGROUND_FLAG}" if background else command


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
        wanted = command if command is not None else launcher_command(background=True)
        if current == wanted:
            return "unchanged"
        key.set(name, wanted)
        return "set"
    if current is None:
        return "unchanged"
    key.delete(name)
    return "removed"
