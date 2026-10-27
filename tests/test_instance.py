"""SYS-03: one ShelfSync per Windows user, by a named mutex taken before anything else is touched."""

import secrets
import sys
import threading

import pytest

from shelfsync.platform.sockets import current_user_sid
from shelfsync.tray import instance
from shelfsync.tray.instance import FakeInstanceLock, mutex_name


def test_the_name_holds_the_user_sid_in_the_local_namespace() -> None:
    """SYS-03: `Local\\` (this logon session, so no other user can see or imitate it) plus the user's SID."""
    assert mutex_name("S-1-5-21-1-2-3-1001") == "Local\\ShelfSync-S-1-5-21-1-2-3-1001"


def test_the_first_lock_wins_the_second_does_not_and_release_frees_it() -> None:
    """SYS-03 (the fake follows the same contract as the real mutex)."""
    taken: set[str] = set()
    first, second = FakeInstanceLock(taken), FakeInstanceLock(taken)
    assert first.acquire()
    assert not second.acquire()
    second.release()  # a lock that never got the name doesn't free the first one's
    assert not FakeInstanceLock(taken).acquire()
    first.release()
    assert second.acquire()


@pytest.mark.skipif(sys.platform == "win32", reason="the other platforms refuse")
def test_off_windows_the_real_mutex_refuses_to_pretend() -> None:
    """SYS-03."""
    with pytest.raises(OSError):
        instance.default_instance_lock()


windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


@pytest.mark.windows
@windows_only
def test_the_real_mutex_lets_one_holder_in_and_frees_the_name_on_release() -> None:
    """SYS-03: a throwaway name, so a running ShelfSync can't interfere."""
    name = f"Local\\ShelfSync-test-{secrets.token_hex(6)}"
    first, second, third = (instance.WindowsInstanceLock(name) for _ in range(3))
    try:
        assert first.acquire()
        assert first.acquire()  # asking again is still "yes", not a second handle
        assert not second.acquire()
        first.release()
        assert third.acquire()
        assert not second.acquire()
    finally:
        for lock in (first, second, third):
            lock.release()


@pytest.mark.windows
@windows_only
def test_the_real_mutex_is_seen_from_another_thread() -> None:
    """SYS-03: the name is process-wide, not per thread."""
    name = f"Local\\ShelfSync-test-{secrets.token_hex(6)}"
    holder = instance.WindowsInstanceLock(name)
    other = instance.WindowsInstanceLock(name)
    answers: list[bool] = []
    try:
        assert holder.acquire()
        thread = threading.Thread(target=lambda: answers.append(other.acquire()))
        thread.start()
        thread.join()
        assert answers == [False]
    finally:
        holder.release()
        other.release()


@pytest.mark.windows
@windows_only
def test_the_default_name_is_this_users_and_the_lock_is_usable() -> None:
    """SYS-03: only checks the name that the app would use; the lock is released at once (a running ShelfSync on
    this PC would make `acquire` False, so that part isn't asserted)."""
    lock = instance.WindowsInstanceLock()
    assert lock._name == mutex_name(current_user_sid())
    lock.release()
