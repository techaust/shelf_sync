"""Who owns a listening socket (04-A V33, 06 section 10, SYS-03).

Before the launcher sends the install token to a running copy it asks Windows which process listens on
127.0.0.1:<port> (`GetExtendedTcpTable`, owner PID), then which Windows user runs that process and which program
file it was started from. The token goes only to a process of the same user running ShelfSync's own Python.
Another user's program, or an unrelated one, that answers `/api/health` like ShelfSync never gets it.

The Windows calls are in `listener_owners()` and `current_user_sid()`. `judge()` is the decision table; it is plain
Python so Linux CI tests it with fakes.
"""

import enum
import os
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

LOOPBACK = "127.0.0.1"
# bandit B104 is about binding; this is the address to recognise in the table of listeners, nothing is bound to it
_ANY = "0.0.0.0"  # nosec B104  # a listener on every address also receives connections to 127.0.0.1


class OwnerLookupError(Exception):
    """Windows couldn't say who owns the socket (or this isn't Windows). The message holds no secret."""


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    user_sid: str
    image: str  # full path of the program file


class Verdict(enum.Enum):
    TRUSTED = "trusted"
    NOBODY = "nobody"  # nothing listens on the port
    OTHER_USER = "other_user"
    OTHER_PROGRAM = "other_program"
    STALE_PID = "stale_pid"  # runtime.json names a different process than the one that listens
    LOOKUP_FAILED = "lookup_failed"


def normalize_image(path: str) -> str:
    """A program path in a form that can be compared: junctions and links resolved (the `current` junction points
    at the active version), case ignored, separators uniform."""
    return os.path.normcase(os.path.realpath(path))


def expected_images() -> frozenset[str]:
    """The program files a running ShelfSync can show as its image: this interpreter, the one a virtual environment
    was made from (a venv's `python.exe` starts the base interpreter, and the listening process is that one), and
    the `python.exe` / `pythonw.exe` pair beside each (the launcher and the developer entry differ in that)."""
    found: set[str] = set()
    base = getattr(sys, "_base_executable", sys.executable)
    for executable in (sys.executable, base):
        folder = Path(executable).parent
        found.add(normalize_image(executable))
        found.add(normalize_image(str(folder / "python.exe")))
        found.add(normalize_image(str(folder / "pythonw.exe")))
    return frozenset(found)


def judge(
    owners: Iterable[ProcessInfo],
    *,
    my_sid: str,
    expected: frozenset[str],
    runtime_pid: int,
) -> Verdict:
    """The launcher's decision table: send the token only on TRUSTED.

    Every process that could receive a connection to the port must pass: the same Windows user, ShelfSync's own
    Python, and the PID runtime.json names (a different PID means runtime.json is stale).
    """
    found = list(owners)
    if not found:
        return Verdict.NOBODY
    for owner in found:
        if owner.user_sid.casefold() != my_sid.casefold():
            return Verdict.OTHER_USER
    for owner in found:
        if normalize_image(owner.image) not in expected:
            return Verdict.OTHER_PROGRAM
    for owner in found:
        if owner.pid != runtime_pid:
            return Verdict.STALE_PID
    return Verdict.TRUSTED


def check_listener(
    port: int,
    runtime_pid: int,
    lookup: Callable[[int], list[ProcessInfo]] | None = None,
    my_sid: Callable[[], str] | None = None,
    expected: frozenset[str] | None = None,
) -> Verdict:
    """Look the port up and judge it. Any failure of the lookup is LOOKUP_FAILED: refuse, never guess."""
    try:
        owners = (lookup or listener_owners)(port)
        sid = (my_sid or current_user_sid)()
    except OwnerLookupError:
        return Verdict.LOOKUP_FAILED
    return judge(owners, my_sid=sid, expected=expected or expected_images(), runtime_pid=runtime_pid)


if sys.platform == "win32":
    import ctypes
    import socket
    import struct
    from ctypes import wintypes

    _ERROR_INSUFFICIENT_BUFFER = 122
    _NO_ERROR = 0
    _AF_INET = 2
    _TCP_TABLE_OWNER_PID_LISTENER = 3
    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    _TOKEN_QUERY = 0x0008
    _TOKEN_USER = 1

    _iphlpapi = ctypes.WinDLL("iphlpapi", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)

    _iphlpapi.GetExtendedTcpTable.argtypes = [
        wintypes.LPVOID,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.BOOL,
        wintypes.ULONG,
        ctypes.c_int,
        wintypes.ULONG,
    ]
    _iphlpapi.GetExtendedTcpTable.restype = wintypes.DWORD
    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL
    _kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    _kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    _kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    _kernel32.LocalFree.restype = wintypes.HLOCAL
    _advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    _advapi32.OpenProcessToken.restype = wintypes.BOOL
    _advapi32.GetTokenInformation.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    _advapi32.GetTokenInformation.restype = wintypes.BOOL
    _advapi32.ConvertSidToStringSidW.argtypes = [wintypes.LPVOID, ctypes.POINTER(wintypes.LPWSTR)]
    _advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL

    class _TcpRowOwnerPid(ctypes.Structure):
        """MIB_TCPROW_OWNER_PID: the ports are in network byte order in the low 16 bits."""

        _fields_ = [
            ("state", wintypes.DWORD),
            ("local_addr", wintypes.DWORD),
            ("local_port", wintypes.DWORD),
            ("remote_addr", wintypes.DWORD),
            ("remote_port", wintypes.DWORD),
            ("owning_pid", wintypes.DWORD),
        ]

    def _fail(what: str) -> OwnerLookupError:
        return OwnerLookupError(f"{what} failed (Windows error {ctypes.get_last_error()})")

    def _listener_pids(port: int) -> list[int]:
        """PIDs of the processes that listen on 127.0.0.1 or on every address, on this port (IPv4)."""
        size = wintypes.DWORD(0)
        code = _iphlpapi.GetExtendedTcpTable(
            None, ctypes.byref(size), False, _AF_INET, _TCP_TABLE_OWNER_PID_LISTENER, 0
        )
        for _ in range(5):  # the table can grow between the two calls
            if code not in (_ERROR_INSUFFICIENT_BUFFER, _NO_ERROR):
                raise OwnerLookupError(f"GetExtendedTcpTable failed (Windows error {code})")
            buffer = ctypes.create_string_buffer(size.value)
            code = _iphlpapi.GetExtendedTcpTable(
                buffer, ctypes.byref(size), False, _AF_INET, _TCP_TABLE_OWNER_PID_LISTENER, 0
            )
            if code == _NO_ERROR:
                break
        else:
            raise OwnerLookupError("GetExtendedTcpTable kept changing size")
        (count,) = struct.unpack_from("<I", buffer, 0)
        rows = (_TcpRowOwnerPid * count).from_buffer_copy(buffer, 4) if count else ()
        pids: list[int] = []
        for row in rows:
            address = socket.inet_ntoa(row.local_addr.to_bytes(4, "little"))
            if socket.ntohs(row.local_port & 0xFFFF) == port and address in (LOOPBACK, _ANY):
                pids.append(row.owning_pid)
        return pids

    def _sid_of_process(handle: int) -> str:
        token = wintypes.HANDLE()
        if not _advapi32.OpenProcessToken(handle, _TOKEN_QUERY, ctypes.byref(token)):
            raise _fail("OpenProcessToken")
        try:
            needed = wintypes.DWORD(0)
            _advapi32.GetTokenInformation(token, _TOKEN_USER, None, 0, ctypes.byref(needed))
            if needed.value == 0:
                raise _fail("GetTokenInformation")
            buffer = ctypes.create_string_buffer(needed.value)
            if not _advapi32.GetTokenInformation(token, _TOKEN_USER, buffer, needed, ctypes.byref(needed)):
                raise _fail("GetTokenInformation")
            sid_pointer = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0]  # TOKEN_USER starts with the SID
            text = wintypes.LPWSTR()
            if not _advapi32.ConvertSidToStringSidW(sid_pointer, ctypes.byref(text)):
                raise _fail("ConvertSidToStringSid")
            try:
                return str(text.value)
            finally:
                _kernel32.LocalFree(ctypes.cast(text, wintypes.HLOCAL))
        finally:
            _kernel32.CloseHandle(token)

    def _image_of_process(handle: int) -> str:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not _kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            raise _fail("QueryFullProcessImageName")
        return buffer.value

    def process_info(pid: int) -> ProcessInfo:
        """The user SID and program path of a process. A process this user may not query (another user's) raises
        OwnerLookupError, which callers treat as "refuse"."""
        handle = _kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            raise _fail("OpenProcess")
        try:
            return ProcessInfo(pid=pid, user_sid=_sid_of_process(handle), image=_image_of_process(handle))
        finally:
            _kernel32.CloseHandle(handle)

    def current_user_sid() -> str:
        """The SID of the Windows user running this process, as text (S-1-5-21-...)."""
        return _sid_of_process(_kernel32.GetCurrentProcess())

    def listener_owners(port: int) -> list[ProcessInfo]:
        """Every process listening on 127.0.0.1:<port> (or on all addresses). Empty if nobody does."""
        return [process_info(pid) for pid in sorted(set(_listener_pids(port)))]

else:

    def process_info(pid: int) -> ProcessInfo:
        raise OwnerLookupError("Processes can be looked up on Windows only")

    def current_user_sid() -> str:
        raise OwnerLookupError("Socket owners can be looked up on Windows only")

    def listener_owners(port: int) -> list[ProcessInfo]:
        raise OwnerLookupError("Socket owners can be looked up on Windows only")
