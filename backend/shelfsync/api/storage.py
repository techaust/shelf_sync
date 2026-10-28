"""The Settings > Storage API (SET-02): the S3 settings and the two S3 key pairs. **No Test route yet** (needs boto3).

Behind the guard in `secure/middleware.py` (a session, and Origin plus `X-ShelfSync: 1` for the writes). Request bodies
refuse unknown fields; a wrong shape is the fixed 422 `invalid_request` that never echoes the request.

    GET    /api/settings/storage   the five settings, and `rw` and `ro`: each `{access_key_id, secret_access_key}` as a
                                   mask, or null when not stored
    PUT    /api/settings/storage   all five (required, unknown fields refused); answers what was saved
    PUT    /api/secrets/s3-rw      `{access_key_id, secret_access_key}`, always a pair; 204; 503 secrets_unavailable
    PUT    /api/secrets/s3-ro      the same, for the read-only pair
    DELETE /api/secrets/s3-rw      204 (removing what isn't there is fine); 503 secrets_unavailable
    DELETE /api/secrets/s3-ro      the same

**No response holds a key ID or a secret in full**: the masks only (`secure/credentials.py`). An empty `s3_region` or
`s3_bucket` means not set yet (no default is decided): the Storage Test of M2.7 needs both. The limits are in
`db/settings.py`, one place for the database and this API.
"""

import re
import sqlite3
import threading
import uuid
import weakref
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Response
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StrictInt, StrictStr

from shelfsync.api.app_settings import stored_values, validators_for
from shelfsync.api.errors import ApiError, ErrorResponse
from shelfsync.db.migrate import migrate
from shelfsync.db.settings import (
    KEEP_PREVIOUS_MAX,
    KEEP_PREVIOUS_MIN,
    LINK_TEMPLATE_MAX,
    S3_ENDPOINT_MAX,
    check_link_template,
    check_s3_bucket,
    check_s3_endpoint,
    check_s3_region,
    set_setting,
)
from shelfsync.platform.secrets import MemorySecretStore, SecretStore, SecretStoreError
from shelfsync.secure.credentials import S3_KEY_ID, S3_SECRET, S3Credentials, S3Slot

STORAGE_SETTINGS_PATH = "/api/settings/storage"
S3_RW_PATH = "/api/secrets/s3-rw"
S3_RO_PATH = "/api/secrets/s3-ro"
_KEYS = ("s3_endpoint", "s3_region", "s3_bucket", "keep_previous_files", "download_link_template")


def _rule(check: Callable[[str], None]) -> AfterValidator:
    def run(value: str) -> str:
        check(value)
        return value

    return AfterValidator(run)


def _matches(pattern: re.Pattern[str]) -> AfterValidator:
    def run(value: str) -> str:
        if pattern.fullmatch(value) is None:
            raise ValueError("not an acceptable key")
        return value

    return AfterValidator(run)


# Strict strings (a number is never an endpoint), a length cap first so a huge body is refused cheaply, then the same
# rule the database applies.
Endpoint = Annotated[StrictStr, Field(max_length=S3_ENDPOINT_MAX), _rule(check_s3_endpoint)]
Region = Annotated[StrictStr, Field(max_length=32), _rule(check_s3_region)]
Bucket = Annotated[StrictStr, Field(max_length=63), _rule(check_s3_bucket)]
LinkTemplate = Annotated[StrictStr, Field(max_length=LINK_TEMPLATE_MAX), _rule(check_link_template)]
KeyId = Annotated[StrictStr, Field(max_length=128), _matches(S3_KEY_ID)]
SecretKey = Annotated[StrictStr, Field(max_length=128), _matches(S3_SECRET)]


class StorageValues(BaseModel):
    """The five settings. Strict types, so `true` is never a count and `7` is never a bucket."""

    model_config = ConfigDict(extra="forbid")
    s3_endpoint: Endpoint
    s3_region: Region
    s3_bucket: Bucket
    keep_previous_files: StrictInt = Field(ge=KEEP_PREVIOUS_MIN, le=KEEP_PREVIOUS_MAX)
    download_link_template: LinkTemplate


class KeyMasks(BaseModel):
    access_key_id: str | None
    secret_access_key: str | None


class StorageResponse(StorageValues):
    rw: KeyMasks
    ro: KeyMasks


class KeyPairRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    access_key_id: KeyId
    secret_access_key: SecretKey


_VALIDATORS = validators_for(StorageValues)


class StorageService:
    """What the routes and start-up talk to. `connect` opens a connection to the database (one per call, closed
    after); `secrets` is Credential Manager (a fake in tests)."""

    def __init__(self, connect: Callable[[], sqlite3.Connection], secrets: SecretStore) -> None:
        self._connect = connect
        self._credentials = S3Credentials(secrets)
        self._lock = threading.Lock()  # one write at a time
        self._keeper: sqlite3.Connection | None = None  # holds a development database's memory open

    @classmethod
    def development(cls, secrets: SecretStore | None = None) -> StorageService:
        """Settings in memory and, by default, an in-memory secret store: no test reaches a file or Credential Manager
        by accident."""
        uri = f"file:shelfsync-storage-{uuid.uuid4().hex}?mode=memory&cache=shared"

        def connect() -> sqlite3.Connection:
            return sqlite3.connect(uri, uri=True, isolation_level=None, check_same_thread=False)

        keeper = connect()
        migrate(keeper)
        service = cls(connect, secrets if secrets is not None else MemorySecretStore())
        service._keeper = keeper
        weakref.finalize(service, keeper.close)
        return service

    def register_secrets(self) -> None:
        """Start-up: every stored key goes into the log redaction. A failure only warns."""
        self._credentials.register_all()

    def read(self) -> StorageResponse:
        connection = self._connect()
        try:
            values = stored_values(connection, _VALIDATORS, _KEYS)
        finally:
            connection.close()
        return StorageResponse(**values, rw=self._masks("rw"), ro=self._masks("ro"))

    def _masks(self, slot: S3Slot) -> KeyMasks:
        key_id, secret = self._credentials.masked(slot)
        return KeyMasks(access_key_id=key_id, secret_access_key=secret)

    def save(self, new: StorageValues) -> StorageValues:
        with self._lock:
            connection = self._connect()
            try:
                connection.execute("BEGIN IMMEDIATE")  # all five or none
                try:
                    for key in _KEYS:
                        set_setting(connection, key, getattr(new, key))
                    connection.execute("COMMIT")
                except BaseException:
                    connection.execute("ROLLBACK")
                    raise
            finally:
                connection.close()
        return StorageValues(**new.model_dump())

    def set_keys(self, slot: S3Slot, key_id: str, secret: str) -> None:
        with self._lock:
            try:
                self._credentials.save(slot, key_id, secret)
            except SecretStoreError:
                raise ApiError(503, "secrets_unavailable") from None

    def delete_keys(self, slot: S3Slot) -> None:
        with self._lock:
            try:
                self._credentials.delete(slot)
            except SecretStoreError:
                raise ApiError(503, "secrets_unavailable") from None


def build_storage_service(connect: Callable[[], sqlite3.Connection], secrets: SecretStore) -> StorageService:
    """The service the running app uses: the data folder's database and Credential Manager."""
    return StorageService(connect, secrets)


def make_storage_router(service: StorageService) -> APIRouter:
    router = APIRouter()

    @router.get(STORAGE_SETTINGS_PATH, response_model=StorageResponse)
    def get_storage() -> StorageResponse:
        return service.read()

    @router.put(STORAGE_SETTINGS_PATH, response_model=StorageValues, responses={422: {"model": ErrorResponse}})
    def put_storage(body: StorageValues) -> StorageValues:
        return service.save(body)

    errors: dict[int | str, dict[str, Any]] = {422: {"model": ErrorResponse}, 503: {"model": ErrorResponse}}

    def add_slot(slot: S3Slot, path: str) -> None:
        @router.put(path, status_code=204, responses=errors, name=f"put_s3_{slot}")
        def put_keys(body: KeyPairRequest) -> Response:
            service.set_keys(slot, body.access_key_id, body.secret_access_key)
            return Response(status_code=204)

        @router.delete(path, status_code=204, responses=errors, name=f"delete_s3_{slot}")
        def delete_keys() -> Response:
            service.delete_keys(slot)
            return Response(status_code=204)

    add_slot("rw", S3_RW_PATH)
    add_slot("ro", S3_RO_PATH)
    return router


__all__ = [
    "S3_RO_PATH",
    "S3_RW_PATH",
    "STORAGE_SETTINGS_PATH",
    "StorageService",
    "build_storage_service",
    "make_storage_router",
]
