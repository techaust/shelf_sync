"""Starting and watching processes for the switch (04-A V43).

The switch process is started detached, so it outlives the app that started it and the job object that app may run
in: `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB`. A job that doesn't allow breakaway
refuses that flag; the start is then tried once without it (V43 is verified outside the Claude app).

`is_running` and `terminate_pid` use Windows calls on Windows: `os.kill(pid, 0)` would END a process there.
"""

import os
import signal
import subprocess  # nosec B404  # the programs started are ShelfSync's own, with argument lists and no shell
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol

_DETACHED_PROCESS = 0x00000008
_CREATE_NEW_PROCESS_GROUP = 0x00000200
_CREATE_BREAKAWAY_FROM_JOB = 0x01000000
_CREATE_NO_WINDOW = 0x08000000


class SpawnedProcess(Protocol):
    @property
    def pid(self) -> int: ...

    def poll(self) -> int | None:
        """The exit code, or None while it runs."""
        ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...

    def wait(self, timeout: float) -> int | None:
        """Wait up to `timeout` seconds; the exit code, or None if it still runs."""
        ...


class ProcessWatch(Protocol):
    """One open handle on a process, held for as long as it is watched: the PID can't be reused by another program
    in the meantime, and the image path is the one of the process the handle was opened on."""

    @property
    def image(self) -> str | None:
        """The program file the process runs, or None if Windows won't say."""
        ...

    def is_running(self) -> bool: ...

    def close(self) -> None: ...


class Processes(Protocol):
    def is_running(self, pid: int) -> bool: ...

    def watch(self, pid: int) -> ProcessWatch | None:
        """Open a handle on the process, or None if there is no such process (or it isn't this user's to watch)."""
        ...

    def spawn_detached(
        self, argv: Sequence[str], cwd: Path, env: Mapping[str, str] | None = None
    ) -> SpawnedProcess: ...

    def terminate_pid(self, pid: int) -> None:
        """End a process by PID (a program the caller already checked is one of ShelfSync's)."""
        ...


class _Popen:
    def __init__(self, popen: subprocess.Popen[bytes]) -> None:
        self._popen = popen

    @property
    def pid(self) -> int:
        return self._popen.pid

    def poll(self) -> int | None:
        return self._popen.poll()

    def terminate(self) -> None:
        self._popen.terminate()

    def kill(self) -> None:
        self._popen.kill()

    def wait(self, timeout: float) -> int | None:
        try:
            return self._popen.wait(timeout)
        except subprocess.TimeoutExpired:
            return None


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _SYNCHRONIZE = 0x00100000
    _PROCESS_TERMINATE = 0x0001
    _WAIT_TIMEOUT = 0x102
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _kernel32.WaitForSingleObject.restype = wintypes.DWORD
    _kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    _kernel32.TerminateProcess.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL
    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    _kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    _kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL

    class _WindowsWatch:
        def __init__(self, handle: int) -> None:
            self._handle: int | None = handle

        @property
        def image(self) -> str | None:
            if self._handle is None:
                return None
            size = wintypes.DWORD(32768)
            buffer = ctypes.create_unicode_buffer(size.value)
            if not _kernel32.QueryFullProcessImageNameW(self._handle, 0, buffer, ctypes.byref(size)):
                return None
            return buffer.value

        def is_running(self) -> bool:
            return self._handle is not None and bool(_kernel32.WaitForSingleObject(self._handle, 0) == _WAIT_TIMEOUT)

        def close(self) -> None:
            if self._handle is not None:
                _kernel32.CloseHandle(self._handle)
                self._handle = None

    def _open_watch(pid: int) -> ProcessWatch | None:
        handle = _kernel32.OpenProcess(_SYNCHRONIZE | _PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        return _WindowsWatch(handle) if handle else None

    def _is_running(pid: int) -> bool:
        handle = _kernel32.OpenProcess(_SYNCHRONIZE, False, pid)
        if not handle:
            return False  # no such process (or one this user may not open: not ours to wait for)
        try:
            return bool(_kernel32.WaitForSingleObject(handle, 0) == _WAIT_TIMEOUT)
        finally:
            _kernel32.CloseHandle(handle)

    def _terminate(pid: int) -> None:
        handle = _kernel32.OpenProcess(_PROCESS_TERMINATE, False, pid)
        if not handle:
            return
        try:
            _kernel32.TerminateProcess(handle, 1)
        finally:
            _kernel32.CloseHandle(handle)

else:

    class _PosixWatch:
        def __init__(self, pid: int) -> None:
            self._pid = pid

        @property
        def image(self) -> str | None:
            try:
                return os.readlink(f"/proc/{self._pid}/exe")
            except OSError:
                return None

        def is_running(self) -> bool:
            return _is_running(self._pid)

        def close(self) -> None:
            return None

    def _open_watch(pid: int) -> ProcessWatch | None:
        return _PosixWatch(pid) if _is_running(pid) else None

    def _is_running(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def _terminate(pid: int) -> None:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            return


def _popen(
    arguments: list[str], cwd: Path, env: dict[str, str] | None, creationflags: int, new_session: bool
) -> subprocess.Popen[bytes]:
    return subprocess.Popen(  # nosec B603  # a list of arguments, no shell, ShelfSync's own program
        arguments,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        creationflags=creationflags,
        start_new_session=new_session,
    )


class RealProcesses:
    def is_running(self, pid: int) -> bool:
        return pid > 0 and _is_running(pid)

    def watch(self, pid: int) -> ProcessWatch | None:
        return _open_watch(pid) if pid > 0 else None

    def spawn_detached(self, argv: Sequence[str], cwd: Path, env: Mapping[str, str] | None = None) -> SpawnedProcess:
        arguments = list(argv)
        environment = dict(env) if env is not None else None
        if sys.platform != "win32":
            return _Popen(_popen(arguments, cwd, environment, 0, True))
        base = _DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP
        try:
            return _Popen(_popen(arguments, cwd, environment, base | _CREATE_BREAKAWAY_FROM_JOB, False))
        except PermissionError:  # the job refuses breakaway (V43): the same start, without it
            return _Popen(_popen(arguments, cwd, environment, base, False))

    def terminate_pid(self, pid: int) -> None:
        if pid > 0 and pid != os.getpid():
            _terminate(pid)


def default_processes() -> Processes:
    return RealProcesses()
