"""Start-up and the server (SET-06, ERR-06): bind 127.0.0.1 ourselves, hand the open socket to uvicorn."""

import asyncio
import logging
import os
import socket
import time
from collections.abc import Callable
from logging.handlers import TimedRotatingFileHandler

import uvicorn
from fastapi import FastAPI

from shelfsync import messages
from shelfsync.api.app import create_app
from shelfsync.db.connection import connect
from shelfsync.db.migrate import MigrationError, migrate
from shelfsync.db.settings import DEFAULTS, get_setting
from shelfsync.logs import configure_logging, remove_logging
from shelfsync.paths import DataPaths, create_data_folders, empty_tmp, resolve_data_paths, write_runtime_json
from shelfsync.platform.notify import LogNotifier, Notifier
from shelfsync.ports import DEFAULT_PORT, LAST_PORT, MAX_PORT, MIN_PORT

HOST = "127.0.0.1"  # never anything else (NFR-5, 06 section 2)

# A restarted ShelfSync may find its own old port still closing (Windows keeps a closed connection's port for a
# while, and we ask for exclusive use). Retry the preferred port this long before falling back to the next one.
PREFERRED_PORT_RETRY_SECONDS = 3.0
_RETRY_STEP_SECONDS = 0.25

EXIT_OK = 0
EXIT_PORTS_IN_USE = 1
EXIT_MIGRATION_FAILED = 2
EXIT_START_FAILED = 3  # any other failure before the server was running

_log = logging.getLogger("shelfsync.server")

Serve = Callable[[FastAPI, socket.socket], None]


def candidate_ports(preferred: int) -> list[int]:
    """The port setting first, then each next one up to 47624.

    A port setting outside 47615-47624 gets no fallback: only that port is tried. A port outside 1024-65535 is an
    error.
    """
    if not MIN_PORT <= preferred <= MAX_PORT:
        raise ValueError(f"The port setting {preferred} is outside {MIN_PORT}-{MAX_PORT}.")
    if DEFAULT_PORT <= preferred <= LAST_PORT:
        return list(range(preferred, LAST_PORT + 1))
    return [preferred]


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


def _start(
    paths: DataPaths,
    notifier: Notifier,
    serve: Serve,
    retry_seconds: float,
    handler: TimedRotatingFileHandler,
) -> int:
    empty_tmp(paths)
    connection = connect(paths.database)
    try:
        migrate(connection)
        preferred = get_setting(connection, "port")
        handler.backupCount = int(get_setting(connection, "log_retention_days"))
    finally:
        connection.close()

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
        serve(create_app(), sock)
    finally:
        sock.close()
    return EXIT_OK


def run(
    paths: DataPaths,
    notifier: Notifier,
    serve: Serve = serve_with_uvicorn,
    retry_seconds: float = PREFERRED_PORT_RETRY_SECONDS,
) -> int:
    """Start ShelfSync; return the exit code. `serve` is replaceable for tests.

    Logging is set up first (with the default retention, adjusted once the settings are read), so every start-up
    failure is logged. A failure is also sent to the notifier in plain words and gets its own exit code.
    """
    handler: TimedRotatingFileHandler | None = None
    try:
        create_data_folders(paths)
        handler = configure_logging(paths.logs, int(DEFAULTS["log_retention_days"]))
        return _start(paths, notifier, serve, retry_seconds, handler)
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


def main() -> int:
    """`python -m shelfsync`: a development entry point (the launcher is M1a.4)."""
    return run(resolve_data_paths(), LogNotifier())
