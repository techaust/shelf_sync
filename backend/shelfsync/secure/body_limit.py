"""A request body size limit for chosen routes (SET-05, 06 section 2): a pure ASGI middleware.

Before M2.4 nothing in the app limited a request body: uvicorn has no body limit (its `h11_max_incomplete_event_size`
bounds the request line and headers only) and FastAPI reads a JSON body whole. A route that takes a big body
(`POST /api/backup/import`, a file's text up to 1 MiB) must not let a client make the app read an unbounded one first.

For each listed (method, path) the request must carry exactly one `Content-Length` of digits no larger than the limit.
A body without one (chunked), a malformed one or a bigger one is answered with the route's own fixed error before the
app sees a byte. The server itself (h11 or httptools) ends a request at its declared length, so a body longer than
declared can't reach this code through a real server; if one did (a test, another server), the app is told the client
went away, whatever it answers is dropped, and the route's own fixed error is sent. Every other route is untouched.

The guard in `secure/middleware.py` sits outside this: a request without a session never gets this far. Nothing here
reads a header value into a log: a refusal logs the method and the path only.
"""

import logging
from collections.abc import Mapping
from dataclasses import dataclass

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from shelfsync.secure.headers import ErrorCode, error_response

_log = logging.getLogger("shelfsync.security")


@dataclass(frozen=True)
class BodyLimit:
    max_bytes: int
    status: int
    code: ErrorCode


def _declared_length(headers: list[tuple[bytes, bytes]]) -> int | None:
    """The one `Content-Length`, as a number; None when there isn't exactly one or it isn't plain digits."""
    values = [value for key, value in headers if key == b"content-length"]
    if len(values) != 1 or not values[0].isdigit() or len(values[0]) > 12:
        return None
    return int(values[0])


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp, *, limits: Mapping[tuple[str, str], BodyLimit]) -> None:
        self.app = app
        self._limits = dict(limits)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        limit = self._limits.get((scope["method"], scope["path"])) if scope["type"] == "http" else None
        if limit is None:
            await self.app(scope, receive, send)
            return
        declared = _declared_length(scope["headers"])
        if declared is None or declared > limit.max_bytes:
            _log.warning("request refused by the body-size check: %s %s", scope["method"], scope["path"][:200])
            await error_response(limit.status, limit.code)(scope, receive, send)
            return
        seen = 0
        exceeded = False

        async def counted() -> Message:
            nonlocal seen, exceeded
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > limit.max_bytes:  # the server sent more than it declared: the app never sees it
                    exceeded = True
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message: Message) -> None:
            if not exceeded:
                await send(message)
            # else: whatever the app made of a cut-off body is dropped; the route's own error is sent below

        await self.app(scope, counted, guarded_send)
        if exceeded:
            _log.warning("request refused by the body-size check: %s %s", scope["method"], scope["path"][:200])
            await error_response(limit.status, limit.code)(scope, receive, send)
