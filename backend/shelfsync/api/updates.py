"""The Updates API (SET-04, SYS-06): the state of updates and the three actions. No screen yet (m1b.4).

Every route sits behind the guard in `secure/middleware.py` (a session, and Origin plus `X-ShelfSync: 1` for the
POSTs), so none of them needs its own check. Answers are typed models and fixed error codes; nothing from GitHub or a
file is passed through as text.

    GET  /api/updates            the whole picture (below)
    POST /api/updates/check      202 started, 409 (development build, busy), 429 (a check ran less than 60 s ago)
    POST /api/updates/install    202 the switch started and ShelfSync is closing; 409 with a code
    POST /api/updates/rollback   202; 409 with a code; 422 `confirm_required` when the database changed and
                                 `confirm_data_loss` isn't true (the backup taken before the migration is restored,
                                 so changes made since the update are lost)
"""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from shelfsync.api.errors import ApiError, ErrorResponse
from shelfsync.update.service import (
    UpdateConflict,
    UpdateNeedsConfirmation,
    UpdateService,
    UpdateStatus,
    UpdateTooSoon,
)

UPDATES_PATH = "/api/updates"

CheckOutcome = Literal[
    "ok",
    "no_release",
    "token_refused",
    "rate_limited",
    "not_public",
    "unreachable",
    "update_refused",
    "update_failed",
]
SwitchOutcome = Literal["updated", "rolled_back", "kept_old", "not_switched", "failed"]


class LastCheckModel(BaseModel):
    at: str  # UTC, ISO 8601
    outcome: CheckOutcome
    detail: str | None  # a fixed code, for update_refused and update_failed


class AvailableModel(BaseModel):
    version: str
    ready: bool  # downloaded, signature and files verified; waits for the owner's Install


class TokenModel(BaseModel):
    set: bool
    expires_at: str | None  # UTC, ISO 8601, only when GitHub said
    notice: bool  # true from 14 days before the expiry


class ResultModel(BaseModel):
    mode: Literal["install", "rollback"]
    from_version: str
    to_version: str
    outcome: SwitchOutcome
    reason: str | None  # a fixed code
    at: str


class UpdatesResponse(BaseModel):
    development: bool  # a copy that isn't installed: updates are off
    key_available: bool  # false: this build can't verify updates, so none can be installed
    installed: str
    previous: str | None
    can_roll_back: bool
    database_changed: bool  # the update changed the database layout: a roll back restores the backup
    backup_at: str | None
    backup_available: bool
    checking: bool
    busy: bool  # a switch is under way
    last_check: LastCheckModel | None
    available: AvailableModel | None
    token: TokenModel
    last_result: ResultModel | None


class AcceptedResponse(BaseModel):
    accepted: Literal[True] = True


class RollbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm_data_loss: bool = False


def to_response(status: UpdateStatus) -> UpdatesResponse:
    last_check = status.last_check
    result = status.last_result
    return UpdatesResponse(
        development=status.development,
        key_available=status.key_available,
        installed=status.installed,
        previous=status.previous,
        can_roll_back=status.can_roll_back,
        database_changed=status.database_changed,
        backup_at=status.backup_at,
        backup_available=status.backup_available,
        checking=status.checking,
        busy=status.busy,
        last_check=(
            LastCheckModel(at=last_check.at, outcome=last_check.outcome, detail=last_check.detail)  # type: ignore[arg-type]
            if last_check is not None
            else None
        ),
        available=(
            AvailableModel(version=status.available.version, ready=status.available.ready)
            if status.available is not None
            else None
        ),
        token=TokenModel(set=status.token.is_set, expires_at=status.token.expires_at, notice=status.token.notice),
        last_result=(
            ResultModel(
                mode=result.mode,  # type: ignore[arg-type]
                from_version=result.from_version,
                to_version=result.to_version,
                outcome=result.outcome,  # type: ignore[arg-type]
                reason=result.reason,
                at=result.at,
            )
            if result is not None
            else None
        ),
    )


def _conflict(error: UpdateConflict) -> ApiError:
    return ApiError(409, error.code)  # type: ignore[arg-type]  # the service raises only codes in ErrorCode


def make_updates_router(service: UpdateService) -> APIRouter:
    router = APIRouter()

    @router.get(UPDATES_PATH, response_model=UpdatesResponse)
    def get_updates() -> UpdatesResponse:
        return to_response(service.status())

    @router.post(
        f"{UPDATES_PATH}/check",
        status_code=202,
        response_model=AcceptedResponse,
        responses={409: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
    )
    def check() -> AcceptedResponse:
        try:
            service.check_now()
        except UpdateConflict as error:
            raise _conflict(error) from None
        except UpdateTooSoon:
            raise ApiError(429, "too_soon") from None
        return AcceptedResponse()

    @router.post(
        f"{UPDATES_PATH}/install",
        status_code=202,
        response_model=AcceptedResponse,
        responses={409: {"model": ErrorResponse}},
    )
    def install() -> AcceptedResponse:
        try:
            service.install()
        except UpdateConflict as error:
            raise _conflict(error) from None
        return AcceptedResponse()

    @router.post(
        f"{UPDATES_PATH}/rollback",
        status_code=202,
        response_model=AcceptedResponse,
        responses={409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    def rollback(body: RollbackRequest | None = None) -> AcceptedResponse:
        try:
            service.rollback(body.confirm_data_loss if body is not None else False)
        except UpdateConflict as error:
            raise _conflict(error) from None
        except UpdateNeedsConfirmation:
            raise ApiError(422, "confirm_required") from None
        return AcceptedResponse()

    return router
