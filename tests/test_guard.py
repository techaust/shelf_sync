"""SYS-03, NFR-5: the Host, Origin, CSRF and session checks (DNS rebinding, other web pages, other local servers)."""

import asyncio
from pathlib import Path
from typing import Any

import pytest
from fastapi.routing import iter_route_contexts
from fastapi.testclient import TestClient

from shelfsync.secure.headers import is_api_path
from shelfsync.secure.middleware import SESSION_EXEMPT_PATHS
from tests.support import HOST, ORIGIN, PORT, WRITE_HEADERS, Harness, asgi_http, make_harness

WRITE_METHODS = ["POST", "PUT", "PATCH", "DELETE"]


@pytest.fixture
def harness() -> Harness:
    return make_harness()


@pytest.fixture(params=["api only", "with the UI"])
def any_harness(request: pytest.FixtureRequest, tmp_path: Path) -> Harness:
    """The app without and with the static UI mount (M1a.3), for the route-table tests."""
    if request.param == "api only":
        return make_harness()
    (tmp_path / "index.html").write_text("<!doctype html><title>ShelfSync</title>", encoding="utf-8")
    return make_harness(ui_dir=tmp_path)


def assert_nothing_happened(harness: Harness, client: TestClient, token_before: str) -> None:
    """The refused request changed nothing: the session still works (a protected path is answered by the router,
    404, not 401) and the install token is the same."""
    assert client.get("/api/nope").status_code == 404
    assert harness.token == token_before


# ---- 1. Host --------------------------------------------------------------------------------------------------


WRONG_HOSTS = [
    f"evil.example:{PORT}",
    f"127.0.0.1:{PORT}.evil.example",
    f"127.0.0.1:{PORT + 1}",
    "127.0.0.1",
    "localhost",
    f"[::1]:{PORT}",
    f"0.0.0.0:{PORT}",
    f"LOCALHOST:{PORT}",
    f"user@127.0.0.1:{PORT}",
    "",
]


@pytest.mark.parametrize("host", WRONG_HOSTS)
def test_a_wrong_host_is_refused_on_health(harness: Harness, host: str) -> None:
    """SYS-03: DNS rebinding. The Host check runs on every request, /api/health included."""
    response = harness.client().get("/api/health", headers={"Host": host})
    assert response.status_code == 403
    assert response.json() == {"error": "forbidden"}


@pytest.mark.parametrize("host", WRONG_HOSTS)
def test_a_wrong_host_is_refused_on_the_ticket_route_even_with_the_right_token(harness: Harness, host: str) -> None:
    """SYS-03: the ticket route still has the Host check."""
    response = harness.client().post(
        "/api/session/ticket", headers={"Host": host, "Authorization": f"Bearer {harness.token}"}
    )
    assert response.status_code == 403


@pytest.mark.parametrize("path", ["/", "/index.html", "/assets/app.js", "/nope"])
def test_a_wrong_host_is_refused_outside_api_too(harness: Harness, path: str) -> None:
    """SYS-03: the check covers the static UI paths, not just /api."""
    assert harness.client().get(path, headers={"Host": "evil.example"}).status_code == 403


def test_both_loopback_names_are_accepted(harness: Harness) -> None:
    """SYS-03: 127.0.0.1:<port> and localhost:<port>, exactly."""
    assert harness.client(host=f"127.0.0.1:{PORT}").get("/api/health").status_code == 200
    assert harness.client(host=f"localhost:{PORT}").get("/api/health").status_code == 200


def test_two_host_headers_are_refused(harness: Harness) -> None:
    """SYS-03: exactly one Host header, whichever order. (h11 under uvicorn already answers 400 for two; this is
    the app's own check, reached here by calling ASGI directly.)"""
    good = (b"host", HOST.encode())
    evil = (b"host", b"evil.example")
    assert asgi_http(harness.app, "GET", "/api/health", [good, evil]).status == 403
    assert asgi_http(harness.app, "GET", "/api/health", [evil, good]).status == 403
    assert asgi_http(harness.app, "GET", "/api/health", [good, good]).status == 403


def test_no_host_header_is_refused(harness: Harness) -> None:
    """SYS-03: HTTP/1.0 may send none (h11 refuses it for HTTP/1.1 before the app)."""
    assert asgi_http(harness.app, "GET", "/api/health", []).status == 403


def test_a_refusal_logs_the_check_method_and_path_only(harness: Harness, caplog: pytest.LogCaptureFixture) -> None:
    """LOG-01: refusals are logged without any header value."""
    caplog.set_level("WARNING", logger="shelfsync.security")
    harness.client().get("/api/health", headers={"Host": "evil.example", "X-Probe": "header-value-1234"})
    assert [record.getMessage() for record in caplog.records] == ["request refused by the host check: GET /api/health"]


# ---- 2. Origin, and 3. state-changing methods --------------------------------------------------------------


FOREIGN_ORIGINS = [
    "http://evil.example",
    "http://127.0.0.1:3000",  # another local server: same site, so SameSite doesn't stop it
    f"http://localhost:{PORT}",  # a different name for the same server while Host is 127.0.0.1
    f"https://127.0.0.1:{PORT}",
    "null",
    "",
    f"{ORIGIN}/",
    f"HTTP://{HOST}",
]


@pytest.mark.parametrize("origin", FOREIGN_ORIGINS)
@pytest.mark.parametrize("method", WRITE_METHODS)
def test_a_state_changing_request_with_a_foreign_origin_is_refused(harness: Harness, method: str, origin: str) -> None:
    """SYS-03: cross-origin writes, with a valid session cookie and the CSRF header, still get 403."""
    client = harness.signed_in_client()
    token = harness.token
    response = client.request(method, "/api/session/reset-token", headers={"Origin": origin, "X-ShelfSync": "1"})
    assert response.status_code == 403
    assert response.json() == {"error": "forbidden"}
    assert_nothing_happened(harness, client, token)


@pytest.mark.parametrize("origin", FOREIGN_ORIGINS)
def test_a_foreign_origin_on_a_get_is_refused(harness: Harness, origin: str) -> None:
    """SYS-03: Origin, if present on any request, must be ShelfSync's."""
    assert harness.client().get("/api/health", headers={"Origin": origin}).status_code == 403
    assert harness.client().get("/", headers={"Origin": origin}).status_code == 403


def test_shelfsyncs_own_origin_on_a_get_is_fine(harness: Harness) -> None:
    """SYS-03: the page's own GETs may carry its Origin."""
    assert harness.client().get("/api/health", headers={"Origin": ORIGIN}).status_code == 200


def test_the_origin_must_match_the_host_the_request_used(harness: Harness) -> None:
    """SYS-03: via localhost:<port> the right Origin is http://localhost:<port>."""
    client = harness.client(host=f"localhost:{PORT}")
    assert client.get("/api/health", headers={"Origin": f"http://localhost:{PORT}"}).status_code == 200
    assert client.get("/api/health", headers={"Origin": ORIGIN}).status_code == 403


def test_two_origin_headers_are_refused(harness: Harness) -> None:
    """SYS-03: one Origin only."""
    headers = [(b"host", HOST.encode()), (b"origin", ORIGIN.encode()), (b"origin", ORIGIN.encode())]
    assert asgi_http(harness.app, "GET", "/api/health", headers).status == 403


@pytest.mark.parametrize("method", WRITE_METHODS)
def test_a_write_with_no_origin_is_refused(harness: Harness, method: str) -> None:
    """SYS-03: a state-changing request with no Origin (other than the ticket route) gets 403."""
    client = harness.signed_in_client()
    assert client.request(method, "/api/session/reset-token", headers={"X-ShelfSync": "1"}).status_code == 403


@pytest.mark.parametrize("value", [None, "0", "true", "1 ", " 1", "11", "yes", ""])
def test_a_write_without_the_exact_csrf_header_is_refused(harness: Harness, value: str | None) -> None:
    """SYS-03: POST with cookie and Origin but no X-ShelfSync: 1 gets 403."""
    client = harness.signed_in_client()
    token = harness.token
    headers = {"Origin": ORIGIN}
    if value is not None:
        headers["X-ShelfSync"] = value
    response = client.post("/api/session/reset-token", headers=headers)
    assert response.status_code == 403
    assert_nothing_happened(harness, client, token)


def test_two_csrf_headers_are_refused(harness: Harness) -> None:
    """SYS-03: exactly one X-ShelfSync header."""
    client = harness.signed_in_client()
    cookie = client.cookies.get("shelfsync_session")
    headers = [
        (b"host", HOST.encode()),
        (b"origin", ORIGIN.encode()),
        (b"x-shelfsync", b"1"),
        (b"x-shelfsync", b"1"),
        (b"cookie", f"shelfsync_session={cookie}".encode()),
    ]
    assert asgi_http(harness.app, "POST", "/api/session/reset-token", headers).status == 403


# ---- 4. Session --------------------------------------------------------------------------------------------------


# Routes outside /api that may exist, because they are served without a session (the static UI). M1a.3's static
# mount at "/" is the one entry: Starlette stores a mount at "/" with the path "" (it strips the trailing slash).
ALLOWED_OUTSIDE_API: set[str] = {""}

# The routes that need no session: exactly these three (docs/runs/m1a.2-security.md item 11).
EXPECTED_EXEMPT_ROUTES = {("GET", "/api/health"), ("POST", "/api/session/ticket"), ("POST", "/api/session")}


def _route_contexts(app: Any) -> list[tuple[object, object]]:
    """(path, methods) of every route. FastAPI 0.143 keeps included routers as one lazy `_IncludedRouter` object in
    `app.routes`, so the walk goes through `fastapi.routing.iter_route_contexts`, the function FastAPI's own
    OpenAPI builder uses, which yields every route with its full path."""
    return [
        (getattr(context, "path", None), getattr(context, "methods", None))
        for context in iter_route_contexts(app.routes)
    ]


def _api_routes(app: Any) -> list[tuple[str, str]]:
    """Every (method, path) under /api, a path parameter turned into a plain segment."""
    found: list[tuple[str, str]] = []
    for path, methods in _route_contexts(app):
        if isinstance(path, str) and is_api_path(path) and isinstance(methods, set):
            plain = path.replace("{", "").replace("}", "")
            found.extend((method, plain) for method in sorted(methods))
    return found


def test_every_route_is_a_known_kind_under_api_or_on_the_allowlist(any_harness: Harness) -> None:
    """SYS-03: nothing slips through the route-table test unseen, with and without the static UI mount."""
    seen = _route_contexts(any_harness.app)
    assert seen  # the walk found routes at all
    for path, methods in seen:
        assert isinstance(path, str), f"a route with no path ({methods!r}) isn't understood by this test"
        if is_api_path(path):
            assert isinstance(methods, set) and methods, f"{path} is under /api but has no methods"
        else:
            assert path in ALLOWED_OUTSIDE_API, f"{path} is outside /api and not on the allowlist"


def test_the_ui_mount_is_the_only_route_outside_api(any_harness: Harness) -> None:
    """SYS-03: with the UI built, exactly one route sits outside /api, the static mount (path "", see the
    allowlist); without it, none does."""
    outside = [path for path, _ in _route_contexts(any_harness.app) if isinstance(path, str) and not is_api_path(path)]
    has_ui = any(getattr(route, "name", None) == "ui" for route in any_harness.app.routes)
    assert outside == ([""] if has_ui else [])


def test_the_exempt_routes_are_exactly_the_three_documented_ones(any_harness: Harness) -> None:
    """SYS-03: the routes that need no session, as (method, path) pairs, are pinned."""
    exempt = {(method, path) for method, path in _api_routes(any_harness.app) if path in SESSION_EXEMPT_PATHS}
    assert exempt == EXPECTED_EXEMPT_ROUTES
    assert set(SESSION_EXEMPT_PATHS) == {"/api/health", "/api/session/ticket", "/api/session"}


def test_route_table_every_api_route_outside_the_exemption_table_refuses_without_a_cookie(any_harness: Harness) -> None:
    """SYS-03: walks the route table, so a route added in a later milestone is checked without anyone remembering to."""
    routes = _api_routes(any_harness.app)
    assert ("GET", "/api/health") in routes
    assert {("GET", "/api/settings/app"), ("PUT", "/api/settings/app")} <= set(routes)  # SET-06 (m1b.3)
    client = any_harness.client()
    checked = 0
    for method, path in routes:
        if path in SESSION_EXEMPT_PATHS:
            continue
        headers = {} if method in ("GET", "HEAD") else WRITE_HEADERS
        response = client.request(method, path, headers=headers)
        assert response.status_code == 401, (method, path)
        assert response.json() == {"error": "signed_out"}, (method, path)
        checked += 1
    assert checked >= 2  # at least reset-token and session status today


@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize("path", ["/api/nope", "/api", "/api/", "/api/health/", "/api/session/x", "/api/a/b/c"])
def test_unknown_paths_under_api_need_a_session_too(harness: Harness, method: str, path: str) -> None:
    """SYS-03: deny by default: a path nobody wrote yet is 401, not 404."""
    headers = {} if method == "GET" else WRITE_HEADERS
    assert harness.client().request(method, path, headers=headers).status_code == 401


@pytest.mark.parametrize("path", ["/", "/nope", "/index.html", "/API/health", "/apix", "/ap"])
def test_a_path_outside_api_is_never_401(harness: Harness, path: str) -> None:
    """SYS-03: the static UI is served without a session (404 today)."""
    response = harness.client().get(path)
    assert response.status_code == 404


@pytest.mark.parametrize(
    "cookie",
    [
        "shelfsync_session=forged",
        "shelfsync_session=",
        "other=1",
        "shelfsync_session=" + "x" * 5000,
        "shelfsync_session",
    ],
)
def test_a_forged_cookie_is_401(harness: Harness, cookie: str) -> None:
    """SYS-03: only a session this server made counts."""
    response = harness.client().get("/api/nope", headers={"Cookie": cookie})
    assert response.status_code == 401


def test_a_valid_cookie_among_other_cookies_works(harness: Harness) -> None:
    """SYS-03: the session cookie is found whatever else the browser sends."""
    client = harness.signed_in_client()
    session = client.cookies.get("shelfsync_session")
    response = client.get("/api/nope", headers={"Cookie": f"a=1; shelfsync_session={session}; b=2"})
    assert response.status_code == 404  # signed in, so the router answers: no such route


def test_a_tossed_bad_cookie_next_to_the_real_one_does_not_sign_the_user_out(harness: Harness) -> None:
    """SYS-03: another local server can set a cookie of the same name; the valid one still works."""
    client = harness.signed_in_client()
    session = client.cookies.get("shelfsync_session")
    headers = {"Cookie": f"shelfsync_session=tossed; shelfsync_session={session}"}
    assert client.get("/api/nope", headers=headers).status_code == 404


# ---- 5. No CORS ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/api/health", "/api/session", "/api/session/ticket", "/api/nope"])
def test_options_under_api_is_refused_and_carries_no_cors_headers(harness: Harness, path: str) -> None:
    """SYS-03: no CORS: a preflight never succeeds."""
    client = harness.signed_in_client()
    for headers in (
        {},
        {"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"},
        WRITE_HEADERS,
    ):
        response = client.options(path, headers=headers)
        assert response.status_code in (403, 405)
        assert not [name for name in response.headers if name.lower().startswith("access-control-")]


def test_a_websocket_is_refused(harness: Harness) -> None:
    """SYS-03: no WebSocket route exists; deny by default."""
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "websocket.connect"}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    scope = {"type": "websocket", "path": "/api/events", "headers": [(b"host", HOST.encode())], "subprotocols": []}
    asyncio.run(harness.app(scope, receive, send))  # type: ignore[arg-type]
    assert sent == [{"type": "websocket.close", "code": 1008}]
