"""Error bodies (06 section 3): fixed JSON that never echoes what the caller sent.

Every body passes through `redact`, which on these fixed texts changes nothing; it is there so that a later,
less fixed body can't skip it.
"""

from typing import cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from starlette.responses import Response

from shelfsync.secure.headers import ErrorCode, apply_security_headers, error_response, forbidden, signed_out


class ErrorResponse(BaseModel):
    error: ErrorCode


class ApiError(Exception):
    """Raised by a route to answer with a fixed error body."""

    def __init__(self, status_code: int, code: ErrorCode) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code: ErrorCode = code


async def _api_error(request: Request, exc: Exception) -> Response:
    api_error = cast("ApiError", exc)  # registered for ApiError only
    return error_response(api_error.status_code, api_error.code)


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


__all__ = [
    "ApiError",
    "ErrorCode",
    "ErrorResponse",
    "error_response",
    "forbidden",
    "register_error_handlers",
    "signed_out",
]


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(RequestValidationError, _invalid_request)
    app.add_exception_handler(Exception, _internal_error)
