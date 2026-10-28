"""SET-05: the body size limit for chosen routes (`secure/body_limit.py`), on its own and in the real app.

The behaviour of the two backup routes under it is in tests/test_backup_api.py."""

import asyncio
import json
from typing import Any

import pytest
from starlette.types import Message, Receive, Scope, Send

from shelfsync.secure.body_limit import BodyLimit, BodyLimitMiddleware

LIMIT = BodyLimit(100, 422, "export_invalid")


class Probe:
    """An app that reads its whole body and says how much it got."""

    def __init__(self) -> None:
        self.calls = 0
        self.received = 0
        self.disconnected = False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        self.calls += 1
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                self.disconnected = True
                break
            self.received += len(message.get("body", b""))
            if not message.get("more_body", False):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


def call(
    app: Probe, headers: list[tuple[bytes, bytes]], chunks: list[bytes], method: str = "POST", path: str = "/x"
) -> tuple[int, bytes]:
    middleware = BodyLimitMiddleware(app, limits={("POST", "/x"): LIMIT})
    scope: Scope = {"type": "http", "method": method, "path": path, "headers": headers}
    pending: list[Message] = [
        {"type": "http.request", "body": chunk, "more_body": index < len(chunks) - 1}
        for index, chunk in enumerate(chunks)
    ]
    sent: list[Message] = []

    async def receive() -> Message:
        return pending.pop(0) if pending else {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        sent.append(message)

    asyncio.run(middleware(scope, receive, send))
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return status, body


def length(value: bytes) -> list[tuple[bytes, bytes]]:
    return [(b"content-length", value)]


def test_a_body_within_the_limit_passes_through() -> None:
    app = Probe()
    assert call(app, length(b"100"), [b"x" * 100]) == (200, b"ok")
    assert app.calls == 1 and app.received == 100


def test_a_declared_length_over_the_limit_is_refused_without_calling_the_app() -> None:
    app = Probe()
    status, body = call(app, length(b"101"), [b"x" * 101])
    assert (status, json.loads(body)) == (422, {"error": "export_invalid"})
    assert app.calls == 0


@pytest.mark.parametrize("value", [b"", b"-1", b"1.5", b"1e2", b" 1", b"0x5", b"\xd9\xa1", b"1" * 13])
def test_a_length_that_isnt_plain_digits_is_refused(value: bytes) -> None:
    app = Probe()
    assert call(app, length(value), [b"x"])[0] == 422
    assert app.calls == 0


def test_no_length_and_two_lengths_are_refused() -> None:
    app = Probe()
    assert call(app, [], [b"x"])[0] == 422  # a chunked body has no length
    assert call(app, length(b"1") + length(b"1"), [b"x"])[0] == 422
    assert app.calls == 0


def test_a_body_longer_than_declared_gets_the_routes_own_error_and_the_apps_answer_is_dropped() -> None:
    """R9. A real server (h11, httptools) ends a request at its declared length, so this can't happen through one; if
    it did, the app is told the client went away, whatever it says is dropped, and the fixed 422 is sent."""
    app = Probe()
    status, body = call(app, length(b"10"), [b"x" * 60, b"x" * 60])  # declared 10, sent 120: past the limit of 100
    assert (status, json.loads(body)) == (422, {"error": "export_invalid"})
    assert app.disconnected and app.received <= 100
    assert b"ok" not in body  # the probe's own 200 never reached the client


def test_other_methods_paths_and_scopes_are_untouched() -> None:
    app = Probe()
    assert call(app, [], [b"x" * 500], method="GET")[0] == 200
    assert call(app, [], [b"x" * 500], path="/other")[0] == 200
    assert app.calls == 2


def test_a_non_http_scope_passes_through() -> None:
    reached: list[Any] = []

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        reached.append(scope["type"])

    middleware = BodyLimitMiddleware(inner, limits={("POST", "/x"): LIMIT})

    async def never(*args: Any) -> Any:
        raise AssertionError

    asyncio.run(middleware({"type": "lifespan"}, never, never))
    assert reached == ["lifespan"]
