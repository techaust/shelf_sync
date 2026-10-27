"""Helpers for the API tests: an app on a known port with an in-memory secret store and a controllable clock."""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from shelfsync.api.app import create_app
from shelfsync.platform.secrets import MemorySecretStore
from shelfsync.secure.token import INSTALL_TOKEN_NAME, InstallToken

PORT = 47615
HOST = f"127.0.0.1:{PORT}"
ORIGIN = f"http://{HOST}"
WRITE_HEADERS = {"Origin": ORIGIN, "X-ShelfSync": "1"}


class FakeClock:
    """A clock the test moves by hand."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@dataclass
class Harness:
    app: FastAPI
    store: MemorySecretStore
    clock: FakeClock
    port: int = PORT

    @property
    def token(self) -> str:
        value = self.store.get(INSTALL_TOKEN_NAME)
        assert value is not None
        return value

    def client(self, host: str | None = None, raise_server_exceptions: bool = True) -> TestClient:
        """A client that talks to the app as `host` (default 127.0.0.1:<port>). Not signed in."""
        base_url = f"http://{host or f'127.0.0.1:{self.port}'}"
        return TestClient(self.app, base_url=base_url, raise_server_exceptions=raise_server_exceptions)

    def ticket(self, client: TestClient | None = None) -> str:
        """Ask for a ticket the way the launcher does: the install token, no Origin."""
        launcher = client or self.client()
        response = launcher.post("/api/session/ticket", headers={"Authorization": f"Bearer {self.token}"})
        assert response.status_code == 200, response.text
        ticket = response.json()["ticket"]
        assert isinstance(ticket, str)
        return ticket

    def signed_in_client(self, raise_server_exceptions: bool = True) -> TestClient:
        """A client holding a valid session cookie."""
        client = self.client(raise_server_exceptions=raise_server_exceptions)
        response = client.post("/api/session", json={"ticket": self.ticket()}, headers=WRITE_HEADERS)
        assert response.status_code == 204, response.text
        assert client.cookies.get("shelfsync_session")
        return client


@dataclass
class RawResponse:
    status: int
    headers: list[tuple[bytes, bytes]]
    body: bytes

    def header(self, name: str) -> str | None:
        wanted = name.lower().encode()
        for key, value in self.headers:
            if key == wanted:
                return value.decode("latin-1")
        return None


def asgi_http(
    app: FastAPI,
    method: str,
    path: str,
    headers: list[tuple[bytes, bytes]],
    body: bytes = b"",
    query: bytes = b"",
) -> RawResponse:
    """Call the app straight through ASGI with exactly these raw headers. For requests an HTTP client or server
    wouldn't send (two Host headers, a non-ASCII Authorization header)."""
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "query_string": query,
        "headers": headers,
        "client": ("127.0.0.1", 50000),
        "server": ("127.0.0.1", PORT),
    }
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    asyncio.run(app(scope, receive, send))  # type: ignore[arg-type]
    start = next(message for message in sent if message["type"] == "http.response.start")
    payload = b"".join(message.get("body", b"") for message in sent if message["type"] == "http.response.body")
    return RawResponse(start["status"], list(start["headers"]), payload)


def make_harness(port: int = PORT, store: MemorySecretStore | None = None, ui_dir: Path | None = None) -> Harness:
    """API only by default (ui_dir=None), so the result never depends on whether frontend/dist was built on this
    PC; the static-mount tests pass a folder of their own."""
    secret_store = store if store is not None else MemorySecretStore()
    clock = FakeClock()
    app = create_app(port, InstallToken(secret_store), clock, ui_dir=ui_dir)
    return Harness(app=app, store=secret_store, clock=clock, port=port)
