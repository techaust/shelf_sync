"""The installed entry point, `pythonw -m shelfsync.launcher` (04 section 8, SYS-02, SYS-03).

One process runs the server (uvicorn in a worker thread, on the socket the start-up bound), the tray (pystray's own
thread) and, on the main thread, a wait loop that Ctrl+C can interrupt. Quit stops the tray, then asks uvicorn to
shut down and waits for it; start-up's own clean-up then closes the socket and removes runtime.json, and the process
exits 0.

Safety exit: once Quit (or a crash, or Ctrl+C) starts the shut-down, an `ExitGuard` is armed for 45 s (more than the
worst bounded path, about 34 s) and, at the end of `TrayServe.__call__` (after the server join), re-armed for 10 s, so
the 10 s cover `run()`'s clean-up, the release of the single-instance lock and the interpreter's finalization. If the
process still hasn't ended by then, faulthandler writes every thread's stack to `tmp\\shutdown-stall.txt` and ends it
with exit code 1; the next start logs that file. Residual: a relaunch within those 10 s may log "Couldn't remove
shutdown-stall.txt" (the old process still holds the file). Only `shelfsync.launcher`'s `__main__` passes a factory
that builds a real guard (from the data folder `run_application` resolved); a guard that can't be armed is logged and
the shut-down goes on without it.

A second launch (the mutex is taken) opens a new signed-in tab in the running copy and exits (see `second_launch`);
started with `--background` it exits quietly instead.
"""

import argparse
import asyncio
import logging
import threading
from collections.abc import Callable, Sequence
from typing import Any

import uvicorn
from fastapi import FastAPI

from shelfsync import logs, messages, server
from shelfsync.paths import DataPaths
from shelfsync.platform.autostart import BACKGROUND_FLAG, RunKey, apply_start_with_windows_safely
from shelfsync.platform.notify import Notifier, default_notifier
from shelfsync.platform.secrets import SecretStore, default_secret_store
from shelfsync.platform.shell import Shell, ShellError, WindowsShell
from shelfsync.secure.sessions import SessionStore, sign_in_url
from shelfsync.tray.exit_guard import ExitGuard
from shelfsync.tray.second_launch import second_launch
from shelfsync.tray.state import TrayState
from shelfsync.tray.tray import Tray

_log = logging.getLogger("shelfsync.launcher")

SERVER_START_SECONDS = 15.0
SERVER_STOP_SECONDS = 15.0
STAGE1_SECONDS = 45.0  # the exit guard, armed when the shut-down starts
# Re-armed at the end of `__call__`: run()'s clean-up (a crash's toast, not timed cold), the lock release, finalization.
STAGE2_SECONDS = 10.0
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
        exit_guard: ExitGuard | None = None,
    ) -> None:
        self._exit_guard = exit_guard
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
        """Hook for M5: `guard()` returns False while an upload is running, and Quit then waits. None exist yet.
        A guard may run on the tray's thread (the menu's Quit) or on a server thread (the updater calls
        `app.state.request_quit` from a request handler), so it must be thread-safe and must never block on the
        server's event loop or on the tray's."""
        self._before_quit.append(guard)

    # --- the menu's actions -------------------------------------------------------------------------------------

    def open_tab(self) -> None:
        """Open ShelfSync with a fresh single-use ticket. The address is never logged."""
        sessions = self._sessions
        if sessions is None or self._quit.is_set():  # an Open that was queued before Quit must not open a tab now
            return
        try:
            self._shell.open_url(sign_in_url(self._port, sessions.issue_ticket()))
        except (ShellError, ValueError) as error:
            _log.warning("The tab couldn't be opened (%s)", type(error).__name__)
            self._notifier.notify(messages.LAUNCH_NO_SIGN_IN)

    def view_logs(self) -> None:
        self._shell.open_folder(self._paths.logs)

    def request_quit(self) -> bool:
        """Quit, exactly as the tray menu's Quit does. True if the quit started; False if a quit guard refused
        (the menu ignores the answer; the updater, through `app.state.request_quit`, reads it)."""
        # M5: wait here for a running upload (see add_quit_guard). Nothing runs yet, so Quit is immediate.
        if all(guard() for guard in self._before_quit):
            self._quit_requested.set()
            self._quit.set()
            return True
        return False

    # --- serve ---------------------------------------------------------------------------------------------------

    def __call__(self, app: FastAPI, sock: Any) -> None:
        self._port = int(sock.getsockname()[1])
        self._sessions = app.state.sessions
        # For the updater (m1b.2): the one way the app asks the tray to quit. The developer entry never sets it.
        app.state.request_quit = self.request_quit
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
            raise RuntimeError("The server didn't start") from (crashed[0] if crashed else None)

        tray = self._make_tray(self.state, self.open_tab, self.view_logs, self.request_quit)
        try:
            tray.start()
            if self._open_first_tab:
                self.open_tab()
            while not self._quit.wait(_WAIT_STEP_SECONDS):  # Ctrl+C raises here
                pass
        finally:
            _log.info("Stopping (Quit: %s)", "yes" if self._quit_requested.is_set() else "no")
            if self._exit_guard is not None:
                try:
                    self._exit_guard.arm(STAGE1_SECONDS)
                except Exception as error:  # no safety exit is better than no shut-down
                    _log.warning("The safety exit couldn't be armed (%s)", type(error).__name__)
            tray.stop()
            uv.should_exit = True
            thread.join(timeout=SERVER_STOP_SECONDS)
            if thread.is_alive():
                _log.warning("The server thread didn't end in %.0f seconds", SERVER_STOP_SECONDS)
            _log.info("Threads at exit: %s", ", ".join(f"{t.name} (daemon={t.daemon})" for t in threading.enumerate()))
            if self._exit_guard is not None and self._exit_guard.armed:
                # Stage 2: what is left (run()'s clean-up, the lock release, finalization) gets 10 s.
                self._exit_guard.rearm(STAGE2_SECONDS)
        # A crash is reported first, even if Quit was asked for meanwhile: it is the more useful fact.
        if crashed:
            raise server.ServerStoppedError("The server stopped unexpectedly") from crashed[0]
        if not self._quit_requested.is_set():
            # The wait loop ended without a Quit and without a crash: the server returned on its own.
            raise server.ServerStoppedError("The server stopped without being asked to")


def _append_logging(paths: DataPaths) -> logging.Handler | None:
    """The second launch's log handler, or None. A log it can't open must not stop it from opening the tab."""
    if not paths.logs.is_dir():
        return None
    # Defensive: with delay=True the handler's constructor doesn't touch the disk, so this is not expected to fail.
    try:
        return logs.configure_append_logging(paths.logs)
    except OSError:
        return None


def make_on_settings(run_key: RunKey | None = None, installed: bool | None = None) -> server.OnSettings:
    """Applies what the settings decide at start-up: Start with Windows (SYS-04)."""

    def apply(settings: dict[str, Any]) -> None:
        apply_start_with_windows_safely(bool(settings["start_with_windows"]), run_key, installed=installed)

    return apply


def parse_arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    """`--background` is the only argument. An unknown one is an error (argparse exits with 2), never ignored."""
    parser = argparse.ArgumentParser(prog="shelfsync.launcher", allow_abbrev=False)
    parser.add_argument(
        BACKGROUND_FLAG,
        action="store_true",
        help="start in the tray without opening a browser tab (the Start with Windows value uses it)",
    )
    return parser.parse_args(argv)


def main(
    argv: Sequence[str] | None = None,
    *,
    notifier: Notifier | None = None,
    shell: Shell | None = None,
    secrets: SecretStore | None = None,
    make_exit_guard: Callable[[DataPaths], ExitGuard | None] | None = None,
) -> int:
    """`python -m shelfsync.launcher [--background]`. `argv` defaults to `sys.argv[1:]`. `make_exit_guard(paths)`
    builds the safety exit from the data folder that `run_application` resolved; it is None in tests: a real armed
    guard would end pytest. With `--background` the first copy opens no tab and a second launch does nothing;
    without it a second launch opens a signed-in tab."""
    arguments = parse_arguments(argv)
    logs.install_output_guards()
    toasts = notifier if notifier is not None else default_notifier()
    opener = shell if shell is not None else WindowsShell()
    logs.set_write_failure_notice(lambda: toasts.notify(messages.LOG_WRITE_FAILED))

    def make_serve(paths: DataPaths) -> server.Serve:
        guard = make_exit_guard(paths) if make_exit_guard is not None else None
        return TrayServe(paths, toasts, opener, open_first_tab=not arguments.background, exit_guard=guard)

    def second(paths: DataPaths) -> int:
        if arguments.background:
            # Signing in to Windows while ShelfSync already runs (a second logon session, say): nothing to show, so
            # no tab and no sound. Shortcuts have no flag and still open a tab.
            return 0
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
