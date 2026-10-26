"""Security headers (06 section 2): one set on every response, and no CORS headers ever.

`SecurityHeadersMiddleware` is a pure ASGI middleware that wraps `send`, so it covers every status the app answers
(200, 204, 401, 403, 404, 405, 422). The one answer that can bypass it is a 500 made by Starlette's outermost
`ServerErrorMiddleware`, which sits outside every user middleware; `api/errors.py` adds the same headers in the
handler it registers for that case, through `apply_security_headers`.
"""

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

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
