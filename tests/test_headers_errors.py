"""SYS-03, LOG-01: security headers on every status, fixed error bodies, no traceback to the caller."""

import asyncio
import json
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import uvicorn
from fastapi import Response

from shelfsync import logs, server
from shelfsync.secure.headers import CONTENT_SECURITY_POLICY
from tests.support import WRITE_HEADERS, Harness, make_harness

EXPECTED_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; "
    "connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)
EXPECTED = {
    "content-security-policy": EXPECTED_CSP,
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "cross-origin-resource-policy": "same-origin",
}


class Boom(Exception):
    pass


@pytest.fixture
def harness() -> Harness:
    h = make_harness()

    @h.app.get("/api/boom")
    def boom() -> None:
        raise Boom(f"something broke with {h.token} inside")

    @h.app.get("/api/cors")
    def cors() -> Response:
        return Response(
            content="x", headers={"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Credentials": "true"}
        )

    @h.app.get("/api/overridden")
    def overridden() -> Response:
        return Response(
            content="x", headers={"Content-Security-Policy": "default-src *", "Cache-Control": "max-age=99"}
        )

    return h


def assert_headers(headers: httpx.Headers, api: bool = True) -> None:
    for name, value in EXPECTED.items():
        assert headers[name] == value, name
    if api:
        assert headers["cache-control"] == "no-store"
    assert not [name for name in headers if name.lower().startswith("access-control-")]


def test_the_policy_text_is_exactly_the_documented_one() -> None:
    """SYS-03: 06 section 2 and the brief's item 6."""
    assert CONTENT_SECURITY_POLICY == EXPECTED_CSP


def test_headers_on_200(harness: Harness) -> None:
    """SYS-03."""
    response = harness.client().get("/api/health")
    assert response.status_code == 200
    assert_headers(response.headers)


def test_headers_on_204(harness: Harness) -> None:
    """SYS-03."""
    response = harness.client().post("/api/session", json={"ticket": harness.ticket()}, headers=WRITE_HEADERS)
    assert response.status_code == 204
    assert_headers(response.headers)


def test_headers_on_401(harness: Harness) -> None:
    """SYS-03: both the session refusal and the bad token."""
    client = harness.client()
    for response in (client.get("/api/nope"), client.post("/api/session/ticket")):
        assert response.status_code == 401
        assert_headers(response.headers)


def test_headers_on_403(harness: Harness) -> None:
    """SYS-03: a refusal made by the guard itself carries them (the headers middleware is outside the guard)."""
    for response in (
        harness.client().get("/api/health", headers={"Host": "evil.example"}),
        harness.client().get("/api/health", headers={"Origin": "http://evil.example"}),
        harness.client().post("/api/session", json={}),
    ):
        assert response.status_code == 403
        assert_headers(response.headers)


def test_headers_on_404_inside_and_outside_api(harness: Harness) -> None:
    """SYS-03: no-store only under /api."""
    inside = harness.signed_in_client().get("/api/nope")
    assert inside.status_code == 404
    assert_headers(inside.headers)
    outside = harness.client().get("/nope")
    assert outside.status_code == 404
    assert_headers(outside.headers, api=False)
    assert "cache-control" not in outside.headers


def test_headers_on_405(harness: Harness) -> None:
    """SYS-03."""
    response = harness.client().get("/api/session/ticket")
    assert response.status_code == 405
    assert_headers(response.headers)


def test_headers_on_422(harness: Harness) -> None:
    """SYS-03."""
    response = harness.client().post("/api/session", json={"nope": 1}, headers=WRITE_HEADERS)
    assert response.status_code == 422
    assert_headers(response.headers)


def test_headers_on_500_from_the_outermost_error_middleware(harness: Harness) -> None:
    """SYS-03: Starlette's ServerErrorMiddleware answers an unhandled error outside every user middleware, so the
    headers are added by the 500 handler itself."""
    client = harness.signed_in_client(raise_server_exceptions=False)
    response = client.get("/api/boom")
    assert response.status_code == 500
    assert_headers(response.headers)
    assert response.headers["content-type"] == "application/json"


def test_app_headers_that_clash_are_replaced_and_cors_headers_are_stripped(harness: Harness) -> None:
    """SYS-03: a route can't weaken the headers or add Access-Control-*."""
    client = harness.signed_in_client()
    response = client.get("/api/cors")
    assert response.status_code == 200
    assert_headers(response.headers)
    response = client.get("/api/overridden")
    assert response.headers["content-security-policy"] == EXPECTED_CSP
    assert response.headers["cache-control"] == "no-store"


# ---- error bodies ------------------------------------------------------------------------------------------------


def test_422_body_is_fixed_and_never_echoes_the_input(harness: Harness) -> None:
    """SYS-03, LOG-01: FastAPI's default 422 body repeats each failed `input`; ours holds none of it."""
    token = harness.token
    for payload in ({"ticket": [token]}, {"ticket": 5, "extra": token}, {"wrong": token}):
        response = harness.client().post("/api/session", json=payload, headers=WRITE_HEADERS)
        assert response.status_code == 422
        assert response.json() == {"error": "invalid_request"}
        assert token not in response.text
    raw = harness.client().post(
        "/api/session", content=f"{{{token}".encode(), headers={**WRITE_HEADERS, "Content-Type": "application/json"}
    )
    assert raw.status_code == 422
    assert token not in raw.text


def test_500_body_is_fixed_and_holds_no_traceback_or_message(harness: Harness) -> None:
    """SYS-03, LOG-01: debug stays off; the body is `{"error":"internal"}` and nothing else."""
    assert harness.app.debug is False
    client = harness.signed_in_client(raise_server_exceptions=False)
    response = client.get("/api/boom")
    assert response.status_code == 500
    assert response.json() == {"error": "internal"}
    assert response.text == '{"error":"internal"}'
    assert harness.token not in response.text
    assert "Traceback" not in response.text and "Boom" not in response.text


def test_401_and_403_bodies_are_fixed(harness: Harness) -> None:
    """SYS-03: only these words ever come back, whatever was sent."""
    odd = "ticket-x' OR 1=1 --<script>"
    forbidden = harness.client().get("/api/health", headers={"Origin": odd})
    assert forbidden.json() == {"error": "forbidden"}
    signed_out = harness.client().get("/api/nope", headers={"Cookie": f"shelfsync_session={odd}"})
    assert signed_out.json() == {"error": "signed_out"}
    bad = harness.client().post("/api/session/ticket", headers={"Authorization": f"Bearer {odd}"})
    assert bad.json() == {"error": "bad_token"}
    for response in (forbidden, signed_out, bad):
        assert odd not in response.text


# ---- over a real server: the log holds the redacted traceback ---------------------------------------------------


@pytest.fixture
def live(harness: Harness, tmp_path: Path) -> Iterator[tuple[Harness, str, Path]]:
    handler = logs.configure_logging(tmp_path, retention_days=1)
    sock = server.bind_first_free([0])
    assert sock is not None
    port = sock.getsockname()[1]
    live_harness = make_harness(port=port, store=harness.store)

    @live_harness.app.get("/api/boom")
    def boom() -> None:
        raise Boom(f"something broke with {live_harness.token} inside")

    uv = uvicorn.Server(server.make_uvicorn_config(live_harness.app, port))
    thread = threading.Thread(target=lambda: asyncio.run(uv.serve(sockets=[sock])), daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not uv.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert uv.started
    try:
        yield live_harness, f"http://127.0.0.1:{port}", tmp_path
    finally:
        uv.should_exit = True
        thread.join(timeout=10)
        sock.close()
        handler.flush()
        logs.remove_logging(handler)


def test_over_a_real_server_the_500_log_holds_the_redacted_traceback(live: tuple[Harness, str, Path]) -> None:
    """SYS-03, LOG-01: uvicorn logs the unhandled error with its traceback; the install token inside the message
    is masked in the log and absent from the body."""
    harness, base, folder = live
    token = harness.token
    port = base.rsplit(":", 1)[1]
    with httpx.Client(base_url=base, timeout=5) as client:
        ticket = client.post("/api/session/ticket", headers={"Authorization": f"Bearer {token}"}).json()["ticket"]
        origin = f"http://127.0.0.1:{port}"
        signed = client.post("/api/session", json={"ticket": ticket}, headers={"Origin": origin, "X-ShelfSync": "1"})
        assert signed.status_code == 204
        response = client.get("/api/boom")
    assert response.status_code == 500
    assert response.json() == {"error": "internal"}
    for name, value in EXPECTED.items():
        assert response.headers[name] == value
    time.sleep(0.2)
    text = (folder / logs.LOG_FILE_NAME).read_text(encoding="utf-8")
    assert token not in text
    entries = [json.loads(line) for line in text.splitlines()]
    errors = [entry for entry in entries if "Boom" in entry["message"]]
    assert errors, "the unhandled error was not logged"
    assert "Traceback" in errors[0]["message"]
    assert "something broke with [redacted] inside" in errors[0]["message"]
