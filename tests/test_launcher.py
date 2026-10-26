"""SYS-02, SYS-03: the launcher's process model: uvicorn in a thread, the tray, Open ShelfSync, View logs, Quit, Ctrl+C.
The tray is a fake; the server is real uvicorn on a real loopback socket."""

import asyncio
import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar

import httpx
import pytest
from fastapi import FastAPI

from shelfsync import messages, server
from shelfsync.api.app import create_app
from shelfsync.paths import DataPaths
from shelfsync.platform.autostart import FakeRunKey
from shelfsync.platform.notify import FakeNotifier
from shelfsync.platform.secrets import MemorySecretStore
from shelfsync.platform.shell import FakeShell, ShellError
from shelfsync.secure.token import InstallToken
from shelfsync.tray import launcher
from shelfsync.tray.launcher import TrayServe


class FakeTray:
    instances: ClassVar[list["FakeTray"]] = []
    on_stop: ClassVar[Callable[[], None] | None] = None

    def __init__(
        self, state: Any, on_open: Callable[[], None], on_view_logs: Callable[[], None], on_quit: Callable[[], None]
    ) -> None:
        self.on_open, self.on_view_logs, self.on_quit = on_open, on_view_logs, on_quit
        self.started = self.stopped = False
        FakeTray.instances.append(self)

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True
        if FakeTray.on_stop is not None:
            FakeTray.on_stop()


class Running:
    """TrayServe running its wait loop in a thread, on a real server."""

    def __init__(self, data_paths: DataPaths, open_first_tab: bool = True) -> None:
        FakeTray.instances = []
        self.events: list[str] = []
        FakeTray.on_stop = self._tray_stopped
        self.shell, self.notifier = FakeShell(), FakeNotifier()
        self.serve = TrayServe(data_paths, self.notifier, self.shell, make_tray=FakeTray, open_first_tab=open_first_tab)
        self.paths = data_paths
        self.sock = server.bind_first_free([0])
        assert self.sock is not None
        self.port = self.sock.getsockname()[1]
        self.app: FastAPI = create_app(self.port, InstallToken(MemorySecretStore()))
        self.error: list[BaseException] = []
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        assert self.sock is not None
        try:
            self.serve(self.app, self.sock)
        except BaseException as error:
            self.error.append(error)
        finally:
            self.sock.close()

    def _tray_stopped(self) -> None:
        """Called when the tray is told to stop: is the server still up at that moment?"""
        try:
            self.events.append(f"tray stopped, server answers {self.health()}")
        except httpx.TransportError:
            self.events.append("tray stopped, server already down")

    def start(self) -> "Running":
        self.thread.start()
        assert wait_for(lambda: bool(FakeTray.instances) and FakeTray.instances[0].started)
        return self

    @property
    def tray(self) -> FakeTray:
        return FakeTray.instances[0]

    def health(self) -> int:
        return httpx.get(f"http://127.0.0.1:{self.port}/api/health", timeout=3, trust_env=False).status_code

    def finish(self) -> None:
        self.serve.request_quit()
        self.thread.join(timeout=20)
        assert not self.thread.is_alive()


def wait_for(condition: Callable[[], bool], seconds: float = 10.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return condition()


@pytest.fixture
def running(data_paths: DataPaths) -> Running:
    return Running(data_paths)


def test_it_serves_shows_the_tray_and_opens_one_signed_in_tab(running: Running) -> None:
    """SYS-02, SYS-03: the first copy's tab comes from `issue_ticket()` in-process: 127.0.0.1, one fresh ticket."""
    running.start()
    try:
        assert running.health() == 200
        assert running.tray.started
        (url,) = running.shell.urls
        assert url.startswith(f"http://127.0.0.1:{running.port}/#t=")
    finally:
        running.finish()
    assert running.error == []


def test_open_shelfsync_gives_a_fresh_ticket_each_time_and_each_signs_in_once(running: Running) -> None:
    """UI-TRAY: the default item (and a click on the icon) opens a new tab with a new single-use ticket."""
    running.start()
    try:
        running.tray.on_open()
        running.tray.on_open()
        tickets = [url.split("#t=", 1)[1] for url in running.shell.urls]
        assert len(tickets) == 3 and len(set(tickets)) == 3
        browser = httpx.Client(base_url=f"http://127.0.0.1:{running.port}", trust_env=False)
        headers = {"Origin": f"http://127.0.0.1:{running.port}", "X-ShelfSync": "1"}
        assert [browser.post("/api/session", json={"ticket": t}, headers=headers).status_code for t in tickets] == [
            204
        ] * 3
        assert browser.post("/api/session", json={"ticket": tickets[0]}, headers=headers).status_code == 401
        browser.close()
    finally:
        running.finish()


def test_the_first_tab_can_be_left_out(data_paths: DataPaths) -> None:
    """SYS-02."""
    running = Running(data_paths, open_first_tab=False).start()
    try:
        assert running.shell.urls == []
    finally:
        running.finish()


def test_view_logs_opens_the_logs_folder(running: Running) -> None:
    """UI-TRAY: View logs opens `logs\\` in Explorer."""
    running.start()
    try:
        running.tray.on_view_logs()
        assert running.shell.folders == [running.paths.logs]
    finally:
        running.finish()


def test_quit_stops_the_tray_then_the_server_and_returns(running: Running) -> None:
    """UI-TRAY: Quit stops the tray, shuts uvicorn down cleanly and the call returns (exit 0 follows)."""
    running.start()
    assert running.health() == 200
    running.tray.on_quit()
    running.thread.join(timeout=20)
    assert not running.thread.is_alive()
    assert running.error == [] and running.tray.stopped
    # The order: the tray is stopped while the server still answers; only then does the server shut down.
    assert running.events == ["tray stopped, server answers 200"]
    with pytest.raises(httpx.TransportError):
        running.health()  # the port is closed
    # ... and the uvicorn thread really ended (not just the call that waited for it)
    assert [t for t in threading.enumerate() if t.name == "uvicorn"] == []


def test_quit_waits_while_a_guard_says_an_upload_is_running(running: Running) -> None:
    """UI-TRAY: the hook for M5. No upload exists yet, so nothing registers one and Quit is immediate."""
    busy = [True]
    running.serve.add_quit_guard(lambda: not busy[0])
    running.start()
    try:
        running.tray.on_quit()
        time.sleep(0.3)
        assert running.thread.is_alive()
        busy[0] = False
        running.tray.on_quit()
        running.thread.join(timeout=20)
        assert not running.thread.is_alive()
    finally:
        busy[0] = False
        running.finish()


def test_ctrl_c_in_the_wait_loop_stops_the_tray_and_the_server_and_propagates(
    running: Running, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SYS-02: the wait loop is interruptible, so Ctrl+C in a console stops everything (start-up makes it exit 0)."""
    calls = [0]
    real_wait = running.serve._quit.wait

    def interrupted(timeout: float | None = None) -> bool:
        calls[0] += 1
        if calls[0] > 2:
            raise KeyboardInterrupt
        return real_wait(timeout)

    monkeypatch.setattr(running.serve._quit, "wait", interrupted)
    running.thread.start()
    running.thread.join(timeout=20)
    assert not running.thread.is_alive()
    assert len(running.error) == 1 and isinstance(running.error[0], KeyboardInterrupt)
    assert running.tray.stopped
    with pytest.raises(httpx.TransportError):
        running.health()


def test_a_server_that_dies_ends_the_launcher_with_an_error(
    data_paths: DataPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SYS-02: a tray with no server is useless; a server that was up and then dies reaches start-up as
    `ServerStoppedError` (its own notice and exit code, not "couldn't start")."""

    def broken_serve(self: Any, sockets: Any = None) -> None:
        self.started = True  # it came up ...
        time.sleep(0.3)
        raise RuntimeError("uvicorn crashed")  # ... and then died

    monkeypatch.setattr(launcher.uvicorn.Server, "serve", broken_serve)
    running = Running(data_paths)
    running.thread.start()
    running.thread.join(timeout=20)
    assert not running.thread.is_alive()
    assert len(running.error) == 1 and isinstance(running.error[0], server.ServerStoppedError)
    assert running.tray.stopped  # the tray went away with it


def test_a_server_that_never_starts_is_still_a_start_failure(
    data_paths: DataPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SYS-02: the other path stays "couldn't start", not "stopped unexpectedly"."""
    monkeypatch.setattr(launcher, "SERVER_START_SECONDS", 0.2)

    def never_starts(self: Any, sockets: Any = None) -> None:
        time.sleep(1.0)

    monkeypatch.setattr(launcher.uvicorn.Server, "serve", never_starts)
    running = Running(data_paths)
    running.thread.start()
    running.thread.join(timeout=20)
    assert len(running.error) == 1
    assert isinstance(running.error[0], RuntimeError) and not isinstance(running.error[0], server.ServerStoppedError)


def test_a_tab_that_cant_be_opened_is_a_notice_and_not_a_crash(data_paths: DataPaths) -> None:
    """SYS-02: no default browser, say."""

    class NoBrowser(FakeShell):
        def open_url(self, url: str) -> None:
            raise ShellError("Windows couldn't open the address (OSError)")

    running = Running(data_paths, open_first_tab=False)
    running.serve._shell = NoBrowser()
    running.start()
    try:
        running.tray.on_open()
        assert running.notifier.messages == [messages.LAUNCH_NO_SIGN_IN]
    finally:
        running.finish()


def test_the_sign_in_address_is_never_logged(running: Running, caplog: pytest.LogCaptureFixture) -> None:
    """LOG-01: no ticket and no `#t=` in any log line."""
    with caplog.at_level("DEBUG"):
        running.start()
        try:
            running.tray.on_open()
            tickets = [url.split("#t=", 1)[1] for url in running.shell.urls]
        finally:
            running.finish()
    assert "#t=" not in caplog.text
    assert all(ticket not in caplog.text for ticket in tickets)


# ---- the Start-with-Windows hook -------------------------------------------------------------------------


def test_the_settings_hook_applies_start_with_windows_and_skips_in_development(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """SYS-04: from `start_with_windows` (default true). This is a development run, so nothing is written."""
    key = FakeRunKey()
    apply = launcher.make_on_settings(key, installed=False)
    with caplog.at_level("INFO", logger="shelfsync.autostart"):
        apply({"start_with_windows": True})
    assert "skipped" in caplog.text
    assert key.values == {}


def test_the_settings_hook_sets_and_removes_the_run_value_of_an_installed_copy() -> None:
    """SYS-04: on a fake key, with `installed` forced, so the owner's real Run key is never involved."""
    key = FakeRunKey()
    launcher.make_on_settings(key, installed=True)({"start_with_windows": True})
    assert list(key.values) == ["ShelfSync"] and key.values["ShelfSync"].endswith("-m shelfsync.launcher")
    launcher.make_on_settings(key, installed=True)({"start_with_windows": False})
    assert key.values == {}


def test_a_run_key_error_is_logged_and_start_up_continues(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """SYS-04."""
    from shelfsync.platform.autostart import AutostartError

    def refuse(enabled: bool, run_key: object = None, installed: object = None) -> str:
        raise AutostartError("Writing the Run key failed (PermissionError)")

    monkeypatch.setattr(launcher, "apply_start_with_windows", refuse)
    with caplog.at_level("WARNING", logger="shelfsync.launcher"):
        launcher.make_on_settings()({"start_with_windows": True})
    assert "couldn't be applied" in caplog.text


# ---- main() ----------------------------------------------------------------------------------------------


def test_main_first_copy_wires_the_log_failure_notice_and_runs(
    data_paths: DataPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    """LOG-01 (R6), SYS-03: `main` sets the one-time log-failure toast and goes through run_application."""
    from shelfsync import logs
    from shelfsync.tray.instance import FakeInstanceLock

    monkeypatch.setattr(server, "default_instance_lock", lambda: FakeInstanceLock(set()))
    monkeypatch.setattr(launcher.logs, "install_output_guards", lambda: None)
    served: list[bool] = []
    monkeypatch.setattr(launcher.TrayServe, "__call__", lambda self, app, sock: served.append(True))
    notifier = FakeNotifier()
    try:
        assert launcher.main(notifier=notifier, shell=FakeShell(), secrets=MemorySecretStore()) == 0
        assert served == [True]
        # the notice is wired: a failed log write now reaches the notifier, once
        assert logs._write_failure_notice is not None
        logs._write_failure_notice()
        assert notifier.messages == [messages.LOG_WRITE_FAILED]
    finally:
        logs.set_write_failure_notice(None)


def test_main_second_launch_goes_to_second_launch_and_not_to_the_server(
    data_paths: DataPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SYS-03."""
    from shelfsync import logs
    from shelfsync.tray.instance import FakeInstanceLock

    monkeypatch.setattr(server, "default_instance_lock", lambda: FakeInstanceLock({"ShelfSync"}))
    monkeypatch.setattr(launcher.logs, "install_output_guards", lambda: None)
    asked: list[DataPaths] = []

    kinds: list[str] = []

    def fake_second(paths: DataPaths, notifier: Any, shell: Any, store: Any) -> int:
        asked.append(paths)
        kinds.extend(type(h).__name__ for h in logging.getLogger().handlers if "Redacting" in type(h).__name__)
        return 0

    data_paths.logs.mkdir(parents=True)  # the running copy has made it

    monkeypatch.setattr(launcher, "second_launch", fake_second)
    monkeypatch.setattr(launcher.TrayServe, "__call__", lambda self, app, sock: pytest.fail("a second server"))
    try:
        assert launcher.main(notifier=FakeNotifier(), shell=FakeShell(), secrets=MemorySecretStore()) == 0
    finally:
        logs.set_write_failure_notice(None)
    assert asked == [data_paths]
    assert kinds == ["RedactingAppendHandler"]  # logs to the shared file without ever rotating it
    assert not data_paths.database.exists() and not data_paths.tmp.exists()


def test_the_launcher_module_is_the_installed_entry_point() -> None:
    """SYS-02: `pythonw -m shelfsync.launcher` (04 section 8) imports `main` from the tray package."""
    import shelfsync.launcher as entry

    assert entry.main is launcher.main


def test_a_server_that_returns_by_itself_without_a_quit_is_reported_as_stopped(
    data_paths: DataPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SYS-02 (re-check L2): no exception, no Quit: the server just ended. That is "stopped unexpectedly", not a quiet
    exit 0, and the tray goes away with it."""

    async def returns(self: Any, sockets: Any = None) -> None:
        self.started = True
        await asyncio.sleep(0.3)

    monkeypatch.setattr(launcher.uvicorn.Server, "serve", returns)
    running = Running(data_paths)
    running.thread.start()
    running.thread.join(timeout=20)
    assert not running.thread.is_alive()
    assert len(running.error) == 1 and isinstance(running.error[0], server.ServerStoppedError)
    assert running.error[0].__cause__ is None
    assert running.tray.stopped


def test_a_quit_that_ends_the_server_is_not_reported_as_stopped(running: Running) -> None:
    """SYS-02 (re-check L2): the flag distinguishes a Quit from the server ending on its own."""
    running.start()
    running.finish()
    assert running.error == []


def test_the_stopped_error_keeps_the_crash_as_its_cause(data_paths: DataPaths, monkeypatch: pytest.MonkeyPatch) -> None:
    """SYS-02 (re-check L1): the log shows why the server died."""

    def broken(self: Any, sockets: Any = None) -> None:
        self.started = True
        time.sleep(0.2)
        raise RuntimeError("uvicorn crashed")

    monkeypatch.setattr(launcher.uvicorn.Server, "serve", broken)
    running = Running(data_paths)
    running.thread.start()
    running.thread.join(timeout=20)
    (error,) = running.error
    assert isinstance(error, server.ServerStoppedError)
    assert isinstance(error.__cause__, RuntimeError) and str(error.__cause__) == "uvicorn crashed"


def test_a_log_file_that_cant_be_opened_doesnt_stop_the_second_launch(
    data_paths: DataPaths, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """SYS-03 (re-check L3): the handler opens its file at the first line (`delay=True`). One that still can't be
    opened is a reported write failure, and the second launch carries on to open the tab."""
    from shelfsync import logs
    from shelfsync.tray.instance import FakeInstanceLock

    monkeypatch.setattr(server, "default_instance_lock", lambda: FakeInstanceLock({"ShelfSync"}))
    monkeypatch.setattr(launcher.logs, "install_output_guards", lambda: None)
    (data_paths.logs / logs.LOG_FILE_NAME).mkdir(parents=True)  # a folder where the log file should be
    ran: list[int] = []

    def fake_second(paths: DataPaths, notifier: Any, shell: Any, store: Any) -> int:
        logging.getLogger("shelfsync.launcher").warning("second launch")  # tries the file: can't
        ran.append(1)
        return 0

    monkeypatch.setattr(launcher, "second_launch", fake_second)
    try:
        code = launcher.main(notifier=FakeNotifier(), shell=FakeShell(), secrets=MemorySecretStore())
    finally:
        logs.set_write_failure_notice(None)
    assert code == 0 and ran == [1]
    assert "A log line couldn't be written" in capfd.readouterr().err


def test_a_handler_that_cant_even_be_built_means_no_file_log_not_a_failed_start(
    data_paths: DataPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SYS-03 (re-check L3)."""
    data_paths.logs.mkdir(parents=True)

    def refuse(logs_dir: Any) -> Any:
        raise PermissionError("no")

    monkeypatch.setattr(launcher.logs, "configure_append_logging", refuse)
    assert launcher._append_logging(data_paths) is None


def test_the_append_handler_makes_no_file_until_the_first_line(tmp_path: Path) -> None:
    """SYS-03 (re-check L3): `delay=True`."""
    from shelfsync import logs

    handler = logs.configure_append_logging(tmp_path)
    try:
        assert list(tmp_path.iterdir()) == []
    finally:
        logs.remove_logging(handler)
