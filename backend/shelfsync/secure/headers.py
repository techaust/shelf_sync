"""Security headers (06 section 2): one set on every response, and no CORS headers ever. Also the fixed error
responses the checks in `secure/` answer with (`api/errors.py` re-exports them, so `secure/` never imports `api/`).

`SecurityHeadersMiddleware` is a pure ASGI middleware that wraps `send`, so it covers every status the app answers
(200, 204, 401, 403, 404, 405, 422). The one answer that can bypass it is a 500 made by Starlette's outermost
`ServerErrorMiddleware`, which sits outside every user middleware; `api/errors.py` adds the same headers in the
handler it registers for that case, through `apply_security_headers`.
"""

import json
from typing import Literal

from starlette.datastructures import MutableHeaders
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from shelfsync.secure.redact import redact

ErrorCode = Literal[
    "forbidden",
    "signed_out",
    "bad_token",
    "bad_ticket",
    "invalid_request",
    "internal",
    # Updates (M1b.2): 409 with one of these, 429 `too_soon`, 422 `confirm_required`
    "development_build",
    "busy",
    "no_key",
    "nothing_to_install",
    "no_previous",
    "no_backup",
    "files_changed",
    "manifest_invalid",
    "manifest_missing",
    "cannot_restart",
    "too_soon",
    "confirm_required",
]

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; "
    "connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)

SECURITY_HEADERS: tuple[tuple[str, str], ...] = (
    ("Content-Security-Policy", CONTENT_SECURITY_POLICY),
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
    ("Cross-Origin-Resource-Policy", "same-origin"),
)


def error_response(status_code: int, code: ErrorCode) -> Response:
    """A fixed JSON error body that never echoes input. It passes through `redact` like every other output."""
    body = redact(json.dumps({"error": code}, separators=(",", ":")))
    return Response(content=body, status_code=status_code, media_type="application/json")


def forbidden() -> Response:
    return error_response(403, "forbidden")


def signed_out() -> Response:
    return error_response(401, "signed_out")


def is_api_path(path: str) -> bool:
    return path == "/api" or path.startswith("/api/")


def apply_security_headers(headers: MutableHeaders, path: str) -> None:
    """Set the fixed headers (replacing any the app set), `Cache-Control: no-store` under /api, and remove any
    `Access-Control-*` header: ShelfSync sends no CORS headers."""
    for name, value in SECURITY_HEADERS:
        headers[name] = value
    if is_api_path(path):
        headers["Cache-Control"] = "no-store"
    for name in [key for key in headers if key.lower().startswith("access-control-")]:
        del headers[name]


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope["path"]

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                apply_security_headers(MutableHeaders(scope=message), path)
            await send(message)

        await self.app(scope, receive, send_with_headers)
