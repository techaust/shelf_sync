"""Shared fixtures. The no-outbound fixture is on for every test (NFR-5)."""

import ipaddress
import socket
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from shelfsync.paths import DATA_DIR_ENV, DataPaths


class OutboundNetworkBlocked(AssertionError):
    """A test reached for a non-loopback address. Not an OSError on purpose: code under test can't swallow it."""


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
def no_outbound_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make any connection or name lookup for a non-loopback address fail the test."""
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_getaddrinfo = socket.getaddrinfo

    def guard(address: Any) -> None:
        if isinstance(address, tuple) and not _is_loopback(address[0]):
            raise OutboundNetworkBlocked(f"outbound connection to {address[0]!r} blocked (NFR-5)")

    def connect(self: socket.socket, address: Any) -> None:
        guard(address)
        real_connect(self, address)

    def connect_ex(self: socket.socket, address: Any) -> int:
        guard(address)
        return real_connect_ex(self, address)

    def getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
        if not _is_loopback(host):
            raise OutboundNetworkBlocked(f"name lookup for {host!r} blocked (NFR-5)")
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)


@pytest.fixture
def data_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[DataPaths]:
    """An empty data folder, selected through SHELFSYNC_DATA_DIR."""
    root = tmp_path / "ShelfSync"
    monkeypatch.setenv(DATA_DIR_ENV, str(root))
    yield DataPaths(root)
