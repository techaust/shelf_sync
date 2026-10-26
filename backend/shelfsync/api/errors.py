"""Error bodies (06 section 3): fixed JSON that never echoes what the caller sent.

Every body passes through `redact`, which on these fixed texts changes nothing; it is there so that a later,
less fixed body can't skip it.
"""

import json
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from starlette.responses import Response

from shelfsync.secure.headers import apply_security_headers
from shelfsync.secure.redact import redact

ErrorCode = Literal["forbidden", "signed_out", "bad_token", "bad_ticket", "invalid_request", "internal"]


class ErrorResponse(BaseModel):
    error: ErrorCode


class ApiError(Exception):
    """Raised by a route to answer with a fixed error body."""

    def __init__(self, status_code: int, code: ErrorCode) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code: ErrorCode = code


def error_response(status_code: int, code: ErrorCode) -> Response:
    body = redact(json.dumps({"error": code}, separators=(",", ":")))
    return Response(content=body, status_code=status_code, media_type="application/json")


def forbidden() -> Response:
    return error_response(403, "forbidden")


def signed_out() -> Response:
    return error_response(401, "signed_out")


async def _api_error(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, ApiError)
    return error_response(exc.status_code, exc.code)


async def _invalid_request(request: Request, exc: Exception) -> Response:
    # FastAPI's default 422 body lists each error with the `input` that failed, which would echo the request.
    return error_response(422, "invalid_request")


async def _internal_error(request: Request, exc: Exception) -> Response:
    # No traceback in the body; the traceback goes to the log through uvicorn's own error record (redacted there).
    # This 500 is made by Starlette's outermost ServerErrorMiddleware, outside our middleware, so it gets the
    # security headers here.
    response = error_response(500, "internal")
    apply_security_headers(response.headers, request.scope["path"])
    return response


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(RequestValidationError, _invalid_request)
    app.add_exception_handler(Exception, _internal_error)
