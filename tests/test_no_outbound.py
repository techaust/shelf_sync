"""NFR-5: the suite can't reach the internet."""

import socket

import pytest

from tests.conftest import OutboundNetworkBlocked


def test_connection_to_example_com_fails_the_test() -> None:
    with pytest.raises(OutboundNetworkBlocked):
        socket.create_connection(("example.com", 80), timeout=1)


def test_connect_to_a_public_ip_fails_the_test() -> None:
    with socket.socket() as sock, pytest.raises(OutboundNetworkBlocked):
        sock.connect(("93.184.216.34", 80))


def test_loopback_is_allowed() -> None:
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        with socket.create_connection(server.getsockname(), timeout=1):
            pass
