"""SYS-03, SET-06, LOG-01, NFR-5: the install token at start-up, and the app built for the bound port."""

import logging
import socket

import pytest
from fastapi.testclient import TestClient

from shelfsync import messages, server
from shelfsync.paths import DataPaths
from shelfsync.platform.notify import FakeNotifier
from shelfsync.platform.secrets import MemorySecretStore, SecretStoreError
from shelfsync.secure.token import INSTALL_TOKEN_NAME
from tests.support import PORT, make_harness
from tests.test_server import RecordingServe, start


def run_with(paths: DataPaths, store: MemorySecretStore) -> tuple[int, FakeNotifier, RecordingServe]:
    notifier = FakeNotifier()
    serve = RecordingServe()
    return server.run(paths, notifier, serve, 0.0, store), notifier, serve


def test_start_up_creates_the_install_token_once(data_paths: DataPaths) -> None:
    """SYS-03: made on the first run; the second run finds and keeps the same one."""
    store = MemorySecretStore()
    code, _, _ = run_with(data_paths, store)
    assert code == server.EXIT_OK
    first = store.get(INSTALL_TOKEN_NAME)
    assert first
    code, _, _ = run_with(data_paths, store)
    assert code == server.EXIT_OK
    assert store.get(INSTALL_TOKEN_NAME) == first


def test_runtime_json_and_the_log_never_hold_the_token(data_paths: DataPaths) -> None:
    """SYS-03, LOG-01: runtime.json has the port and PID only; the log doesn't have the token either."""
    store = MemorySecretStore()
    _, _, serve = run_with(data_paths, store)
    token = store.get(INSTALL_TOKEN_NAME)
    assert token
    assert serve.runtime_json is not None
    assert token not in serve.runtime_json
    assert token not in (data_paths.logs / "shelfsync.log").read_text(encoding="utf-8")


def test_the_app_is_built_for_the_port_that_was_bound(data_paths: DataPaths) -> None:
    """NFR-5: start-up hands the bound port to create_app, so the Host check expects exactly that port."""
    _, _, serve = start(data_paths)
    assert serve.app is not None and serve.sockname is not None
    port = serve.sockname[1]
    assert TestClient(serve.app, base_url=f"http://127.0.0.1:{port}").get("/api/health").status_code == 200
    assert TestClient(serve.app, base_url=f"http://127.0.0.1:{port + 1}").get("/api/health").status_code == 403
    assert TestClient(serve.app).get("/api/health").status_code == 403  # the default host, testserver


class _BrokenStore:
    """A store that fails, with a message that happens to hold a key-shaped value."""

    leaked = "c" + "k_" + "0123456789abcdef" * 3

    def get(self, name: str) -> str | None:
        raise SecretStoreError(f"read failed near {self.leaked}")

    def set(self, name: str, value: str) -> None:
        raise SecretStoreError("write failed")

    def delete(self, name: str) -> None:
        raise SecretStoreError("delete failed")


def test_a_store_that_fails_stops_start_up_before_any_port_is_bound(
    data_paths: DataPaths, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """SYS-03: exit 3 with the fixed notice, the server never started, no port held; no secret in the log."""
    bound: list[list[int]] = []
    real_bind = server.bind_first_free

    def spy(ports: list[int], retry_seconds: float = 0.0) -> socket.socket | None:
        bound.append(ports)
        return real_bind(ports, retry_seconds)

    monkeypatch.setattr(server, "bind_first_free", spy)
    notifier = FakeNotifier()
    serve = RecordingServe()
    with caplog.at_level(logging.ERROR):
        code = server.run(data_paths, notifier, serve, 0.0, _BrokenStore())
    assert code == server.EXIT_START_FAILED == 3
    assert notifier.messages == [messages.START_FAILED]
    assert bound == []  # bind_first_free was never reached
    assert serve.sockname is None
    assert not data_paths.runtime_json.exists()
    log_text = (data_paths.logs / "shelfsync.log").read_text(encoding="utf-8")
    assert "start-up failed" in log_text
    assert _BrokenStore.leaked not in log_text  # redacted by shape


def test_a_store_that_fails_to_write_also_stops_start_up(data_paths: DataPaths) -> None:
    """SYS-03: the first run can't save the new token: stop, don't run with a token nobody can read back."""

    class WriteFails(MemorySecretStore):
        def set(self, name: str, value: str) -> None:
            raise SecretStoreError("write failed")

    notifier = FakeNotifier()
    serve = RecordingServe()
    code = server.run(data_paths, notifier, serve, 0.0, WriteFails())
    assert code == server.EXIT_START_FAILED
    assert notifier.messages == [messages.START_FAILED]
    assert serve.sockname is None


def test_the_uvicorn_config_host_is_loopback() -> None:
    """NFR-5: uvicorn is configured for 127.0.0.1 only (the bound socket is checked by
    test_server.py::test_socket_is_bound_to_loopback_never_all_interfaces)."""
    config = server.make_uvicorn_config(make_harness().app, PORT)
    assert config.host == "127.0.0.1"
    assert server.HOST == "127.0.0.1"
