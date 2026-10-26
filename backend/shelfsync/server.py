"""Start-up and the server (SET-06, ERR-06): bind 127.0.0.1 ourselves, hand the open socket to uvicorn."""

import asyncio
import logging
import os
import socket
import sys
from collections.abc import Callable

import uvicorn
from fastapi import FastAPI

from shelfsync import messages
from shelfsync.api.app import create_app
from shelfsync.db.connection import connect
from shelfsync.db.migrate import MigrationError, migrate
from shelfsync.db.settings import get_setting
from shelfsync.logs import configure_logging, remove_logging
from shelfsync.paths import DataPaths, prepare_data_folder, resolve_data_paths, write_runtime_json
from shelfsync.platform.notify import LogNotifier, Notifier

HOST = "127.0.0.1"  # never anything else (NFR-5, 06 section 2)
DEFAULT_PORT = 47615
LAST_PORT = 47624

EXIT_OK = 0
EXIT_PORTS_IN_USE = 1
EXIT_MIGRATION_FAILED = 2

_log = logging.getLogger("shelfsync.server")

Serve = Callable[[FastAPI, socket.socket], None]


def candidate_ports(preferred: int) -> list[int]:
    """The port setting first, then each next one up to 47624.

    A port setting outside 47615-47624 gets no fallback: only that port is tried.
    """
    if DEFAULT_PORT <= preferred <= LAST_PORT:
        return list(range(preferred, LAST_PORT + 1))
    return [preferred]


def bind_first_free(ports: list[int]) -> socket.socket | None:
    """Bind and listen on 127.0.0.1 on the first free port; return that open socket, or None if all are taken.

    The socket stays open and is handed to uvicorn, so no other program can take the port in between.
    """
    for port in ports:
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
            continue
        return sock
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


def run(paths: DataPaths, notifier: Notifier, serve: Serve = serve_with_uvicorn) -> int:
    """Start ShelfSync; return the exit code. `serve` is replaceable for tests."""
    prepare_data_folder(paths)
    connection = connect(paths.database)
    try:
        try:
            migrate(connection)
        except MigrationError as error:
            print(f"ShelfSync can't start: {error}", file=sys.stderr)
            _log.error("start-up stopped: %s", error)
            return EXIT_MIGRATION_FAILED
        preferred = int(get_setting(connection, "port"))
        retention_days = int(get_setting(connection, "log_retention_days"))
    finally:
        connection.close()

    handler = configure_logging(paths.logs, retention_days)
    try:
        ports = candidate_ports(preferred)
        sock = bind_first_free(ports)
        if sock is None:
            message = messages.ERR06_ALL_IN_USE.format(first=ports[0], last=ports[-1])
            _log.error(message)
            notifier.notify(message)
            return EXIT_PORTS_IN_USE
        port = sock.getsockname()[1]
        try:
            write_runtime_json(paths, port, os.getpid())
            if port != preferred:
                first = messages.ERR06_FALLBACK.format(preferred=preferred, port=port)
                notifier.notify(f"{first}\n{messages.ERR06_OLD_ADDRESS}")
            _log.info("ShelfSync listening on %s:%d", HOST, port)
            serve(create_app(), sock)
        finally:
            sock.close()
        return EXIT_OK
    finally:
        remove_logging(handler)


def main() -> int:
    """`python -m shelfsync`: a development entry point (the launcher is M1a.4)."""
    return run(resolve_data_paths(), LogNotifier())
