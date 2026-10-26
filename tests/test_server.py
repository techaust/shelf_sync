"""SET-06 and ERR-06: the port, runtime.json, start-up, and the real server on a handed-over socket."""

import asyncio
import json
import os
import socket
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager

import httpx
import pytest
import uvicorn
from fastapi import FastAPI

from shelfsync import server
from shelfsync.api.app import create_app
from shelfsync.paths import DataPaths
from shelfsync.platform.notify import FakeNotifier

DEFAULT_RANGE = list(range(47615, 47625))


@contextmanager
def held(ports: list[int]) -> Iterator[None]:
    """Hold these loopback ports with listening sockets, as another program would."""
    with ExitStack() as stack:
        for port in ports:
            sock = stack.enter_context(socket.socket())
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                pytest.fail(f"port {port} is already used on this PC, so the test can't hold it")
            sock.listen(1)
        yield


class RecordingServe:
    """Stands in for uvicorn: records the socket it was given."""

    def __init__(self) -> None:
        self.sockname: tuple[str, int] | None = None
        self.app: FastAPI | None = None

    def __call__(self, app: FastAPI, sock: socket.socket) -> None:
        self.app = app
        self.sockname = sock.getsockname()


def start(paths: DataPaths, retry_seconds: float = 0.0) -> tuple[int, FakeNotifier, RecordingServe]:
    notifier = FakeNotifier()
    serve = RecordingServe()
    code = server.run(paths, notifier, serve, retry_seconds)
    return code, notifier, serve


def test_default_port_is_used_when_free(data_paths: DataPaths) -> None:
    code, notifier, serve = start(data_paths)
    assert code == server.EXIT_OK
    assert serve.sockname == ("127.0.0.1", 47615)
    assert notifier.messages == []


def test_fallback_port_when_47615_is_held(data_paths: DataPaths) -> None:
    with held([47615]):
        code, notifier, serve = start(data_paths)
    assert code == server.EXIT_OK
    assert serve.sockname == ("127.0.0.1", 47616)
    assert notifier.messages == [
        "Port 47615 is in use, so ShelfSync started on 47616.\n"
        "Open ShelfSync from the tray icon. The old address now reaches the other program."
    ]
    assert json.loads(data_paths.runtime_json.read_text()) == {
        "port": 47616,
        "pid": os.getpid(),
    }


def test_all_ten_ports_held_sends_message_and_exits_non_zero(data_paths: DataPaths) -> None:
    with held(DEFAULT_RANGE):
        code, notifier, serve = start(data_paths)
    assert code != 0
    assert notifier.messages == [
        "Ports 47615–47624 are all in use. Close the program using them, then start ShelfSync again."
    ]
    assert serve.sockname is None  # the server was never started
    assert not data_paths.runtime_json.exists()


def test_socket_is_bound_to_loopback_never_all_interfaces(data_paths: DataPaths) -> None:
    code, _, serve = start(data_paths)
    assert code == server.EXIT_OK
    assert serve.sockname is not None
    assert serve.sockname[0] == "127.0.0.1"
    assert serve.sockname[0] != "0.0.0.0"
    assert server.HOST == "127.0.0.1"


def test_runtime_json_holds_only_port_and_pid(data_paths: DataPaths) -> None:
    start(data_paths)
    content = json.loads(data_paths.runtime_json.read_text())
    assert set(content) == {"port", "pid"}
    assert content["port"] == 47615


def test_candidate_ports() -> None:
    assert server.candidate_ports(47615) == DEFAULT_RANGE
    assert server.candidate_ports(47620) == [47620, 47621, 47622, 47623, 47624]
    assert server.candidate_ports(5000) == [5000]  # outside the range: no fallback


def test_startup_empties_tmp(data_paths: DataPaths) -> None:
    leftover = data_paths.tmp / "job-1"
    leftover.mkdir(parents=True)
    (leftover / "a.zip").write_bytes(b"x")
    (data_paths.tmp / "stray.txt").write_text("x")
    start(data_paths)
    assert data_paths.tmp.is_dir()
    assert list(data_paths.tmp.iterdir()) == []
    assert data_paths.logs.is_dir()
    assert data_paths.backups.is_dir()


def test_migration_failure_stops_startup_and_is_logged_and_notified(
    data_paths: DataPaths, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def broken(connection: object) -> None:
        raise server.MigrationError("boom")

    monkeypatch.setattr(server, "migrate", broken)
    code, notifier, serve = start(data_paths)
    assert code == server.EXIT_MIGRATION_FAILED
    assert serve.sockname is None
    assert notifier.messages == ["ShelfSync couldn't start: boom"]
    assert "boom" in (data_paths.logs / "shelfsync.log").read_text(encoding="utf-8")
    assert capsys.readouterr().err == ""  # no bare print


def test_any_startup_exception_is_logged_notified_and_has_its_own_exit_code(
    data_paths: DataPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(path: object) -> None:
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(server, "connect", broken)
    code, notifier, serve = start(data_paths)
    assert code == server.EXIT_START_FAILED
    assert code not in (server.EXIT_OK, server.EXIT_PORTS_IN_USE, server.EXIT_MIGRATION_FAILED)
    assert notifier.messages == ["ShelfSync couldn't start. The details are in the log."]
    assert "RuntimeError: disk on fire" in (data_paths.logs / "shelfsync.log").read_text(encoding="utf-8")
    assert serve.sockname is None


def test_preferred_port_is_retried_before_falling_back(data_paths: DataPaths) -> None:
    holder = socket.socket()
    holder.bind(("127.0.0.1", 47615))
    holder.listen(1)
    threading.Timer(0.6, holder.close).start()  # the old process lets go a moment later
    code, notifier, serve = start(data_paths, retry_seconds=3.0)
    assert code == server.EXIT_OK
    assert serve.sockname == ("127.0.0.1", 47615)
    assert notifier.messages == []


def test_port_setting_outside_1024_65535_is_an_error() -> None:
    for bad in (0, 80, 1023, 65536):
        with pytest.raises(ValueError):
            server.candidate_ports(bad)


@pytest.mark.windows
@pytest.mark.skipif(sys.platform != "win32", reason="Windows only: the port's state after a closed connection")
def test_port_can_be_rebound_after_a_connection_closed_by_the_server() -> None:
    first = server.bind_first_free([0])
    assert first is not None
    port = first.getsockname()[1]
    client = socket.create_connection(("127.0.0.1", port), timeout=2)
    connection, _ = first.accept()
    connection.close()  # closed from the server side, which leaves the port in the closing state
    client.close()
    first.close()
    second = server.bind_first_free([port], retry_seconds=server.PREFERRED_PORT_RETRY_SECONDS)
    assert second is not None
    second.close()


def test_uvicorn_config_has_no_access_log_and_no_own_logging(data_paths: DataPaths) -> None:
    config = server.make_uvicorn_config(create_app(), 47615)
    assert config.access_log is False
    assert config.log_config is None
    assert config.host == "127.0.0.1"
    assert config.proxy_headers is False


def test_real_uvicorn_serves_health_on_the_handed_over_socket() -> None:
    sock = server.bind_first_free([0])  # port 0: the OS picks a free one
    assert sock is not None
    port = sock.getsockname()[1]
    uv = uvicorn.Server(server.make_uvicorn_config(create_app(), port))
    thread = threading.Thread(target=lambda: asyncio.run(uv.serve(sockets=[sock])), daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not uv.started and time.monotonic() < deadline:
            time.sleep(0.05)
        assert uv.started
        response = httpx.get(f"http://127.0.0.1:{port}/api/health", timeout=5)
        assert response.json()["app"] == "shelfsync"
    finally:
        uv.should_exit = True
        thread.join(timeout=10)
        sock.close()
