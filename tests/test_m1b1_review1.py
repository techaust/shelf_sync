"""M1b.1 review round 1: the second launch of a `--background` start, the lock's error and retry behaviour."""

import sys
import threading
import time
from pathlib import Path

import pytest

from shelfsync import messages, server
from shelfsync.paths import DataPaths
from shelfsync.platform.notify import FakeNotifier
from shelfsync.platform.secrets import MemorySecretStore
from shelfsync.platform.shell import FakeShell
from shelfsync.tray import launcher
from shelfsync.tray.instance import FakeInstanceLock, WindowsFileLock


def test_a_background_start_that_is_a_second_launch_exits_quietly_with_no_tab(
    data_paths: DataPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SYS-03, SYS-04: signing in while ShelfSync already runs: exit 0, no tab, no toast, no second server."""
    monkeypatch.setattr(server, "default_instance_lock", lambda paths=None: FakeInstanceLock({"ShelfSync"}))
    monkeypatch.setattr(launcher.logs, "install_output_guards", lambda: None)
    shell, notifier = FakeShell(), FakeNotifier()
    assert launcher.main(["--background"], notifier=notifier, shell=shell, secrets=MemorySecretStore()) == 0
    assert shell.urls == [] and notifier.messages == []


def test_a_lock_file_that_cant_be_made_says_the_data_folder_is_the_problem(data_paths: DataPaths) -> None:
    """SYS-03: an OSError from `acquire()` (the data folder or the lock file) is START_FAILED_DATA_FOLDER."""

    class Refusing:
        def acquire(self) -> bool:
            raise OSError("access denied")

        def release(self) -> None: ...

    notifier = FakeNotifier()
    code = server.run_application(
        lambda paths: lambda app, sock: None, notifier, lambda paths: 0, lock=Refusing(), secrets=MemorySecretStore()
    )
    assert code == server.EXIT_START_FAILED
    assert notifier.messages == [messages.START_FAILED_DATA_FOLDER]


def test_run_application_hands_the_resolved_data_folder_to_the_default_lock(
    data_paths: DataPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SYS-03: the lock file is in the folder `run_application` resolved (no second resolve)."""
    seen: list[object] = []

    def make(paths: DataPaths | None = None) -> FakeInstanceLock:
        seen.append(paths)
        return FakeInstanceLock(set())

    monkeypatch.setattr(server, "default_instance_lock", make)
    server.run_application(lambda paths: lambda app, sock: None, FakeNotifier(), lambda paths: 0)
    assert seen == [data_paths]


@pytest.mark.windows
@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_a_lock_that_is_let_go_within_a_second_is_still_won(tmp_path: Path) -> None:
    """SYS-03: a quick restart: the old copy is closing while the new one asks; one second of retries covers it."""
    path = tmp_path / "instance.lock"
    first = WindowsFileLock(path)
    assert first.acquire()
    threading.Timer(0.4, first.release).start()
    started = time.monotonic()
    second = WindowsFileLock(path)
    try:
        assert second.acquire()
        assert 0.3 < time.monotonic() - started < 1.0
    finally:
        second.release()


@pytest.mark.windows
@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_a_lock_that_is_never_let_go_is_refused_after_the_retry_time(tmp_path: Path) -> None:
    """SYS-03: still fails closed: another copy."""
    path = tmp_path / "instance.lock"
    holder = WindowsFileLock(path)
    assert holder.acquire()
    try:
        started = time.monotonic()
        assert not WindowsFileLock(path, retry_seconds=0.3).acquire()
        assert time.monotonic() - started >= 0.3
    finally:
        holder.release()
