"""The safety exit (UI-TRAY, SYS-02, SYS-03): if ShelfSync doesn't end in time after Quit, it is ended anyway.

Python gives no limit on how long the process takes to end once the launcher returns: `threading._shutdown` joins
non-daemon threads without a timeout, and exit callbacks can wait for ever. `faulthandler.dump_traceback_later(...,
exit=True)` runs on its own C thread: when the deadline passes it writes every thread's stack to a file and ends the
process with exit code 1 (the only code it can use; the next start's WARNING says it was a stalled exit).

The file is `tmp\\shutdown-stall.txt`, opened in binary mode and kept open. Nothing cancels the guard: a clean exit
leaves an empty file and the next start removes it. The dump holds thread ids, file paths, line numbers and function
names, never values; it is read back through the redacting log handler at the next start (06 section 3).
"""

import faulthandler
from pathlib import Path
from typing import BinaryIO

STALL_FILE_NAME = "shutdown-stall.txt"


class ExitGuard:
    def __init__(self, tmp: Path) -> None:
        self._path = tmp / STALL_FILE_NAME
        self._file: BinaryIO | None = None
        self.armed = False

    def arm(self, seconds: float) -> None:
        """Start the countdown. The file object is kept alive for as long as the guard exists."""
        if self._file is None:
            self._file = self._path.open("wb")
        self._schedule(seconds)

    def rearm(self, seconds: float) -> None:
        """Replace the countdown by a new one (only if it was armed)."""
        if self._file is not None:
            self._schedule(seconds)

    def _schedule(self, seconds: float) -> None:
        assert self._file is not None
        faulthandler.dump_traceback_later(seconds, repeat=False, file=self._file, exit=True)
        self.armed = True
