"""M1a.5, the safety exit (UI-TRAY, SYS-02, SYS-03): the guard is armed on every way out and re-armed after
`run_application`; a stalled exit is ended with a stack dump that holds no values; the next start logs the dump
through `redact` and removes it. A real guard never runs in-process (it would end pytest)."""

import asyncio
import faulthandler
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from shelfsync import server
from shelfsync.paths import DataPaths
from shelfsync.secure.redact import register_secret
from shelfsync.tray import launcher
from shelfsync.tray.exit_guard import STALL_FILE_NAME, ExitGuard
from tests.test_launcher import FakeTray, Running, wait_for
from tests.test_run_application import go
from tests.test_server import RecordingServe

BACKEND = Path(__file__).parents[1] / "backend"


class FakeGuard:
    """Records what the launcher asks of the guard; nothing is ever scheduled."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, float]] = []
        self.armed = False

    def arm(self, seconds: float) -> None:
        self.calls.append(("arm", seconds))
        self.armed = True

    def rearm(self, seconds: float) -> None:
        self.calls.append(("rearm", seconds))


def with_guard(running: Running) -> FakeGuard:
    guard = FakeGuard()
    running.serve._exit_guard = guard  # type: ignore[assignment]
    return guard


# ---- the launcher arms the guard ----------------------------------------------------------------


def test_exit_guard_arms_on_quit_crash_and_ctrl_c_and_rearms_after_run_application(
    data_paths: DataPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    """UI-TRAY, SYS-02: stage 1 (45 s) on every way out, before the tray is stopped; stage 2 (5 s) in `main()`."""
    # Quit
    running = Running(data_paths)
    guard = with_guard(running)
    order: list[str] = []
    FakeTray.on_stop = lambda: order.append(f"tray stopped after {guard.calls}")
    running.start()
    FakeTray.on_stop = lambda: order.append(f"tray stopped after {guard.calls}")
    running.finish()
    assert guard.calls == [("arm", launcher.STAGE1_SECONDS)] and launcher.STAGE1_SECONDS == 45.0
    assert order == ["tray stopped after [('arm', 45.0)]"]  # armed before the tray was stopped

    # Ctrl+C
    running = Running(data_paths)
    guard = with_guard(running)
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
    assert not running.thread.is_alive() and guard.calls == [("arm", 45.0)]

    # a server crash
    def broken(self: Any, sockets: Any = None) -> None:
        self.started = True
        time.sleep(0.2)
        raise RuntimeError("uvicorn crashed")

    monkeypatch.setattr(launcher.uvicorn.Server, "serve", broken)
    running = Running(data_paths)
    guard = with_guard(running)
    running.thread.start()
    running.thread.join(timeout=20)
    assert not running.thread.is_alive() and guard.calls == [("arm", 45.0)]


def test_main_rearms_for_five_seconds_only_if_the_guard_was_armed(
    data_paths: DataPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    """UI-TRAY, SYS-02: stage 2."""
    from shelfsync.platform.notify import FakeNotifier
    from shelfsync.platform.secrets import MemorySecretStore
    from shelfsync.platform.shell import FakeShell
    from shelfsync.tray.instance import FakeInstanceLock

    monkeypatch.setattr(server, "default_instance_lock", lambda: FakeInstanceLock(set()))
    monkeypatch.setattr(launcher.logs, "install_output_guards", lambda: None)
    guard = FakeGuard()
    monkeypatch.setattr(launcher.TrayServe, "__call__", lambda self, app, sock: guard.arm(45.0))
    assert launcher.main(notifier=FakeNotifier(), shell=FakeShell(), secrets=MemorySecretStore(), exit_guard=guard) == 0  # type: ignore[arg-type]
    assert guard.calls == [("arm", 45.0), ("rearm", launcher.STAGE2_SECONDS)] and launcher.STAGE2_SECONDS == 5.0

    idle = FakeGuard()  # never armed (a second launch, a start failure): nothing to re-arm
    monkeypatch.setattr(launcher.TrayServe, "__call__", lambda self, app, sock: None)
    assert launcher.main(notifier=FakeNotifier(), shell=FakeShell(), secrets=MemorySecretStore(), exit_guard=idle) == 0  # type: ignore[arg-type]
    assert idle.calls == []


def test_in_process_main_never_arms_a_real_guard(data_paths: DataPaths, monkeypatch: pytest.MonkeyPatch) -> None:
    """UI-TRAY: `main()` builds no guard by itself; only the module's `__main__` does, and building it arms nothing."""
    import shelfsync.launcher as entry
    from shelfsync.platform.notify import FakeNotifier
    from shelfsync.platform.secrets import MemorySecretStore
    from shelfsync.platform.shell import FakeShell
    from shelfsync.tray.instance import FakeInstanceLock

    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("a real faulthandler timer was scheduled")

    monkeypatch.setattr(faulthandler, "dump_traceback_later", forbidden)
    monkeypatch.setattr(server, "default_instance_lock", lambda: FakeInstanceLock(set()))
    monkeypatch.setattr(launcher.logs, "install_output_guards", lambda: None)
    guards: list[Any] = []
    monkeypatch.setattr(launcher.TrayServe, "__call__", lambda self, app, sock: guards.append(self._exit_guard))
    assert launcher.main(notifier=FakeNotifier(), shell=FakeShell(), secrets=MemorySecretStore()) == 0
    assert guards == [None]
    built = entry.real_exit_guard()
    assert isinstance(built, ExitGuard) and not built.armed
    assert not (data_paths.tmp / STALL_FILE_NAME).exists()  # nothing opened until it is armed


def test_trayserve_logs_threads_and_a_stuck_server_thread(
    data_paths: DataPaths, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """SYS-02: exit diagnostics: "Stopping (Quit: yes)", a WARNING for an uvicorn thread that won't end, and the live
    threads as names and daemon flags only."""
    release = threading.Event()

    async def deaf(self: Any, sockets: Any = None) -> None:
        self.started = True
        while not release.is_set():  # ignores `should_exit`
            await asyncio.sleep(0.02)

    monkeypatch.setattr(launcher.uvicorn.Server, "serve", deaf)
    monkeypatch.setattr(launcher, "SERVER_STOP_SECONDS", 0.3)
    running = Running(data_paths)
    try:
        with caplog.at_level("INFO"):
            running.start()
            running.serve.request_quit()
            running.thread.join(timeout=20)
        assert not running.thread.is_alive() and running.error == []
        assert "Stopping (Quit: yes)" in caplog.text
        assert "The server thread didn't end in 0 seconds" in caplog.text
        assert "Threads at exit:" in caplog.text and "uvicorn (daemon=True)" in caplog.text
        assert "MainThread" in caplog.text or "(daemon=False)" in caplog.text
    finally:
        release.set()
    assert wait_for(lambda: not any(t.name == "uvicorn" for t in threading.enumerate()))


def test_stopping_without_a_quit_says_so(
    data_paths: DataPaths, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """SYS-02: "Stopping (Quit: no)" when the server crashed."""

    def broken(self: Any, sockets: Any = None) -> None:
        self.started = True
        time.sleep(0.2)
        raise RuntimeError("uvicorn crashed")

    monkeypatch.setattr(launcher.uvicorn.Server, "serve", broken)
    running = Running(data_paths)
    with caplog.at_level("INFO"):
        running.thread.start()
        running.thread.join(timeout=20)
    assert "Stopping (Quit: no)" in caplog.text


# ---- the guard itself, in a child process ----------------------------------------------------

CHILD = textwrap.dedent(
    """
    import atexit, sys, time
    from pathlib import Path
    sys.path.insert(0, sys.argv[1])
    from shelfsync.tray.exit_guard import ExitGuard

    def stuck():
        ck_live_test = "ck_live_test_do_not_dump_me"  # a value in a local of the stuck frame
        time.sleep(60)

    mode = sys.argv[3]
    if mode != "clean":
        atexit.register(stuck)
    if mode != "control":
        guard = ExitGuard(Path(sys.argv[2]))
        guard.arm(1.0 if mode == "stall" else 30.0)
    print("armed", flush=True)
    """
)


def run_child(tmp_path: Path, mode: str, executable: str | None = None) -> subprocess.Popen[str]:
    script = tmp_path / "child.py"
    script.write_text(CHILD, encoding="utf-8")
    folder = tmp_path / "tmp"
    folder.mkdir(exist_ok=True)
    return subprocess.Popen(
        [executable or sys.executable, "-I", str(script), str(BACKEND), str(folder), mode],
        stdout=subprocess.PIPE,
        text=True,
    )


def test_stalled_exit_is_ended_and_dumped(tmp_path: Path) -> None:
    """UI-TRAY, SYS-02, 06 section 3: a process stuck in an exit callback is ended within seconds with code 1, and the
    file holds every thread's stack but no value."""
    control = run_child(tmp_path, "control")
    assert control.stdout is not None and control.stdout.readline().strip() == "armed"
    time.sleep(3)
    still_alive = control.poll() is None
    control.kill()
    control.wait()
    assert still_alive, "without the guard the child should still be stuck at 3 s"

    child = run_child(tmp_path, "stall")
    assert child.stdout is not None and child.stdout.readline().strip() == "armed"
    started = time.monotonic()
    code = child.wait(timeout=10)
    assert code == 1 and time.monotonic() - started < 3
    dump = (tmp_path / "tmp" / STALL_FILE_NAME).read_text(encoding="utf-8")
    assert "Thread 0x" in dump and "stuck" in dump  # the function name is there ...
    assert "ck_live_test" not in dump  # ... the values of its locals are not


def test_clean_exit_leaves_an_empty_stall_file_and_code_0(tmp_path: Path) -> None:
    """UI-TRAY: nothing cancels the guard; a normal exit just ends first and leaves an empty file."""
    child = run_child(tmp_path, "clean")
    assert child.wait(timeout=10) == 0
    assert (tmp_path / "tmp" / STALL_FILE_NAME).read_bytes() == b""


@pytest.mark.windows
@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_exit_guard_under_pythonw_writes_the_file(tmp_path: Path) -> None:
    """UI-TRAY: `pythonw` has no stderr; the guard writes to its file regardless."""
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.is_file():
        pytest.skip("no pythonw.exe next to this interpreter")
    script = tmp_path / "child.py"
    script.write_text(CHILD, encoding="utf-8")
    (tmp_path / "tmp").mkdir()
    child = subprocess.Popen([str(pythonw), "-I", str(script), str(BACKEND), str(tmp_path / "tmp"), "stall"])
    assert child.wait(timeout=15) == 1
    assert "Thread 0x" in (tmp_path / "tmp" / STALL_FILE_NAME).read_text(encoding="utf-8")


# ---- the next start reports it --------------------------------------------------------------


def _log_text(data_paths: DataPaths) -> str:
    return (data_paths.logs / "shelfsync.log").read_text(encoding="utf-8")


def test_stall_report_is_imported_redacted_at_next_start_then_removed(data_paths: DataPaths) -> None:
    """06 section 3: the dump that sits in tmp\\ is logged once through `redact` (a registered secret that somehow got
    in is masked), and `empty_tmp` removes it."""
    secret = "sk_registered_value_123456"
    assert register_secret(secret)
    data_paths.tmp.mkdir(parents=True)
    stall = data_paths.tmp / STALL_FILE_NAME
    stall.write_text(f"Thread 0x00001234 (most recent call first):\n  File x.py, line 1 in stuck {secret}\n")
    code, *_ = go(RecordingServe())
    assert code == server.EXIT_OK
    text = _log_text(data_paths)
    assert "The last exit stalled and was ended by the safety exit" in text
    assert "Thread 0x00001234" in text
    assert secret not in text
    assert not stall.exists()


def test_an_empty_stall_file_is_not_reported_and_is_removed(data_paths: DataPaths) -> None:
    """UI-TRAY: a clean exit leaves an empty file."""
    data_paths.tmp.mkdir(parents=True)
    stall = data_paths.tmp / STALL_FILE_NAME
    stall.write_bytes(b"")
    go(RecordingServe())
    assert "stalled" not in _log_text(data_paths)
    assert not stall.exists()


def test_the_stall_report_is_capped_at_64_kb(data_paths: DataPaths) -> None:
    """06 section 3: a runaway file can't flood the log."""
    data_paths.tmp.mkdir(parents=True)
    (data_paths.tmp / STALL_FILE_NAME).write_bytes(b"A" * 300_000)
    go(RecordingServe())
    text = _log_text(data_paths)
    assert "A" * server.STALL_REPORT_MAX_BYTES in text
    assert "A" * (server.STALL_REPORT_MAX_BYTES + 1) not in text
