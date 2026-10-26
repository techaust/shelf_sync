"""Sign-in routes (SYS-03, SET-06 logic): ticket, session, session status, reset token. The checks that come before
these routes (Host, Origin, X-ShelfSync, session) are in `secure/middleware.py`; the table is
docs/runs/m1a.2-security.md item 11.
"""

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from shelfsync.api.errors import ApiError, ErrorResponse
from shelfsync.secure.middleware import RESET_TOKEN_PATH, SESSION_COOKIE, SIGN_IN_PATH, TICKET_PATH
from shelfsync.secure.sessions import TICKET_LIFETIME_SECONDS, SessionStore
from shelfsync.secure.token import InstallToken

# "Is this tab signed in?" for the page (a refresh, a second tab). A normal route: it is not in
# SESSION_EXEMPT_PATHS, so the guard answers 401 "signed_out" before it runs when the cookie is missing or stale.
SESSION_STATUS_PATH = "/api/session/status"


class TicketResponse(BaseModel):
    ticket: str
    expires_in: int


class SignInRequest(BaseModel):
    ticket: str


def _bearer_token(request: Request) -> str | None:
    """The token from `Authorization: Bearer <token>`: one header, the scheme in any case, one token, nothing else."""
    values = request.headers.getlist("authorization")
    if len(values) != 1:
        return None
    parts = values[0].split(" ")
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        return None
    return parts[1]


def make_session_router(sessions: SessionStore, install_token: InstallToken) -> APIRouter:
    router = APIRouter()

    @router.post(TICKET_PATH, response_model=TicketResponse, responses={401: {"model": ErrorResponse}})
    def issue_ticket(request: Request) -> TicketResponse:
        # Called by the launcher (a program, not a browser): no session, no Origin (the middleware refuses any),
        # no X-ShelfSync. The install token is accepted only here, only in this header.
        presented = _bearer_token(request)
        # The check and the ticket happen under one lock, so a Reset access token can't fall between them.
        ticket = None if presented is None else install_token.run_if_matches(presented, sessions.issue_ticket)
        if ticket is None:
            raise ApiError(401, "bad_token")
        # Cache-Control: no-store comes from SecurityHeadersMiddleware (every /api response)
        return TicketResponse(ticket=ticket, expires_in=int(TICKET_LIFETIME_SECONDS))

    @router.post(SIGN_IN_PATH, status_code=204, responses={401: {"model": ErrorResponse}})
    def sign_in(body: SignInRequest) -> Response:
        session_id = sessions.redeem_ticket(body.ticket)
        if session_id is None:
            raise ApiError(401, "bad_ticket")
        response = Response(status_code=204)
        # No Domain, Expires, Max-Age or Secure: a host-only cookie that ends with the browser session. (Secure
        # would stop it being sent over http://127.0.0.1 in some browsers; the address is never https.)
        response.set_cookie(SESSION_COOKIE, session_id, httponly=True, samesite="strict", path="/")
        return response

    @router.get(SESSION_STATUS_PATH, status_code=204, responses={401: {"model": ErrorResponse}})
    def session_status() -> Response:
        # Reached only with a valid session (the guard refuses everything else), so reaching it is the answer.
        return Response(status_code=204)

    @router.post(RESET_TOKEN_PATH, status_code=204)
    def reset_token() -> Response:
        # New token and end of every session under one lock. If the store fails this raises, nothing changes and the
        # app answers 500.
        install_token.reset(then=sessions.end_all)
        response = Response(status_code=204)
        response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="strict")
        return response

    return router
