"""The GitHub token setting (SET-04, 06 section 3): write-only.

`PUT` stores a fine-grained token (`github_pat_` and 20 to 255 more letters, digits and underscores) in Credential
Manager and registers it with the log redaction; `DELETE` removes it; `GET` says only whether one is set and when it
expires, if GitHub told us. **The token is never in any response**, masked or not, and a wrong shape is refused with
the fixed 422 body that never echoes the request. The token is optional: while the repository is public, updates are
checked without it.

`GITHUB_TOKEN_ENTRY` is the Credential Manager entry's name. m1b.1 lists ShelfSync's entries for "Remove my data" in
`platform/secrets.py` (`OWNED_SECRET_NAMES`, not on this branch); the lead keeps the two names equal at integration.
"""

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict, Field

from shelfsync.api.errors import ApiError, ErrorResponse
from shelfsync.update.service import GITHUB_TOKEN_ENTRY, InvalidToken, UpdateService

GITHUB_TOKEN_PATH = "/api/secrets/github-token"  # a URL path, not a secret  # nosec B105

__all__ = ["GITHUB_TOKEN_ENTRY", "GITHUB_TOKEN_PATH", "make_secrets_router"]


class GithubTokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str = Field(max_length=300)


class GithubTokenStatus(BaseModel):
    set: bool
    expires_at: str | None


def make_secrets_router(service: UpdateService) -> APIRouter:
    router = APIRouter()

    @router.get(GITHUB_TOKEN_PATH, response_model=GithubTokenStatus)
    def get_token() -> GithubTokenStatus:
        status = service.token_status()
        return GithubTokenStatus(set=status.is_set, expires_at=status.expires_at)

    @router.put(GITHUB_TOKEN_PATH, status_code=204, responses={422: {"model": ErrorResponse}})
    def put_token(body: GithubTokenRequest) -> Response:
        try:
            service.set_token(body.value)
        except InvalidToken:
            raise ApiError(422, "invalid_request") from None
        return Response(status_code=204)

    @router.delete(GITHUB_TOKEN_PATH, status_code=204)
    def delete_token() -> Response:
        service.delete_token()
        return Response(status_code=204)

    return router
