"""The installed entry point, `pythonw -m shelfsync.launcher` (04 section 8, SYS-02, SYS-03).

One process runs the server (uvicorn in a worker thread, on the socket the start-up bound), the tray (pystray's own
thread) and, on the main thread, a wait loop that Ctrl+C can interrupt. Quit stops the tray, then asks uvicorn to
shut down and waits for it; start-up's own clean-up then closes the socket and removes runtime.json, and the process
exits 0.

A second launch (the mutex is taken) opens a new signed-in tab in the running copy and exits; see `second_launch`.
"""

import asyncio
import logging
import threading
from collections.abc import Callable
from typing import Any

import uvicorn
from fastapi import FastAPI

from shelfsync import logs, messages, server
from shelfsync.paths import DataPaths
from shelfsync.platform.autostart import AutostartError, RunKey, apply_start_with_windows
from shelfsync.platform.notify import Notifier, default_notifier
from shelfsync.platform.secrets import SecretStore, default_secret_store
from shelfsync.platform.shell import Shell, ShellError, WindowsShell
from shelfsync.secure.sessions import SessionStore, sign_in_url
from shelfsync.tray.second_launch import second_launch
from shelfsync.tray.state import TrayState
from shelfsync.tray.tray import Tray

_log = logging.getLogger("shelfsync.launcher")

SERVER_START_SECONDS = 15.0
SERVER_STOP_SECONDS = 15.0
_WAIT_STEP_SECONDS = 0.5


class TrayServe:
    """The `serve` callable for the launcher: the server in a thread, the tray, a first tab, then wait for Quit."""

    def __init__(
        self,
        paths: DataPaths,
        notifier: Notifier,
        shell: Shell,
        *,
        state: TrayState | None = None,
        make_tray: Callable[..., Any] = Tray,
        open_first_tab: bool = True,
    ) -> None:
        self._paths = paths
        self._notifier = notifier
        self._shell = shell
        self.state = state or TrayState()
        self._make_tray = make_tray
        self._open_first_tab = open_first_tab
        self._quit = threading.Event()  # the wait loop ends: Quit, or the server ended on its own
        self._quit_requested = threading.Event()  # Quit (and nothing else) was asked for
        self._port = 0
        self._sessions: SessionStore | None = None
        self._before_quit: list[Callable[[], bool]] = []

    def add_quit_guard(self, guard: Callable[[], bool]) -> None:
        """Hook for M5: `guard()` returns False while an upload is running, and Quit then waits. None exist yet."""
        self._before_quit.append(guard)

    # --- the menu's actions -------------------------------------------------------------------------------------

    def open_tab(self) -> None:
        """Open ShelfSync with a fresh single-use ticket. The address is never logged."""
        sessions = self._sessions
        if sessions is None:
            return
        try:
            self._shell.open_url(sign_in_url(self._port, sessions.issue_ticket()))
        except (ShellError, ValueError) as error:
            _log.warning("The tab couldn't be opened (%s)", type(error).__name__)
            self._notifier.notify(messages.LAUNCH_NO_SIGN_IN)

    def view_logs(self) -> None:
        self._shell.open_folder(self._paths.logs)

    def request_quit(self) -> None:
        # M5: wait here for a running upload (see add_quit_guard). Nothing runs yet, so Quit is immediate.
        if all(guard() for guard in self._before_quit):
            self._quit_requested.set()
            self._quit.set()

    # --- serve ---------------------------------------------------------------------------------------------------

    def __call__(self, app: FastAPI, sock: Any) -> None:
        self._port = int(sock.getsockname()[1])
        self._sessions = app.state.sessions
        uv = uvicorn.Server(server.make_uvicorn_config(app, self._port))
        crashed: list[BaseException] = []

        def run_server() -> None:
            try:
                asyncio.run(uv.serve(sockets=[sock]))
            except BaseException as error:  # reported in the main thread, below
                crashed.append(error)
                _log.exception("The server stopped unexpectedly")
            finally:
                self._quit.set()  # whatever the reason, the tray has no use without the server

        thread = threading.Thread(target=run_server, name="uvicorn", daemon=True)
        thread.start()
        deadline = SERVER_START_SECONDS
        while not uv.started and thread.is_alive() and deadline > 0:
            self._quit.wait(0.05)
            deadline -= 0.05
        if not uv.started:
            uv.should_exit = True
            thread.join(timeout=SERVER_STOP_SECONDS)
            raise RuntimeError("The server didn't start")

        tray = self._make_tray(self.state, self.open_tab, self.view_logs, self.request_quit)
        try:
            tray.start()
            if self._open_first_tab:
                self.open_tab()
            while not self._quit.wait(_WAIT_STEP_SECONDS):  # Ctrl+C raises here
                pass
        finally:
            tray.stop()
            uv.should_exit = True
            thread.join(timeout=SERVER_STOP_SECONDS)
        if not self._quit_requested.is_set():
            # The wait loop ended without a Quit, so the server ended on its own: by a crash, or by returning.
            if crashed:
                raise server.ServerStoppedError("The server stopped unexpectedly") from crashed[0]
            raise server.ServerStoppedError("The server stopped without being asked to")


def _append_logging(paths: DataPaths) -> logging.Handler | None:
    """The second launch's log handler, or None. A log it can't open must not stop it from opening the tab."""
    if not paths.logs.is_dir():
        return None
    try:
        return logs.configure_append_logging(paths.logs)
    except OSError:
        return None


def make_on_settings(run_key: RunKey | None = None, installed: bool | None = None) -> server.OnSettings:
    """Applies what the settings decide at start-up: Start with Windows (SYS-04)."""

    def apply(settings: dict[str, Any]) -> None:
        try:
            outcome = apply_start_with_windows(bool(settings["start_with_windows"]), run_key, installed=installed)
            _log.info("Start with Windows: %s", outcome)
        except AutostartError as error:
            _log.warning("Start with Windows couldn't be applied (%s)", error)

    return apply


def main(
    *,
    notifier: Notifier | None = None,
    shell: Shell | None = None,
    secrets: SecretStore | None = None,
) -> int:
    """`python -m shelfsync.launcher`."""
    logs.install_output_guards()
    toasts = notifier if notifier is not None else default_notifier()
    opener = shell if shell is not None else WindowsShell()
    logs.set_write_failure_notice(lambda: toasts.notify(messages.LOG_WRITE_FAILED))

    def make_serve(paths: DataPaths) -> server.Serve:
        return TrayServe(paths, toasts, opener)

    def second(paths: DataPaths) -> int:
        store = secrets if secrets is not None else default_secret_store()
        # A handler that never rotates or prunes: this short-lived process must not rename the running copy's log
        # file or delete its older files (it doesn't know the retention setting either).
        handler = _append_logging(paths)
        try:
            return second_launch(paths, toasts, opener, store)
        finally:
            if handler is not None:
                logs.remove_logging(handler)

    return server.run_application(make_serve, toasts, second, secrets=secrets, on_settings=make_on_settings())
