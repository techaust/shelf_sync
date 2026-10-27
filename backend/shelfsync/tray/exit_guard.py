"""The safety exit (UI-TRAY, SYS-02, SYS-03): if ShelfSync doesn't end in time after Quit, it is ended anyway.

Python gives no limit on how long the process takes to end once the launcher returns: `threading._shutdown` joins
non-daemon threads without a timeout, and exit callbacks can wait for ever. `faulthandler.dump_traceback_later(...,
exit=True)` runs on its own C thread: when the deadline passes it writes every thread's stack to a file and ends the
process with exit code 1 (the only code it can use; the next start's WARNING says it was a stalled exit).

The file is `tmp\\shutdown-stall.txt`, opened in binary mode and kept open (faulthandler holds a reference to the file
object too; ours is kept so it is never closed early). Our code never cancels the guard: a clean exit leaves an empty
file and the next start removes it. Only the interpreter's own final clean-up cancels the timer, so the very last
shut-down steps (after faulthandler is torn down) are not covered. The dump holds thread ids, file paths, line numbers
and function names, never values; it is read back through the redacting log handler at the next start (06 section 3).

The file name is ours, but the folder is writable by the user, so a link planted there must not be followed: an entry
that is a symlink, a junction or other reparse point, or has more than one hard link, is removed before the guard
opens it, and is not read back at the next start.
"""

import contextlib
import faulthandler
import os
import stat
from pathlib import Path
from typing import BinaryIO

from shelfsync.paths import _remove_entry

STALL_FILE_NAME = "shutdown-stall.txt"


def is_plain_file(path: Path) -> bool:
    """True if `path` is a regular file with one name, and not a link or a reparse point. False if it is anything
    else; an entry that doesn't exist is also False (nothing to read)."""
    try:
        info = path.lstat()
    except OSError:
        return False
    if path.is_symlink() or os.path.isjunction(path):
        return False
    if getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
        return False
    return stat.S_ISREG(info.st_mode) and info.st_nlink == 1


def remove_unsafe_entry(path: Path) -> bool:
    """Remove `path` if it exists and is not a plain file (the way `empty_tmp` removes entries, never following a
    link). Returns True if something unsafe was found."""
    if not path.exists() and not path.is_symlink():
        return False
    if is_plain_file(path):
        return False
    with contextlib.suppress(OSError):  # if it stays, the caller's open fails and is reported
        _remove_entry(path)
    return True


class ExitGuard:
    def __init__(self, tmp: Path) -> None:
        self._path = tmp / STALL_FILE_NAME
        self._file: BinaryIO | None = None
        self.armed = False

    def arm(self, seconds: float) -> None:
        """Start the countdown. The file object is kept alive for as long as the guard exists. Raises OSError if the
        file can't be opened (the caller carries on without the guard)."""
        if self._file is None:
            remove_unsafe_entry(self._path)
            self._file = self._path.open("wb")
        self._schedule(self._file, seconds)

    def rearm(self, seconds: float) -> None:
        """Replace the countdown by a new one (only if it was armed)."""
        if self._file is not None:
            self._schedule(self._file, seconds)

    def _schedule(self, file: BinaryIO, seconds: float) -> None:
        faulthandler.dump_traceback_later(seconds, repeat=False, file=file, exit=True)
        self.armed = True
