"""SYS-03, SET-06: the sign-in routes and their abuse cases."""

from http.cookies import SimpleCookie

import pytest

from shelfsync.secure.sessions import TICKET_LIFETIME_SECONDS
from tests.support import HOST, ORIGIN, PORT, WRITE_HEADERS, Harness, asgi_http, make_harness


@pytest.fixture
def harness() -> Harness:
    return make_harness()


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---- POST /api/session/ticket ------------------------------------------------------------------------------------


def test_ticket_with_the_install_token_gives_a_ticket_and_no_store(harness: Harness) -> None:
    """SYS-03: 200 {"ticket", "expires_in": 60}, Cache-Control: no-store. No session, no X-ShelfSync needed."""
    response = harness.client().post("/api/session/ticket", headers=bearer(harness.token))
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"ticket", "expires_in"}
    assert body["expires_in"] == 60 == int(TICKET_LIFETIME_SECONDS)
    assert len(body["ticket"]) >= 43
    assert response.headers["cache-control"] == "no-store"


def test_the_ticket_scheme_is_case_insensitive(harness: Harness) -> None:
    """SYS-03: Bearer, bearer and BEARER."""
    for scheme in ("Bearer", "bearer", "BEARER"):
        response = harness.client().post("/api/session/ticket", headers={"Authorization": f"{scheme} {harness.token}"})
        assert response.status_code == 200, scheme


@pytest.mark.parametrize(
    "origin",
    [ORIGIN, "null", "http://evil.example", "http://127.0.0.1:3000", f"http://localhost:{PORT}", ""],
)
def test_ticket_route_refuses_any_origin_even_with_the_right_token(harness: Harness, origin: str) -> None:
    """SYS-03: a web page can't use it. ShelfSync's own Origin is refused too: only the launcher calls it."""
    response = harness.client().post("/api/session/ticket", headers={**bearer(harness.token), "Origin": origin})
    assert response.status_code == 403
    assert response.json() == {"error": "forbidden"}


def test_ticket_route_without_authorization_is_401(harness: Harness) -> None:
    """SYS-03: no token, no ticket."""
    response = harness.client().post("/api/session/ticket")
    assert response.status_code == 401
    assert response.json() == {"error": "bad_token"}


def test_ticket_route_with_a_wrong_token_is_401(harness: Harness) -> None:
    """SYS-03."""
    response = harness.client().post("/api/session/ticket", headers=bearer("not-the-token"))
    assert response.status_code == 401
    assert response.json() == {"error": "bad_token"}


def test_the_token_in_the_query_the_body_or_a_cookie_is_not_accepted(harness: Harness) -> None:
    """SYS-03: the install token is accepted in the Authorization header only."""
    token = harness.token
    client = harness.client()
    assert client.post(f"/api/session/ticket?token={token}").status_code == 401
    assert client.post(f"/api/session/ticket?access_token={token}&Authorization=Bearer%20{token}").status_code == 401
    assert (
        client.post("/api/session/ticket", json={"token": token, "authorization": f"Bearer {token}"}).status_code == 401
    )
    assert client.post("/api/session/ticket", content=token).status_code == 401
    assert (
        client.post("/api/session/ticket", headers={"Cookie": f"token={token}; shelfsync_session={token}"}).status_code
        == 401
    )
    assert client.post("/api/session/ticket", headers={"X-Install-Token": token}).status_code == 401


@pytest.mark.parametrize(
    "value",
    [
        "Bearer {t} extra",
        "Bearer  {t}",
        "Bearer {t} ",
        " Bearer {t}",
        "Basic {t}",
        "Token {t}",
        "Bearer",
        "Bearer ",
        "{t}",
        "Bearer\t{t}",
        "BearerX {t}",
        "Bearer {t}x",
        "Bearer x{t}",
    ],
)
def test_a_malformed_authorization_header_is_401(harness: Harness, value: str) -> None:
    """SYS-03: only `Bearer <token>` with nothing else."""
    header = value.replace("{t}", harness.token).encode()
    response = asgi_http(
        harness.app, "POST", "/api/session/ticket", [(b"host", HOST.encode()), (b"authorization", header)]
    )
    assert response.status == 401


def test_a_non_ascii_authorization_header_is_401_not_500(harness: Harness) -> None:
    """SYS-03: hmac.compare_digest raises TypeError on a non-ASCII str; the token check works on bytes."""
    for raw in (
        "Bearer é".encode("latin-1"),
        "Bearer é".encode(),
        b"Bearer \xff\xfe\x80",
        b"Bearer " + b"\xc3\x28" * 50,
    ):
        response = asgi_http(
            harness.app, "POST", "/api/session/ticket", [(b"host", HOST.encode()), (b"authorization", raw)]
        )
        assert response.status == 401, raw


def test_two_authorization_headers_are_401(harness: Harness) -> None:
    """SYS-03: one header only, so a second one can't smuggle a different value past a proxy-style check."""
    good = harness.token.encode()
    headers = [(b"host", HOST.encode()), (b"authorization", b"Bearer " + good), (b"authorization", b"Bearer " + good)]
    assert asgi_http(harness.app, "POST", "/api/session/ticket", headers).status == 401


def test_a_very_long_authorization_header_is_401(harness: Harness) -> None:
    """SYS-03: no error for a huge value."""
    response = harness.client().post("/api/session/ticket", headers=bearer("x" * 100_000))
    assert response.status_code == 401


def test_get_on_the_ticket_route_is_405_with_the_security_headers(harness: Harness) -> None:
    """SYS-03: GET reaches the router (405), not a 401, and carries the headers."""
    response = harness.client().get("/api/session/ticket", headers=bearer(harness.token))
    assert response.status_code == 405
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["cache-control"] == "no-store"


# ---- POST /api/session -------------------------------------------------------------------------------------------


def test_signing_in_sets_exactly_the_documented_cookie(harness: Harness) -> None:
    """SYS-03: 204 with shelfsync_session; HttpOnly; SameSite=Strict; Path=/ and no Domain, Expires, Max-Age, Secure.

    Starlette writes the SameSite value in lower case (`strict`); the attribute value is case-insensitive.
    """
    client = harness.client()
    response = client.post("/api/session", json={"ticket": harness.ticket()}, headers=WRITE_HEADERS)
    assert response.status_code == 204
    assert response.content == b""
    raw = response.headers.get_list("set-cookie")
    assert len(raw) == 1
    parts = [part.strip() for part in raw[0].split(";")]
    name, _, value = parts[0].partition("=")
    assert name == "shelfsync_session"
    assert len(value) >= 43
    attributes = {part.split("=")[0].lower(): part.partition("=")[2].lower() for part in parts[1:]}
    assert attributes == {"httponly": "", "samesite": "strict", "path": "/"}
    parsed = SimpleCookie(raw[0])["shelfsync_session"]
    assert parsed["httponly"] is True
    assert parsed["samesite"].lower() == "strict"
    assert parsed["path"] == "/"
    for absent in ("domain", "expires", "max-age", "secure"):
        assert not parsed[absent], absent


def test_a_signed_in_client_can_use_the_session(harness: Harness) -> None:
    """SYS-03: the cookie works for GET and for writes with the Origin and X-ShelfSync headers."""
    client = harness.signed_in_client()
    assert client.get("/api/nope").status_code == 404  # signed in: the router answers
    assert client.post("/api/nope", headers=WRITE_HEADERS).status_code == 404


@pytest.mark.parametrize("missing", ["Origin", "X-ShelfSync"])
def test_sign_in_needs_the_origin_and_the_csrf_header(harness: Harness, missing: str) -> None:
    """SYS-03: POST /api/session is for the page, so it needs ShelfSync's Origin and X-ShelfSync: 1."""
    headers = {key: value for key, value in WRITE_HEADERS.items() if key != missing}
    response = harness.client().post("/api/session", json={"ticket": harness.ticket()}, headers=headers)
    assert response.status_code == 403
    assert "set-cookie" not in response.headers


def test_a_replayed_ticket_is_401(harness: Harness) -> None:
    """SYS-03: single use."""
    ticket = harness.ticket()
    assert harness.client().post("/api/session", json={"ticket": ticket}, headers=WRITE_HEADERS).status_code == 204
    replay = harness.client().post("/api/session", json={"ticket": ticket}, headers=WRITE_HEADERS)
    assert replay.status_code == 401
    assert replay.json() == {"error": "bad_ticket"}
    assert "set-cookie" not in replay.headers


def test_an_expired_ticket_is_401_and_one_just_inside_is_fine(harness: Harness) -> None:
    """SYS-03: 60 seconds. (The exact boundary, 59.999 against 60.000, is tested on the store in test_sessions.py;
    here the clock moves by whole seconds so floating-point sums can't blur it.)"""
    late, inside = harness.ticket(), harness.ticket()
    start = harness.clock.now
    harness.clock.now = start + 30.0
    assert harness.client().post("/api/session", json={"ticket": inside}, headers=WRITE_HEADERS).status_code == 204
    harness.clock.now = start + 60.0
    response = harness.client().post("/api/session", json={"ticket": late}, headers=WRITE_HEADERS)
    assert response.status_code == 401
    assert response.json() == {"error": "bad_ticket"}


@pytest.mark.parametrize("ticket", ["", "garbage", "x" * 10_240, "é", "a b", "\u0000"])
def test_a_garbage_ticket_is_401(harness: Harness, ticket: str) -> None:
    """SYS-03."""
    response = harness.client().post("/api/session", json={"ticket": ticket}, headers=WRITE_HEADERS)
    assert response.status_code == 401
    assert response.json() == {"error": "bad_ticket"}


def test_the_install_token_is_not_a_ticket(harness: Harness) -> None:
    """SYS-03: the token can't be used as a ticket."""
    response = harness.client().post("/api/session", json={"ticket": harness.token}, headers=WRITE_HEADERS)
    assert response.status_code == 401


@pytest.mark.parametrize(
    "payload",
    [{}, {"ticket": 5}, {"ticket": None}, {"ticket": ["a"]}, [], "text", 7],
)
def test_a_malformed_sign_in_body_is_422(harness: Harness, payload: object) -> None:
    """SYS-03: a body that isn't {"ticket": <string>} is 422 invalid_request."""
    response = harness.client().post("/api/session", json=payload, headers=WRITE_HEADERS)
    assert response.status_code == 422
    assert response.json() == {"error": "invalid_request"}


def test_a_sign_in_body_that_is_not_json_is_422(harness: Harness) -> None:
    """SYS-03."""
    headers = {**WRITE_HEADERS, "Content-Type": "application/json"}
    response = harness.client().post("/api/session", content=b"{not json", headers=headers)
    assert response.status_code == 422
    assert response.json() == {"error": "invalid_request"}


def test_a_ticket_only_works_for_the_session_it_made(harness: Harness) -> None:
    """SYS-03: two tickets make two independent sessions."""
    first, second = harness.signed_in_client(), harness.signed_in_client()
    assert first.cookies.get("shelfsync_session") != second.cookies.get("shelfsync_session")
    assert first.get("/api/nope").status_code == 404
    assert second.get("/api/nope").status_code == 404


# ---- GET /api/session/status --------------------------------------------------------------------------------------


def test_status_is_204_with_a_valid_session_and_has_no_body(harness: Harness) -> None:
    """SYS-03: the page asks "am I signed in?" on a refresh or in a second tab; reaching the route is the answer."""
    response = harness.signed_in_client().get("/api/session/status")
    assert response.status_code == 204
    assert response.content == b""
    assert response.headers["cache-control"] == "no-store"
    assert "set-cookie" not in response.headers  # it only reads the session, never renews or changes it


def test_status_without_a_cookie_is_401_signed_out(harness: Harness) -> None:
    """SYS-03: a normal session-protected route (not exempt), so the guard answers before it runs."""
    response = harness.client().get("/api/session/status")
    assert response.status_code == 401
    assert response.json() == {"error": "signed_out"}


def test_status_with_a_stale_or_made_up_cookie_is_401(harness: Harness) -> None:
    """SYS-03: a cookie ended by a token reset, or one never issued, is signed out."""
    client = harness.signed_in_client()
    stale = {"Cookie": f"shelfsync_session={client.cookies.get('shelfsync_session')}"}
    assert client.post("/api/session/reset-token", headers=WRITE_HEADERS).status_code == 204
    assert harness.client().get("/api/session/status", headers=stale).status_code == 401
    made_up = {"Cookie": "shelfsync_session=" + "A" * 43}
    assert harness.client().get("/api/session/status", headers=made_up).status_code == 401


def test_status_is_not_in_the_exemption_table() -> None:
    """SYS-03: the route is protected like every other; the method-blind exemption on /api/session isn't widened."""
    from shelfsync.api.session import SESSION_STATUS_PATH
    from shelfsync.secure.middleware import SESSION_EXEMPT_PATHS

    assert SESSION_STATUS_PATH == "/api/session/status"
    assert SESSION_STATUS_PATH not in SESSION_EXEMPT_PATHS


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_status_takes_get_only(harness: Harness, method: str) -> None:
    """SYS-03: a write to it is the route's 405 (with a session and the CSRF headers), never a sign-in or a change."""
    response = harness.signed_in_client().request(method, "/api/session/status", headers=WRITE_HEADERS)
    assert response.status_code == 405


# ---- POST /api/session/reset-token --------------------------------------------------------------------------------


def test_reset_token_needs_a_session(harness: Harness) -> None:
    """SET-06: no cookie, no reset, and the token is unchanged."""
    token = harness.token
    response = harness.client().post("/api/session/reset-token", headers=WRITE_HEADERS)
    assert response.status_code == 401
    assert harness.token == token


def test_reset_rotates_the_token_ends_every_session_and_clears_the_cookie(harness: Harness) -> None:
    """SET-06: the old token is refused at the ticket route and the new one accepted; the old cookies are 401."""
    old_token = harness.token
    first, second = harness.signed_in_client(), harness.signed_in_client()
    outstanding = harness.ticket()
    response = first.post("/api/session/reset-token", headers=WRITE_HEADERS)
    assert response.status_code == 204
    cleared = response.headers.get_list("set-cookie")
    assert len(cleared) == 1 and cleared[0].startswith("shelfsync_session=")
    assert "max-age=0" in cleared[0].lower()

    new_token = harness.token
    assert new_token != old_token
    launcher = harness.client()
    assert launcher.post("/api/session/ticket", headers=bearer(old_token)).status_code == 401
    assert launcher.post("/api/session/ticket", headers=bearer(new_token)).status_code == 200

    stale = {"Cookie": f"shelfsync_session={second.cookies.get('shelfsync_session')}"}
    assert harness.client().get("/api/nope", headers=stale).status_code == 401
    assert (
        harness.client().post("/api/session", json={"ticket": outstanding}, headers=WRITE_HEADERS).status_code == 401
    )  # a ticket issued before the reset is cancelled too


def test_after_a_reset_signing_in_again_works(harness: Harness) -> None:
    """SET-06: each tab signs in again with a new ticket from the new token."""
    client = harness.signed_in_client()
    assert client.post("/api/session/reset-token", headers=WRITE_HEADERS).status_code == 204
    again = harness.signed_in_client()
    assert again.get("/api/nope").status_code == 404


def test_reset_with_a_foreign_origin_does_nothing(harness: Harness) -> None:
    """SET-06: a web page can't reset the token."""
    token = harness.token
    client = harness.signed_in_client()
    response = client.post("/api/session/reset-token", headers={"Origin": "http://evil.example", "X-ShelfSync": "1"})
    assert response.status_code == 403
    assert harness.token == token
