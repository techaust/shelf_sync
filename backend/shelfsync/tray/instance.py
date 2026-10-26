"""One ShelfSync per Windows user (SYS-03).

The first copy takes a named mutex, `Local\\ShelfSync-<user SID>`, before it touches `tmp\\`, the database or the
install token. A second launch finds the name taken and becomes a second launch (a new signed-in tab), never a second
server. The mutex disappears with the process, so a crash leaves nothing stale behind.

`Local\\` is the per-logon-session namespace: another Windows user is in another session, so cannot see, block or
imitate the name; and the user's SID in the name keeps it per user. (A second logon session of the same user would
not see this one, so it could start a second server on the next free port. A lock file in the data folder that
covers every session is planned for M1b.)
"""

import sys
from typing import Protocol

from shelfsync.platform.sockets import current_user_sid


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

else:

    class WindowsInstanceLock:
        """Mutexes are a Windows thing; elsewhere this refuses to be used."""

        def __init__(self, name: str | None = None) -> None:
            raise OSError("The single-instance mutex is available on Windows only")

        def acquire(self) -> bool:
            raise OSError("not available")

        def release(self) -> None:
            raise OSError("not available")


def default_instance_lock() -> InstanceLock:
    return WindowsInstanceLock()
