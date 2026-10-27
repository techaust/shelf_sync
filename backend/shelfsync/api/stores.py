"""The Stores API (SET-01, ERR-01): add, edit, pause, remove, the key pair and the read-only Test connection.

Every route sits behind the guard in `secure/middleware.py` (a session, and Origin plus `X-ShelfSync: 1` for the
writes). Request bodies refuse unknown fields; a wrong shape is the fixed 422 `invalid_request` body that never echoes
the request. **No response holds a consumer key or secret**: only the masks (`ck_` and the last four characters).

    GET    /api/stores              {stores: [Store]}
    POST   /api/stores              201 Store; 409 store_exists, code_taken; 503 secrets_unavailable
    PATCH  /api/stores/{id}         200 Store; 404 not_found; 409 store_exists, code_taken; 422 keys_required (a host
                                    change needs `consumer_key` and `consumer_secret` in the same request)
    PUT    /api/stores/{id}/keys    204; the health goes back to `unknown`
    DELETE /api/stores/{id}         204; 503 secrets_unavailable (the entries couldn't be deleted: nothing changed)
    POST   /api/stores/{id}/test    200 StoreTestResponse (a failed test is still a 200 with `ok: false`); 409 busy,
                                    keys_missing; 404 not_found

`color` is a palette key, `indigo` (GF's pair) or `teal` (PW's pair) from 05 section 2.3; the table's CHECK limits
it to these, so a new key needs a migration as well as this Literal and the frontend's palette, which maps each key to
its light and dark colours (`frontend/src/styles/storePalette.ts`). A store id is 1 to
2**63 - 1 (SQLite's integers are 64-bit), so a huge one is a 422, never a 500.
"""

import logging
from typing import Annotated, Any, Literal, Self

from fastapi import APIRouter, Path, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from shelfsync.api.errors import ApiError, ErrorResponse
from shelfsync.db.stores import StoreRow
from shelfsync.store_service import StoreError, StoreService, StoreView, normalize_url

_log = logging.getLogger("shelfsync.stores")

STORES_PATH = "/api/stores"

Shape = Literal["circle", "square", "triangle", "diamond"]
HealthState = Literal["unknown", "connected", "unreachable", "refused"]
Name = Annotated[str, Field(min_length=1, max_length=60)]
Button = Annotated[str, Field(min_length=1, max_length=40)]
Code = Annotated[str, Field(pattern=r"^[A-Z]{2}$")]
Color = Literal["indigo", "teal"]
Spacing = Annotated[int, Field(strict=True, ge=50, le=5000)]
StoreId = Annotated[int, Path(ge=1, le=2**63 - 1)]
ConsumerKey = Annotated[str, Field(pattern=r"^ck_[A-Za-z0-9]{20,64}$")]
ConsumerSecret = Annotated[str, Field(pattern=r"^cs_[A-Za-z0-9]{20,64}$")]


def _text(value: str, longest: int) -> str:
    """Trimmed, with no control character or line break, and still 1 to `longest` characters after the trim."""
    text = value.strip()
    if not text.isprintable() or not 1 <= len(text) <= longest:
        raise ValueError("not an acceptable text")
    return text


class StoreFields(BaseModel):
    """What POST and PATCH share: the same limits and the same checks."""

    model_config = ConfigDict(extra="forbid")

    @field_validator("name", check_fields=False)
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        return None if value is None else _text(value, 60)

    @field_validator("main_button", check_fields=False)
    @classmethod
    def _button(cls, value: str | None) -> str | None:
        return None if value is None else _text(value, 40)

    @field_validator("url", check_fields=False)
    @classmethod
    def _normalised(cls, value: str | None) -> str | None:
        return None if value is None else normalize_url(value)


class CreateStoreRequest(StoreFields):
    name: Name
    url: Annotated[str, Field(max_length=200)]
    code: Code
    shape: Shape
    color: Color
    spacing_ms: Spacing = 150
    main_button: Button = "Download"
    consumer_key: ConsumerKey
    consumer_secret: ConsumerSecret


class UpdateStoreRequest(StoreFields):
    """Any subset of the fields. A field that is present must have a value (null is refused)."""

    name: Name | None = None
    url: Annotated[str, Field(max_length=200)] | None = None
    code: Code | None = None
    shape: Shape | None = None
    color: Color | None = None
    spacing_ms: Spacing | None = None
    main_button: Button | None = None
    state: Literal["active", "paused"] | None = None
    consumer_key: ConsumerKey | None = None
    consumer_secret: ConsumerSecret | None = None

    @model_validator(mode="after")
    def _present_means_set(self) -> Self:
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError("null is not a value")
        if (self.consumer_key is None) != (self.consumer_secret is None):
            raise ValueError("the keys are a pair")
        return self


class KeysRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    consumer_key: ConsumerKey
    consumer_secret: ConsumerSecret


class KeysModel(BaseModel):
    consumer_key: str | None  # masked
    consumer_secret: str | None  # masked


class HealthModel(BaseModel):
    state: HealthState
    reason: str | None
    http_status: int | None
    latency_ms: int | None
    wc_version: str | None
    wp_version: str | None
    downloadable_count: int | None
    tested_at: str | None  # UTC, ISO 8601


class StoreModel(BaseModel):
    id: int
    name: str
    url: str
    code: str
    shape: Shape
    color: Color
    spacing_ms: int
    main_button: str
    state: Literal["active", "paused"]
    keys: KeysModel
    health: HealthModel


class StoresResponse(BaseModel):
    stores: list[StoreModel]


class StoreTestResponse(BaseModel):
    ok: bool
    state: HealthState
    reason: str | None
    http_status: int | None
    latency_ms: int | None
    wc_version: str | None
    wp_version: str | None
    downloadable_count: int | None
    tested_at: str
    detail: str | None  # the host a redirect named, `redirected` only
    warning: str | None  # `no_downloadable_products`


DEFAULT_COLOR: Color = "indigo"


def _color(row: StoreRow) -> Color:
    """The stored key, or the default (with a warning) for any other value, so a list never fails on one row. The
    table's CHECK allows only the two keys, so widening the palette needs a migration as well as a new key here."""
    if row.color == "indigo":
        return "indigo"
    if row.color == "teal":
        return "teal"
    _log.warning("Store %s has an unknown colour key; showing the default", row.code)
    return DEFAULT_COLOR


def to_model(view: StoreView) -> StoreModel:
    row: StoreRow = view.row
    return StoreModel(
        id=row.id,
        name=row.name,
        url=row.url,
        code=row.code,
        shape=row.shape,  # type: ignore[arg-type]  # the table's CHECK allows only these
        color=_color(row),
        spacing_ms=row.spacing_ms,
        main_button=row.main_button,
        state=row.state,  # type: ignore[arg-type]
        keys=KeysModel(consumer_key=view.consumer_key, consumer_secret=view.consumer_secret),
        health=HealthModel(
            state=row.health,  # type: ignore[arg-type]
            reason=row.health_reason,
            http_status=row.http_status,
            latency_ms=row.latency_ms,
            wc_version=row.wc_version,
            wp_version=row.wp_version,
            downloadable_count=row.downloadable_count,
            tested_at=row.tested_at,
        ),
    )


def _error(error: StoreError) -> ApiError:
    return ApiError(error.status, error.code)


_ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
}


def make_stores_router(service: StoreService) -> APIRouter:
    router = APIRouter()

    @router.get(STORES_PATH, response_model=StoresResponse)
    def list_stores() -> StoresResponse:
        return StoresResponse(stores=[to_model(view) for view in service.list()])

    @router.post(STORES_PATH, status_code=201, response_model=StoreModel, responses=_ERRORS)
    def create_store(body: CreateStoreRequest) -> StoreModel:
        try:
            view = service.create(**body.model_dump())
        except StoreError as error:
            raise _error(error) from None
        return to_model(view)

    @router.patch(f"{STORES_PATH}/{{store_id}}", response_model=StoreModel, responses=_ERRORS)
    def update_store(store_id: StoreId, body: UpdateStoreRequest) -> StoreModel:
        fields = body.model_dump(exclude_unset=True)
        key = fields.pop("consumer_key", None)
        secret = fields.pop("consumer_secret", None)
        try:
            view = service.update(store_id, fields, (key, secret) if key is not None and secret is not None else None)
        except StoreError as error:
            raise _error(error) from None
        return to_model(view)

    @router.put(f"{STORES_PATH}/{{store_id}}/keys", status_code=204, responses=_ERRORS)
    def put_keys(store_id: StoreId, body: KeysRequest) -> Response:
        try:
            service.set_keys(store_id, body.consumer_key, body.consumer_secret)
        except StoreError as error:
            raise _error(error) from None
        return Response(status_code=204)

    @router.delete(f"{STORES_PATH}/{{store_id}}", status_code=204, responses=_ERRORS)
    def delete_store(store_id: StoreId) -> Response:
        try:
            service.delete(store_id)
        except StoreError as error:
            raise _error(error) from None
        return Response(status_code=204)

    @router.post(f"{STORES_PATH}/{{store_id}}/test", response_model=StoreTestResponse, responses=_ERRORS)
    def test_store(store_id: StoreId) -> StoreTestResponse:
        try:
            report = service.test(store_id)
        except StoreError as error:
            raise _error(error) from None
        outcome = report.outcome
        return StoreTestResponse(
            ok=outcome.ok,
            state=outcome.health,  # type: ignore[arg-type]
            reason=outcome.reason,
            http_status=outcome.http_status,
            latency_ms=outcome.latency_ms,
            wc_version=outcome.wc_version,
            wp_version=outcome.wp_version,
            downloadable_count=outcome.downloadable_count,
            tested_at=report.tested_at,
            detail=outcome.detail,
            warning=outcome.warning,
        )

    return router
