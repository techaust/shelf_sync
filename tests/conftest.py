"""Shared fixtures. The no-outbound fixture is on for every test (NFR-5)."""

import ipaddress
import socket
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from shelfsync import server
from shelfsync.paths import DATA_DIR_ENV, DataPaths
from shelfsync.platform.secrets import MemorySecretStore
from shelfsync.secure.redact import clear_secrets


class OutboundNetworkBlocked(AssertionError):
    """A test reached for a non-loopback address. Not an OSError, so code that catches network errors doesn't catch it;
    but code that catches every exception can (botocore turns anything raised while sending into `HTTPClientError`).
    So each blocked attempt is also recorded, and the fixture fails the test at its end if the record isn't empty."""


def _is_loopback(host: Any) -> bool:
    if host in ("localhost", "", None):
        return True
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    try:
        return ipaddress.ip_address(str(host).split("%")[0]).is_loopback
    except ValueError:
        return False  # a host name that isn't "localhost": resolving it would be an outbound lookup


@pytest.fixture(autouse=True)
def no_outbound_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """Make any connection or name lookup for a non-loopback address fail the test, even if the code under test
    swallowed the error: the yielded record must be empty at the end. A test that triggers a blocked attempt on purpose
    requests this fixture and clears the record."""
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_getaddrinfo = socket.getaddrinfo
    blocked: list[str] = []

    def guard(address: Any) -> None:
        if isinstance(address, tuple) and not _is_loopback(address[0]):
            blocked.append(f"connect {address[0]!r}")
            raise OutboundNetworkBlocked(f"outbound connection to {address[0]!r} blocked (NFR-5)")

    def connect(self: socket.socket, address: Any) -> None:
        guard(address)
        real_connect(self, address)

    def connect_ex(self: socket.socket, address: Any) -> int:
        guard(address)
        return real_connect_ex(self, address)

    def getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
        if not _is_loopback(host):
            blocked.append(f"lookup {host!r}")
            raise OutboundNetworkBlocked(f"name lookup for {host!r} blocked (NFR-5)")
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    yield blocked
    assert blocked == [], f"outbound attempts were blocked (NFR-5), even if the code under test hid them: {blocked}"


@pytest.fixture(autouse=True)
def no_real_credential_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    """`server.run()` without a store would use Windows Credential Manager. No test may touch it, except the ones
    marked `windows`, which build their own throwaway `KeyringSecretStore`."""
    monkeypatch.setattr(server, "default_secret_store", MemorySecretStore)


@pytest.fixture(autouse=True)
def fresh_redaction_registry() -> Iterator[None]:
    """Registered secrets are process-wide; each test starts and ends with none."""
    clear_secrets()
    yield
    clear_secrets()


@pytest.fixture
def data_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[DataPaths]:
    """An empty data folder, selected through SHELFSYNC_DATA_DIR."""
    root = tmp_path / "ShelfSync"
    monkeypatch.setenv(DATA_DIR_ENV, str(root))
    yield DataPaths(root)
