"""SYS-03, 04-A V33, 06 section 10: the decision table for "may the install token go to the program on this port?",
and the real Windows lookup of a socket's owner."""

import os
import socket
import sys
from pathlib import Path

import pytest

from shelfsync.platform import sockets
from shelfsync.platform.sockets import OwnerLookupError, ProcessInfo, Verdict

ME = "S-1-5-21-111-222-333-1001"
OTHER_USER = "S-1-5-21-111-222-333-1002"
PYTHON = str(Path(sys.executable))
EXPECTED = frozenset({sockets.normalize_image(PYTHON)})
PID = 4242


def process(pid: int = PID, sid: str = ME, image: str = PYTHON) -> ProcessInfo:
    return ProcessInfo(pid=pid, user_sid=sid, image=image)


def judge(owners: list[ProcessInfo], runtime_pid: int = PID) -> Verdict:
    return sockets.judge(owners, my_sid=ME, expected=EXPECTED, runtime_pid=runtime_pid)


# ---- the decision table (Linux and Windows) -----------------------------------------------------------------------


def test_same_user_same_python_and_the_runtime_pid_is_trusted() -> None:
    """SYS-03: the only case that gets the token."""
    assert judge([process()]) is Verdict.TRUSTED


def test_nobody_listening_is_refused() -> None:
    """SYS-03."""
    assert judge([]) is Verdict.NOBODY


def test_another_windows_user_is_refused() -> None:
    """SYS-03 (port squatting): another user's program answering like ShelfSync never gets the token."""
    assert judge([process(sid=OTHER_USER)]) is Verdict.OTHER_USER


def test_another_program_of_the_same_user_is_refused() -> None:
    """SYS-03."""
    assert judge([process(image=r"C:\Windows\System32\notepad.exe")]) is Verdict.OTHER_PROGRAM


def test_a_pid_that_is_not_the_one_in_runtime_json_is_stale() -> None:
    """SYS-03 (M1a.1 #12): runtime.json belongs to a copy that is gone, another process holds the port."""
    assert judge([process(pid=PID + 1)]) is Verdict.STALE_PID


@pytest.mark.parametrize("bad", [process(sid=OTHER_USER), process(image=r"C:\x\evil.exe"), process(pid=1)])
def test_every_process_that_could_receive_the_connection_must_pass(bad: ProcessInfo) -> None:
    """SYS-03: a listener on every address next to ShelfSync's own is one more process the token could reach."""
    assert judge([process(), bad]) is not Verdict.TRUSTED
    assert judge([bad, process()]) is not Verdict.TRUSTED


def test_the_user_sid_and_the_image_path_compare_without_case() -> None:
    """SYS-03: Windows paths and SIDs are case-insensitive."""
    upper = process(sid=ME.upper(), image=PYTHON.upper() if sys.platform == "win32" else PYTHON)
    assert judge([upper]) is Verdict.TRUSTED


def test_a_failed_lookup_is_refused_never_guessed() -> None:
    """SYS-03: an error from Windows (access denied on another user's process, say) means refuse."""

    def broken(port: int) -> list[ProcessInfo]:
        raise OwnerLookupError("OpenProcess failed (Windows error 5)")

    assert (
        sockets.check_listener(47615, PID, lookup=broken, my_sid=lambda: ME, expected=EXPECTED) is Verdict.LOOKUP_FAILED
    )


def test_a_failed_own_sid_is_refused() -> None:
    """SYS-03."""

    def no_sid() -> str:
        raise OwnerLookupError("OpenProcessToken failed")

    assert (
        sockets.check_listener(47615, PID, lookup=lambda port: [process()], my_sid=no_sid, expected=EXPECTED)
        is Verdict.LOOKUP_FAILED
    )


def test_check_listener_passes_the_port_to_the_lookup() -> None:
    """SYS-03."""
    asked: list[int] = []

    def lookup(port: int) -> list[ProcessInfo]:
        asked.append(port)
        return [process()]

    verdict = sockets.check_listener(47617, PID, lookup=lookup, my_sid=lambda: ME, expected=EXPECTED)
    assert verdict is Verdict.TRUSTED and asked == [47617]


def test_the_expected_images_hold_this_python_its_base_and_the_pythonw_pair() -> None:
    """SYS-03: a venv's python.exe starts the base interpreter, so the listening process shows the base image;
    the launcher runs pythonw.exe and the developer entry python.exe."""
    images = sockets.expected_images()
    assert sockets.normalize_image(sys.executable) in images
    base = getattr(sys, "_base_executable", sys.executable)
    assert sockets.normalize_image(base) in images
    for folder in {Path(sys.executable).parent, Path(base).parent}:
        assert sockets.normalize_image(str(folder / "python.exe")) in images
        assert sockets.normalize_image(str(folder / "pythonw.exe")) in images


def test_a_program_that_only_shares_a_folder_name_is_not_expected() -> None:
    """SYS-03."""
    assert sockets.normalize_image(r"C:\Windows\System32\notepad.exe") not in sockets.expected_images()


@pytest.mark.skipif(sys.platform == "win32", reason="the other platforms refuse")
def test_off_windows_the_lookup_refuses() -> None:
    """SYS-03: no Windows, no answer, so no token."""
    with pytest.raises(OwnerLookupError):
        sockets.listener_owners(47615)
    with pytest.raises(OwnerLookupError):
        sockets.current_user_sid()


# ---- the real thing (V33) -----------------------------------------------------------------------------------------

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


def listening_socket() -> tuple[socket.socket, int]:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    return sock, sock.getsockname()[1]


@pytest.mark.windows
@windows_only
def test_v33_a_socket_this_test_opens_is_reported_with_this_process() -> None:
    """V33: GetExtendedTcpTable gives the owner PID; the token gives the user SID; the image is the program file."""
    sock, port = listening_socket()
    try:
        owners = sockets.listener_owners(port)
    finally:
        sock.close()
    assert len(owners) == 1
    owner = owners[0]
    assert owner.pid == os.getpid()
    assert owner.user_sid == sockets.current_user_sid()
    assert owner.user_sid.startswith("S-1-5-")
    assert sockets.normalize_image(owner.image) in sockets.expected_images()


@pytest.mark.windows
@windows_only
def test_v33_a_closed_port_has_nobody() -> None:
    """V33."""
    sock, port = listening_socket()
    sock.close()
    assert sockets.listener_owners(port) == []
    assert sockets.check_listener(port, os.getpid()) is Verdict.NOBODY


@pytest.mark.windows
@windows_only
def test_v33_this_process_is_trusted_with_its_own_pid_and_stale_with_another() -> None:
    """V33: the whole check on a real socket."""
    sock, port = listening_socket()
    try:
        assert sockets.check_listener(port, os.getpid()) is Verdict.TRUSTED
        assert sockets.check_listener(port, os.getpid() + 1) is Verdict.STALE_PID
    finally:
        sock.close()


@pytest.mark.windows
@windows_only
def test_v33_a_process_this_user_may_not_open_is_refused_not_guessed() -> None:
    """V33: the System process (PID 4) can't be opened by an ordinary user; that is an error, which means refuse."""
    with pytest.raises(OwnerLookupError):
        sockets.process_info(4)


@pytest.mark.windows
@windows_only
def test_v33_the_current_sid_is_stable_and_names_this_user() -> None:
    """V33."""
    assert sockets.current_user_sid() == sockets.current_user_sid()
    owner = sockets.process_info(os.getpid())
    assert owner.user_sid == sockets.current_user_sid()
    assert owner.pid == os.getpid()
