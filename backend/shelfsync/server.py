"""Start-up and the server (SET-06, ERR-06): bind 127.0.0.1 ourselves, hand the open socket to uvicorn."""

import asyncio
import logging
import os
import socket
import time
from collections.abc import Callable
from logging.handlers import TimedRotatingFileHandler
from typing import Any

import uvicorn
from fastapi import FastAPI

from shelfsync import messages
from shelfsync.api.app import create_app
from shelfsync.api.app_settings import AppSettingsService
from shelfsync.db.backup import migrate_with_backup
from shelfsync.db.connection import connect
from shelfsync.db.migrate import MigrationError
from shelfsync.db.settings import DEFAULTS, get_all_settings
from shelfsync.logs import (
    configure_logging,
    install_output_guards,
    remove_logging,
    report_ctrl_c,
    set_log_retention,
)
from shelfsync.paths import (
    DataPaths,
    UiMissingError,
    create_data_folders,
    empty_tmp,
    resolve_data_paths,
    ui_dir,
    write_runtime_json,
)
from shelfsync.platform.notify import LogNotifier, Notifier
from shelfsync.platform.secrets import SecretStore, default_secret_store
from shelfsync.ports import DEFAULT_PORT, LAST_PORT
from shelfsync.secure.token import InstallToken
from shelfsync.tray.exit_guard import STALL_FILE_NAME, remove_unsafe_entry
from shelfsync.tray.instance import InstanceLock, default_instance_lock
from shelfsync.update.service import build_update_service

HOST = "127.0.0.1"  # never anything else (NFR-5, 06 section 2)

# A restarted ShelfSync may find its own old port still closing (Windows keeps a closed connection's port for a
# while, and we ask for exclusive use). Retry the preferred port this long before falling back to the next one.
PREFERRED_PORT_RETRY_SECONDS = 3.0
_RETRY_STEP_SECONDS = 0.25

EXIT_OK = 0
EXIT_PORTS_IN_USE = 1
EXIT_MIGRATION_FAILED = 2
EXIT_START_FAILED = 3  # any other failure before the server was running
EXIT_SERVER_STOPPED = 7  # the server was running and then stopped on its own

_log = logging.getLogger("shelfsync.server")


class ServerStoppedError(Exception):
    """The server was running and stopped without being asked to (not a failure to start)."""


Serve = Callable[[FastAPI, socket.socket], None]
MakeServe = Callable[[DataPaths], Serve]
OnSettings = Callable[[dict[str, Any]], None]
SecondLaunch = Callable[[DataPaths], int]


def candidate_ports(preferred: int) -> list[int]:
    """The port setting first, then each next one up to 47624.

    The setting stays inside 47615-47624 (the "all in use" notice names that range), so a stored value outside it is
    an error, not a port to try.
    """
    if not DEFAULT_PORT <= preferred <= LAST_PORT:
        raise ValueError(f"The port setting {preferred} is outside {DEFAULT_PORT}-{LAST_PORT}.")
    return list(range(preferred, LAST_PORT + 1))


def _try_bind(port: int) -> socket.socket | None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):  # Windows: nobody else may share the port
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:  # POSIX: lets us rebind after a restart without allowing two listeners
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((HOST, port))
        sock.listen(128)
    except OSError:
        sock.close()
        return None
    return sock


def bind_first_free(ports: list[int], retry_seconds: float = 0.0) -> socket.socket | None:
    """Bind and listen on 127.0.0.1 on the first free port; return that open socket, or None if all are taken.

    The first port is retried for `retry_seconds` before moving on. The socket stays open and is handed to uvicorn,
    so no other program can take the port in between.
    """
    deadline = time.monotonic() + retry_seconds
    for index, port in enumerate(ports):
        while True:
            sock = _try_bind(port)
            if sock is not None:
                return sock
            if index > 0 or time.monotonic() >= deadline:
                break
            time.sleep(_RETRY_STEP_SECONDS)
    return None


def make_uvicorn_config(app: FastAPI, port: int) -> uvicorn.Config:
    """uvicorn settings: no log_config (our handler on the root logger gets uvicorn's records), no access log
    (it would write the request line with its query string), no proxy headers, no Server header."""
    return uvicorn.Config(
        app,
        host=HOST,
        port=port,
        log_config=None,
        access_log=False,
        proxy_headers=False,
        server_header=False,
    )


def serve_with_uvicorn(app: FastAPI, sock: socket.socket) -> None:
    """Run uvicorn on the already-open socket until it is stopped."""
    port = sock.getsockname()[1]
    server = uvicorn.Server(make_uvicorn_config(app, port))
    asyncio.run(server.serve(sockets=[sock]))


STALL_REPORT_MAX_BYTES = 64 * 1024


def _report_stalled_exit(paths: DataPaths) -> None:
    """The last exit stalled and the safety exit ended it: log what it dumped, through the redacting handler (06
    section 3). `empty_tmp` removes the file right after."""
    path = paths.tmp / STALL_FILE_NAME
    if remove_unsafe_entry(path):  # a link or a file with several names: never read, never followed
        _log.warning("A link or shared file was found in place of the stall report; it was removed unread")
        return
    try:
        with path.open("rb") as stall_file:
            content = stall_file.read(STALL_REPORT_MAX_BYTES)
    except OSError:  # no file (the usual case) or an unreadable one: nothing to report
        return
    if content.strip():
        _log.warning(
            "The last exit stalled and was ended by the safety exit:\n%s", content.decode("utf-8", errors="replace")
        )


def _start(
    paths: DataPaths,
    notifier: Notifier,
    serve: Serve,
    retry_seconds: float,
    handler: TimedRotatingFileHandler,
    secrets: SecretStore,
    on_settings: OnSettings | None = None,
) -> int:
    # Only the one running copy gets here (the instance lock is held), so a runtime.json that exists is a leftover
    # of a copy that didn't exit cleanly: it isn't ours and must not point a second launch at a dead port.
    ui = ui_dir()  # an installed copy without its UI stops here, before the database or any port is touched
    paths.runtime_json.unlink(missing_ok=True)
    _report_stalled_exit(paths)
    empty_tmp(paths)
    connection = connect(paths.database)
    try:
        migrate_with_backup(connection, paths)  # SYS-07: a backup first when migrations are pending
        settings = get_all_settings(connection)
    finally:
        connection.close()
    preferred = settings["port"]
    set_log_retention(handler, int(settings["log_retention_days"]))  # LOG-01: also prunes files past the retention
    if on_settings is not None:
        on_settings(settings)

    # The install token is loaded (made on first run) before any port is bound, once, and handed to the app: if the
    # secret store fails, the start-up fails here and holds no port.
    install_token = InstallToken(secrets)

    ports = candidate_ports(preferred)
    sock = bind_first_free(ports, retry_seconds)
    if sock is None:
        _log.error(messages.ERR06_ALL_IN_USE)
        notifier.notify(messages.ERR06_ALL_IN_USE)
        return EXIT_PORTS_IN_USE
    try:
        port = sock.getsockname()[1]
        write_runtime_json(paths, port, os.getpid())
        if port != preferred:
            first = messages.ERR06_FALLBACK.format(preferred=preferred, port=port)
            notifier.notify(f"{first}\n{messages.ERR06_OLD_ADDRESS}")
        _log.info("ShelfSync listening on %s:%d", HOST, port)
        app = create_app(
            port,
            install_token,
            ui_dir=ui,
            updates=build_update_service(paths, secrets),
            app_settings=AppSettingsService(lambda: connect(paths.database), handler),
        )
        serve(app, sock)
    finally:
        sock.close()
        paths.runtime_json.unlink(missing_ok=True)  # clean exit: nothing left to point a second launch at
    return EXIT_OK


def run(
    paths: DataPaths,
    notifier: Notifier,
    serve: Serve = serve_with_uvicorn,
    retry_seconds: float = PREFERRED_PORT_RETRY_SECONDS,
    secrets: SecretStore | None = None,
    on_settings: OnSettings | None = None,
) -> int:
    """Start ShelfSync; return the exit code. `serve` and `secrets` are replaceable for tests (`secrets` defaults to
    Credential Manager); `on_settings` is called with the settings once they are read (the launcher applies Start
    with Windows there).

    The caller holds the single-instance lock (`run_application`). Logging is set up first (with the default
    retention, adjusted once the settings are read), so every start-up failure is logged. A failure is also sent to
    the notifier in plain words and gets its own exit code.
    """
    handler: TimedRotatingFileHandler | None = None
    try:
        try:
            create_data_folders(paths)
            handler = configure_logging(paths.logs, int(DEFAULTS["log_retention_days"]))
        except OSError:
            # No log exists yet, so the notice must not point to one.
            _log.exception("start-up stopped: the data folder or the log file couldn't be used")
            notifier.notify(messages.START_FAILED_DATA_FOLDER)
            return EXIT_START_FAILED
        store = secrets if secrets is not None else default_secret_store()
        return _start(paths, notifier, serve, retry_seconds, handler, store, on_settings)
    except ServerStoppedError:
        _log.exception("the server stopped unexpectedly")
        notifier.notify(messages.SERVER_STOPPED)
        return EXIT_SERVER_STOPPED
    except UiMissingError:
        _log.exception("start-up stopped: the installed copy has no UI")
        notifier.notify(messages.START_FAILED_UI_MISSING)
        return EXIT_START_FAILED
    except MigrationError:
        _log.exception("start-up stopped: the database couldn't be migrated")
        notifier.notify(messages.START_FAILED_MIGRATION)
        return EXIT_MIGRATION_FAILED
    except Exception:
        _log.exception("start-up failed")
        notifier.notify(messages.START_FAILED)
        return EXIT_START_FAILED
    finally:
        if handler is not None:
            remove_logging(handler)


def run_application(
    make_serve: MakeServe,
    notifier: Notifier,
    on_second_launch: SecondLaunch,
    *,
    lock: InstanceLock | None = None,
    secrets: SecretStore | None = None,
    on_settings: OnSettings | None = None,
    retry_seconds: float = PREFERRED_PORT_RETRY_SECONDS,
) -> int:
    """The whole start: find the data folder, take the single-instance lock (before anything touches the tmp folder,
    the database or the install token), then `run` with the `serve` that `make_serve(paths)` builds for the data
    folder found here (so nothing resolves it a second time). If another copy holds the lock this is a second launch:
    `on_second_launch(paths)` decides what that does and its code is returned. Ctrl+C is a normal stop (exit 0).
    """
    try:
        paths = resolve_data_paths()
    except Exception:
        _log.exception("start-up failed: the data folder is unknown")
        notifier.notify(messages.START_FAILED_DATA_FOLDER)
        return EXIT_START_FAILED
    try:
        instance = lock if lock is not None else default_instance_lock(paths)
        try:
            first_copy = instance.acquire()
        except OSError:
            # The data folder or the lock file in it can't be made or opened: say so, not "couldn't start".
            _log.exception("start-up failed: the instance lock in the data folder couldn't be taken")
            notifier.notify(messages.START_FAILED_DATA_FOLDER)
            return EXIT_START_FAILED
        if not first_copy:
            return on_second_launch(paths)
        try:
            return run(paths, notifier, make_serve(paths), retry_seconds, secrets, on_settings)
        finally:
            instance.release()
    except KeyboardInterrupt:
        report_ctrl_c()
        return EXIT_OK
    except Exception:
        _log.exception("start-up failed")
        notifier.notify(messages.START_FAILED)
        return EXIT_START_FAILED


def _already_running(paths: DataPaths) -> int:
    """The developer entry on a second start: say so and stop. (The launcher opens a signed-in tab instead.)"""
    _log.warning("ShelfSync is already running. Open it from the tray icon.")
    return EXIT_OK


def main() -> int:
    """`python -m shelfsync`: the developer entry (no tray; the installed entry is `python -m shelfsync.launcher`)."""
    install_output_guards()  # first: from here nothing leaves the process unredacted, even before logging is set up
    return run_application(lambda paths: serve_with_uvicorn, LogNotifier(), _already_running)
