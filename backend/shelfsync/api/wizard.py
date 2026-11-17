"""The first-run wizard's API (UI-WIZ, to the catalog step; ERR-02 is shown from `GET /api/sync`'s store reasons).

Behind the guard in `secure/middleware.py` (a session, and Origin plus `X-ShelfSync: 1` for the PUT).

    GET /api/wizard          200 WizardResponse: each step, whether it is done, and the step to start at
    PUT /api/wizard/{step}   200 WizardResponse; 409 wizard_step_from_state (that step's state comes from the data);
                             422 invalid_request (an unknown step or body). `{step}` is a step or `finished`

The steps up to the catalog are `stores`, `storage`, `test` and `catalog`; `catalog/service.py` says how each one's
"done" is decided. Only `test` is the owner's mark; the screen sets it when both tests passed, or when the owner skips
the S3 test (it costs a few requests). `PUT /api/wizard/finished` is the screen's mark on leaving the catalog step
(Lead (proposed)): from then on `current` is null whatever changes.
"""

from collections.abc import Callable
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, StrictBool

from shelfsync.api.errors import ApiError, ErrorResponse
from shelfsync.api.storage import StorageService
from shelfsync.catalog.service import WizardService, WizardState

WIZARD_PATH = "/api/wizard"
Step = Literal["stores", "storage", "test", "catalog"]
MarkPath = Literal["stores", "storage", "test", "catalog", "finished"]


class WizardStepModel(BaseModel):
    step: Step
    done: bool
    from_state: bool  # true: read from the data; false: the owner's mark


class WizardResponse(BaseModel):
    steps: list[WizardStepModel]
    current: Step | None  # the first step not done; null when every step up to the catalog is done, or finished
    finished: bool  # the owner left the catalog step (`PUT /api/wizard/finished`)


class WizardMarkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    done: StrictBool


def wizard_response(state: WizardState) -> WizardResponse:
    return WizardResponse.model_validate(
        {
            "steps": [{"step": s.step, "done": s.done, "from_state": s.from_state} for s in state.steps],
            "current": state.current,
            "finished": state.finished,
        }
    )


def storage_ready(storage: StorageService) -> Callable[[], bool]:
    """The storage step is done when the region and the bucket are saved and both key pairs are in Credential Manager
    (what the Storage Test needs, 13). Read through the Settings > Storage service; a key store that can't be read
    counts as not done."""

    def check() -> bool:
        view = storage.read()
        pairs = (view.rw.access_key_id, view.rw.secret_access_key, view.ro.access_key_id, view.ro.secret_access_key)
        return bool(view.s3_region and view.s3_bucket and all(pairs))

    return check


def make_wizard_router(service: WizardService) -> APIRouter:
    router = APIRouter()

    @router.get(WIZARD_PATH, response_model=WizardResponse)
    def get_wizard() -> WizardResponse:
        return wizard_response(service.state())

    @router.put(
        f"{WIZARD_PATH}/{{step}}",
        response_model=WizardResponse,
        responses={409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    def put_wizard(step: MarkPath, body: WizardMarkRequest) -> WizardResponse:
        try:
            state = service.mark(step, body.done)
        except ValueError:
            raise ApiError(409, "wizard_step_from_state") from None
        return wizard_response(state)

    return router
