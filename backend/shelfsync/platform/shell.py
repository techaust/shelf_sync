"""Open a web address or a folder with Windows' own handler (UI-TRAY, SYS-03).

`os.startfile` calls the Windows shell (`ShellExecuteW` with the "open" verb) directly. The address is handed over as
one argument, never put into a command line, so no `cmd.exe` or PowerShell sees it and nothing writes it to a log.
It reaches the default browser's own command line, which is why the ticket in it is single-use and lasts 60 seconds
(06 section 2). This module never logs the address.
"""

import os
import sys
from pathlib import Path
from typing import Protocol


class Shell(Protocol):
    def open_url(self, url: str) -> None: ...

    def open_folder(self, folder: Path) -> None: ...


class ShellError(Exception):
    """The shell couldn't open it. The message holds neither the address nor the folder."""


def _check_http_loopback(url: str) -> None:
    # The only addresses ShelfSync opens are its own. Refuse anything else, so a bug can't open another site with a
    # ticket in it.
    if not url.startswith("http://127.0.0.1:"):
        raise ShellError("Only ShelfSync's own address can be opened")


class WindowsShell:
    """The real shell. Windows only."""

    def open_url(self, url: str) -> None:
        _check_http_loopback(url)
        if sys.platform != "win32":
            raise ShellError("Opening an address needs Windows")
        try:
            # nosec B606: the address was checked above to be ShelfSync's own http://127.0.0.1; no shell, no command line
            os.startfile(url)  # nosec B606
        except OSError as error:
            raise ShellError(f"Windows couldn't open the address ({type(error).__name__})") from None

    def open_folder(self, folder: Path) -> None:
        if sys.platform != "win32":
            raise ShellError("Opening a folder needs Windows")
        try:
            # nosec B606: the folder is ShelfSync's own logs folder, passed as one argument to the shell's "open"
            os.startfile(folder)  # nosec B606
        except OSError as error:
            raise ShellError(f"Windows couldn't open the folder ({type(error).__name__})") from None


class FakeShell:
    """Records what was asked, for tests."""

    def __init__(self) -> None:
        self.urls: list[str] = []
        self.folders: list[Path] = []

    def open_url(self, url: str) -> None:
        _check_http_loopback(url)
        self.urls.append(url)

    def open_folder(self, folder: Path) -> None:
        self.folders.append(folder)
