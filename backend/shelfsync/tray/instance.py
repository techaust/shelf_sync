"""One ShelfSync per Windows user (SYS-03).

The first copy takes a named mutex, `Local\\ShelfSync-<user SID>`, before it touches `tmp\\`, the database or the
install token. A second launch finds the name taken and becomes a second launch (a new signed-in tab), never a second
server. The mutex disappears with the process, so a crash leaves nothing stale behind.

`Local\\` is the per-logon-session namespace: another Windows user is in another session, so cannot see, block or
imitate the name; and the user's SID in the name keeps it per user. A second logon session of the same user would
not see the mutex, so the first copy also holds `instance.lock` in the data folder, opened with no sharing for the
life of the process: any session of that user finds it taken. `default_instance_lock()` takes the mutex first, then
the file; either one taken means a second launch. Windows closes both handles when the process ends, so a crash
leaves no stale lock. The installer and uninstaller also try to open the file to tell whether ShelfSync is running.
"""

import sys
import time
from pathlib import Path
from typing import Protocol

from shelfsync.paths import DataPaths, resolve_data_paths
from shelfsync.platform.sockets import current_user_sid

# A sharing violation on instance.lock may be a copy that is just closing (a quick restart): look again for about a
# second before deciding another copy runs. A folder where the file should be is refused at once.
LOCK_RETRY_SECONDS = 1.0
_RETRY_STEP_SECONDS = 0.1


def mutex_name(sid: str) -> str:
    return f"Local\\ShelfSync-{sid}"


class InstanceLock(Protocol):
    def acquire(self) -> bool:
        """True if this process is now the one ShelfSync; False if another copy already is."""
        ...

    def release(self) -> None: ...


class FakeInstanceLock:
    """Process-local stand-in for tests and Linux CI: locks sharing one `taken` set behave like one PC."""

    def __init__(self, taken: set[str] | None = None, name: str = "ShelfSync") -> None:
        self._taken = taken if taken is not None else set()
        self._name = name
        self._held = False

    def acquire(self) -> bool:
        if self._name in self._taken:
            return False
        self._taken.add(self._name)
        self._held = True
        return True

    def release(self) -> None:
        if self._held:
            self._taken.discard(self._name)
            self._held = False


class CombinedInstanceLock:
    """Two locks that must both be won: `first` (the mutex), then `second` (the data-folder lock file). If the second
    is refused the first is given back, so a refused launch holds nothing."""

    def __init__(self, first: InstanceLock, second: InstanceLock) -> None:
        self._first = first
        self._second = second
        self._held = False

    def acquire(self) -> bool:
        if self._held:
            return True
        if not self._first.acquire():
            return False
        try:
            won = self._second.acquire()
        except BaseException:
            self._first.release()
            raise
        if not won:
            self._first.release()
            return False
        self._held = True
        return True

    def release(self) -> None:
        self._second.release()
        self._first.release()
        self._held = False


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _ERROR_ALREADY_EXISTS = 183
    _ERROR_ACCESS_DENIED = 5

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    _kernel32.CreateMutexW.restype = wintypes.HANDLE
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL

    class WindowsInstanceLock:
        """The named mutex. The handle is kept open for the life of the process; closing it releases the name."""

        def __init__(self, name: str | None = None) -> None:
            self._name = name or mutex_name(current_user_sid())
            self._handle: int | None = None

        def acquire(self) -> bool:
            if self._handle is not None:
                return True
            handle = _kernel32.CreateMutexW(None, False, self._name)
            error = ctypes.get_last_error()
            if not handle:
                # An object of this name exists that this user can't open: not ours, so not the first copy.
                if error == _ERROR_ACCESS_DENIED:
                    return False
                raise OSError(f"CreateMutexW failed (Windows error {error})")
            if error == _ERROR_ALREADY_EXISTS:
                _kernel32.CloseHandle(handle)
                return False
            self._handle = handle
            return True

        def release(self) -> None:
            if self._handle is not None:
                _kernel32.CloseHandle(self._handle)
                self._handle = None

    _ERROR_SHARING_VIOLATION = 32
    _ERROR_LOCK_VIOLATION = 33
    _GENERIC_READ_WRITE = 0xC0000000
    _OPEN_ALWAYS = 4
    _FILE_ATTRIBUTE_NORMAL = 0x80
    _FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000  # a planted link is opened itself, never followed to its target
    _INVALID_HANDLE = ctypes.c_void_p(-1).value

    _kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    _kernel32.CreateFileW.restype = wintypes.HANDLE

    class WindowsFileLock:
        """`instance.lock` opened with share mode 0: no other process (or session) can open it while this one holds
        the handle. The file is empty; its only use is being open."""

        def __init__(self, path: Path, retry_seconds: float = LOCK_RETRY_SECONDS) -> None:
            self._path = path
            self._retry_seconds = retry_seconds
            self._handle: int | None = None

        def acquire(self) -> bool:
            if self._handle is not None:
                return True
            self._path.parent.mkdir(parents=True, exist_ok=True)
            deadline = time.monotonic() + self._retry_seconds
            while True:
                handle = _kernel32.CreateFileW(
                    str(self._path),
                    _GENERIC_READ_WRITE,
                    0,
                    None,
                    _OPEN_ALWAYS,
                    _FILE_ATTRIBUTE_NORMAL | _FILE_FLAG_OPEN_REPARSE_POINT,
                    None,
                )
                if handle is not None and handle != _INVALID_HANDLE:
                    self._handle = handle
                    return True
                error = ctypes.get_last_error()
                if error == _ERROR_ACCESS_DENIED:  # a folder where the file should be: fail closed, no retry
                    return False
                if error not in (_ERROR_SHARING_VIOLATION, _ERROR_LOCK_VIOLATION):
                    raise OSError(f"The lock file couldn't be opened (Windows error {error})")
                if time.monotonic() >= deadline:
                    return False  # held by another copy
                time.sleep(_RETRY_STEP_SECONDS)  # the other copy may be closing right now (a quick restart)

        def release(self) -> None:
            if self._handle is not None:
                _kernel32.CloseHandle(self._handle)
                self._handle = None

else:

    class WindowsFileLock:
        """The lock file needs Windows' share modes; elsewhere this refuses to be used."""

        def __init__(self, path: Path, retry_seconds: float = 0.0) -> None:
            raise OSError("The data-folder lock is available on Windows only")

        def acquire(self) -> bool:
            raise OSError("not available")

        def release(self) -> None:
            raise OSError("not available")

    class WindowsInstanceLock:
        """Mutexes are a Windows thing; elsewhere this refuses to be used."""

        def __init__(self, name: str | None = None) -> None:
            raise OSError("The single-instance mutex is available on Windows only")

        def acquire(self) -> bool:
            raise OSError("not available")

        def release(self) -> None:
            raise OSError("not available")


def default_instance_lock(paths: DataPaths | None = None) -> InstanceLock:
    """The mutex and the data-folder lock file together (SYS-03, M1b.1). `paths` is the data folder the caller already
    resolved; with no argument it is resolved here."""
    data = paths if paths is not None else resolve_data_paths()
    return CombinedInstanceLock(WindowsInstanceLock(), WindowsFileLock(data.instance_lock))
