"""Host, Origin, CSRF and session checks (SYS-03, 06 section 2): a pure ASGI middleware that denies by default.

The checks run in this order, and the first that fails answers (403, or 401 for the session):
1. Host: exactly one `Host` header, equal to `127.0.0.1:<port>` or `localhost:<port>` (lowercase, exact). Every
   request, whatever the path. This is what stops DNS rebinding.
2. Origin: if present, exactly one and equal to `http://` + this request's Host.
3. Methods: every method except GET and HEAD changes state and needs ShelfSync's Origin and `X-ShelfSync: 1`.
4. Session: every path under /api needs a valid session cookie, except the paths in `SESSION_EXEMPT_PATHS`.
5. No CORS: OPTIONS under /api is refused (and `SecurityHeadersMiddleware` strips any `Access-Control-*` header).

The one exception to 2 and 3 is `POST /api/session/ticket` (the launcher is not a browser): it must carry **no**
Origin at all, and any Origin, ShelfSync's own included, is refused. It checks the install token itself.

Nothing here reads a request body, and nothing logs a header value: a refusal is logged with the name of the check,
the method and the path only.
"""

import logging

from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from shelfsync.api.errors import forbidden, signed_out
from shelfsync.secure.headers import is_api_path
from shelfsync.secure.sessions import SessionStore

SESSION_COOKIE = "shelfsync_session"
CSRF_HEADER = b"x-shelfsync"
CSRF_VALUE = b"1"

HEALTH_PATH = "/api/health"
TICKET_PATH = "/api/session/ticket"
SIGN_IN_PATH = "/api/session"
# bandit B105 flags the name: this is a URL path, not a password
RESET_TOKEN_PATH = "/api/session/reset-token"  # nosec B105

# The only /api paths that don't need a session (the contract in docs/runs/m1a.2-security.md item 11). The method
# isn't part of the exemption: a wrong method on these paths reaches the router and gets its 405.
SESSION_EXEMPT_PATHS = frozenset({HEALTH_PATH, TICKET_PATH, SIGN_IN_PATH})

_READ_METHODS = frozenset({"GET", "HEAD"})
_log = logging.getLogger("shelfsync.security")


def _printable(value: str, limit: int = 200) -> str:
    """For a log line: no control characters, bounded length."""
    return "".join(ch if ch.isprintable() else "?" for ch in value[:limit])


def _header_values(headers: list[tuple[bytes, bytes]], name: bytes) -> list[bytes]:
    return [value for key, value in headers if key == name]


def _cookie_values(headers: list[tuple[bytes, bytes]], cookie_name: str) -> list[str]:
    values: list[str] = []
    for raw in _header_values(headers, b"cookie"):
        for part in raw.decode("latin-1").split(";"):
            name, separator, value = part.strip().partition("=")
            if separator and name == cookie_name:
                values.append(value)
    return values


class GuardMiddleware:
    def __init__(self, app: ASGIApp, *, port: int, sessions: SessionStore) -> None:
        self.app = app
        self._sessions = sessions
        self._hosts = frozenset({f"127.0.0.1:{port}", f"localhost:{port}"})

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await self.app(scope, receive, send)
            return
        if scope["type"] != "http":
            # No WebSocket route exists. Deny by default: whoever adds one decides how it is checked.
            _log.warning("request refused by the %s check: %s", scope["type"], _printable(scope.get("path", "")))
            await send({"type": "websocket.close", "code": 1008})
            return
        refusal = self._check(scope)
        if refusal is not None:
            check, response = refusal
            _log.warning("request refused by the %s check: %s %s", check, scope["method"], _printable(scope["path"]))
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)

    def _check(self, scope: Scope) -> tuple[str, Response] | None:
        headers: list[tuple[bytes, bytes]] = scope["headers"]
        method: str = scope["method"]
        path: str = scope["path"]

        # 1. Host
        hosts = _header_values(headers, b"host")
        if len(hosts) != 1:
            return "host", forbidden()
        host = hosts[0].decode("latin-1")
        if host not in self._hosts:
            return "host", forbidden()

        # 2. Origin
        origins = _header_values(headers, b"origin")
        if path == TICKET_PATH:
            # The launcher is no browser, so a request with any Origin is a web page trying the route. Refused.
            # Without one the route has no more checks here: it needs the install token, which it checks itself.
            return ("origin", forbidden()) if origins else None
        if origins and (len(origins) > 1 or origins[0].decode("latin-1") != f"http://{host}"):
            return "origin", forbidden()

        # 3. Methods that change state need ShelfSync's Origin and the CSRF header
        if method not in _READ_METHODS:
            if not origins:
                return "csrf-origin", forbidden()
            if _header_values(headers, CSRF_HEADER) != [CSRF_VALUE]:
                return "csrf-header", forbidden()

        # 5. No CORS (placed before the session so a preflight never learns whether a path exists)
        if method == "OPTIONS" and is_api_path(path):
            return "cors", forbidden()

        # 4. Session
        needs_session = is_api_path(path) and path not in SESSION_EXEMPT_PATHS
        if needs_session and not any(
            self._sessions.check_session(value) for value in _cookie_values(headers, SESSION_COOKIE)
        ):
            return "session", signed_out()
        return None
