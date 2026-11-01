"""The Settings > Storage API (SET-02, ERR-03): the S3 settings, the two S3 key pairs and the Storage Test.

Behind the guard in `secure/middleware.py` (a session, and Origin plus `X-ShelfSync: 1` for the writes). Request bodies
refuse unknown fields; a wrong shape is the fixed 422 `invalid_request` that never echoes the request.

    GET    /api/settings/storage   the five settings, `rw` and `ro` (each `{access_key_id, secret_access_key}` as a
                                   mask, or null when not stored) and `keys_readable` (false when Credential Manager
                                   couldn't be read: the nulls then mean "unknown", not "not set")
    PUT    /api/settings/storage   all five (required, unknown fields refused); answers what was saved
    PUT    /api/secrets/s3-rw      `{access_key_id, secret_access_key}`, always a pair; 204; 503 secrets_unavailable
    PUT    /api/secrets/s3-ro      the same, for the read-only pair
    DELETE /api/secrets/s3-rw      204 (removing what isn't there is fine); 503 secrets_unavailable
    DELETE /api/secrets/s3-ro      the same
    POST   /api/storage/test       no body; 200 StorageTestResponse, even when a step failed (`ok: false`); 409 busy,
                                   storage_not_set, keys_missing; 503 secrets_unavailable

**No response holds a key ID or a secret in full**: the masks only (`secure/credentials.py`). An empty `s3_region` or
`s3_bucket` means not set yet (no default is decided): the Storage Test needs both. The limits are in
`db/settings.py`, one place for the database and this API.

**The Test** (owner, 2026-10-26; `apply/s3.py`) writes a tiny object under `shelfsync-test/` with the read-and-write
key, reads it back with the read-only key, deletes it and confirms with a HEAD: four requests. It runs inside the
request (L1, a recorded exception to 04 section 5: bounded, one at a time, only its own test object). The settings and
keys are read once, under the storage lock, which is let go before any request is sent: a key save during a Test isn't
blocked. The settings are read strictly: an invalid stored value is `storage_not_set`, never the default (an invalid
endpoint would otherwise become "", which means AWS). No answer holds the endpoint, the bucket or a key; the object key
of a test file left behind is the one exception (`left_behind`), so the owner can delete it.
"""

import logging
import re
import sqlite3
import threading
import time
import uuid
import weakref
from collections.abc import Callable
from contextlib import closing
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Response
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StrictInt, StrictStr

from shelfsync.api.app_settings import stored_values, validators_for
from shelfsync.api.errors import ApiError, ErrorResponse
from shelfsync.apply.s3 import (
    TEST_GRACE_SECONDS,
    TEST_LIMIT_SECONDS,
    ClientFactory,
    KeyPairName,
    Reason,
    S3Client,
    S3Target,
    StepName,
    StepState,
    StorageTestOutcome,
    StorageTestProgress,
    close_quietly,
    log_outcome,
    make_client,
    run_storage_test,
)
from shelfsync.clock import to_iso, utc_now
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
    get_setting,
    set_setting,
)
from shelfsync.platform.secrets import MemorySecretStore, SecretStore, SecretStoreError
from shelfsync.secure.credentials import S3_KEY_ID, S3_SECRET, SECRETS_WRITE_LOCK, S3Credentials, S3Pair, S3Slot
from shelfsync.secure.redact import register_secret

_log = logging.getLogger("shelfsync.storage")

STORAGE_SETTINGS_PATH = "/api/settings/storage"
S3_RW_PATH = "/api/secrets/s3-rw"
S3_RO_PATH = "/api/secrets/s3-ro"
STORAGE_TEST_PATH = "/api/storage/test"
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
    keys_readable: bool  # false: Credential Manager couldn't be read, so null masks don't mean "not set"


class KeyPairRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    access_key_id: KeyId
    secret_access_key: SecretKey


class StorageTestStep(BaseModel):
    step: StepName
    key_pair: KeyPairName  # "rw": the read and write key; "ro": the read-only key
    state: StepState
    latency_ms: int | None  # null when the step didn't run, or ran out of time
    reason: Reason | None  # null when it passed or didn't run
    aws_code: str | None  # the S3 error Code only (letters, digits, dots), never its message
    http_status: int | None


class StorageTestResponse(BaseModel):
    ok: bool
    tested_at: str  # UTC, ISO 8601
    latency_ms: int
    steps: list[StorageTestStep]  # always write, read, delete, in that order
    left_behind: str | None  # the test file's key when the write passed and the delete didn't


_VALIDATORS = validators_for(StorageValues)
_TARGET_KEYS = ("s3_endpoint", "s3_region", "s3_bucket")


class StorageTestError(RuntimeError):
    """The Test stopped on an error of its own (a bug, not an answer from the storage service): a 500. Its text names
    only the kind of error, never the error's own text, which can hold the endpoint."""

    def __init__(self, kind: str) -> None:
        super().__init__(f"The storage test stopped ({kind})")


class StorageService:
    """What the routes and start-up talk to. `connect` opens a connection to the database (one per call, closed
    after); `secrets` is Credential Manager (a fake in tests)."""

    def __init__(
        self,
        connect: Callable[[], sqlite3.Connection],
        secrets: SecretStore,
        *,
        client_factory: ClientFactory = make_client,
        monotonic: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = utc_now,
        limit_seconds: float = TEST_LIMIT_SECONDS,
        grace_seconds: float = TEST_GRACE_SECONDS,
    ) -> None:
        self._connect = connect
        self._credentials = S3Credentials(secrets)
        self._lock = SECRETS_WRITE_LOCK  # one secrets write at a time, in the whole process (see `credentials.py`)
        self._keeper: sqlite3.Connection | None = None  # holds a development database's memory open
        # The Storage Test: its seams (real by default), and the flag that lets one run at a time.
        self._client_factory = client_factory
        self._monotonic = monotonic
        self._now = now
        self._limit_seconds = limit_seconds  # the whole Test
        self._grace_seconds = grace_seconds  # how long past the limit the request waits for the worker to report
        self._testing = False
        self._testing_lock = threading.Lock()

    @classmethod
    def development(cls, secrets: SecretStore | None = None, **seams: Any) -> StorageService:
        """Settings in memory and, by default, an in-memory secret store: no test reaches a file or Credential Manager
        by accident."""
        uri = f"file:shelfsync-storage-{uuid.uuid4().hex}?mode=memory&cache=shared"

        def connect() -> sqlite3.Connection:
            return sqlite3.connect(uri, uri=True, isolation_level=None, check_same_thread=False)

        keeper = connect()
        migrate(keeper)
        service = cls(connect, secrets if secrets is not None else MemorySecretStore(), **seams)
        service._keeper = keeper
        weakref.finalize(service, keeper.close)
        return service

    @property
    def lock(self) -> threading.RLock:
        """The one lock every storage write holds (settings saves and key writes). The backup import (`api/backup.py`)
        takes it too, so it can't interleave with a key write."""
        return self._lock

    def register_secrets(self) -> None:
        """Start-up: every stored key goes into the log redaction. A failure only warns."""
        self._credentials.register_all()

    def read(self) -> StorageResponse:
        connection = self._connect()
        try:
            values = stored_values(connection, _VALIDATORS, _KEYS)
        finally:
            connection.close()
        rw_id, rw_secret, rw_readable = self._credentials.masks("rw")
        ro_id, ro_secret, ro_readable = self._credentials.masks("ro")
        return StorageResponse(
            **values,
            rw=KeyMasks(access_key_id=rw_id, secret_access_key=rw_secret),
            ro=KeyMasks(access_key_id=ro_id, secret_access_key=ro_secret),
            keys_readable=rw_readable and ro_readable,
        )

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

    # ---- the Storage Test ------------------------------------------------------------------------------------------

    def test(self) -> tuple[StorageTestOutcome, str]:
        """Run the Test; answer the outcome and when it ran (UTC, ISO 8601). One at a time (`busy`).

        The Test runs on a worker thread and this waits at most the limit plus a short grace: botocore's timeouts are
        per socket operation and per attempt, so a slow service could otherwise hold the request far longer. On overrun
        the running step is `timeout` and later ones `not_run`; the worker skips the read but still deletes a written
        test file, logs what it did, and only then lets the next Test start."""
        self._claim_test()
        handed_over = False
        completed = False
        overrun = {"yes": False}
        finished = threading.Event()
        try:
            target, rw_pair, ro_pair = self._snapshot()
            gave_up = threading.Event()
            progress = StorageTestProgress()
            result: dict[str, Any] = {}
            start = self._monotonic()
            deadline = start + self._limit_seconds

            def abandoned() -> bool:
                return gave_up.is_set() or self._monotonic() >= deadline

            def work() -> None:
                rw: S3Client | None = None
                ro: S3Client | None = None
                try:
                    rw = self._client_factory(target, rw_pair)
                    ro = self._client_factory(target, ro_pair)
                    outcome = run_storage_test(
                        rw,
                        ro,
                        target.bucket,
                        monotonic=self._monotonic,
                        now=self._now,
                        abandoned=abandoned,
                        progress=progress,
                    )
                    result["outcome"] = outcome
                    log_outcome(outcome, late=gave_up.is_set())
                except BaseException as error:  # handed to the request below, never lost in the thread
                    result["error"] = error
                    _log.warning("The storage test stopped (%s)", type(error).__name__)
                finally:
                    close_quietly(rw)
                    close_quietly(ro)
                    with self._testing_lock:
                        finished.set()
                        if overrun["yes"]:  # the request gave up waiting: only now may another Test start
                            self._testing = False

            threading.Thread(target=work, name="storage-test", daemon=True).start()
            handed_over = True
            completed = finished.wait(self._limit_seconds + self._grace_seconds)
            if completed:
                if "error" in result:  # a fixed text: botocore's own can hold the endpoint (`Invalid endpoint: ...`)
                    raise StorageTestError(type(result["error"]).__name__) from None
                answer: StorageTestOutcome = result["outcome"]
            else:
                gave_up.set()
                answer = progress.overrun(max(0, round((self._monotonic() - start) * 1000)))
                _log.warning("The storage test ran out of time")
            return answer, to_iso(self._now())
        finally:
            if not handed_over or completed:
                self._release_test()
            else:  # no answer in time: the worker lets go when it ends (or has, in the meantime)
                with self._testing_lock:
                    if finished.is_set():
                        self._testing = False
                    else:
                        overrun["yes"] = True

    def _claim_test(self) -> None:
        with self._testing_lock:
            if self._testing:
                raise ApiError(409, "busy")
            self._testing = True

    def _release_test(self) -> None:
        with self._testing_lock:
            self._testing = False

    def _snapshot(self) -> tuple[S3Target, S3Pair, S3Pair]:
        """The three settings and both key pairs, read once under the storage lock (let go before any request). Every
        key value read is registered with the log redaction at once."""
        with self._lock:
            try:
                with closing(self._connect()) as connection:
                    raw = [get_setting(connection, key) for key in _TARGET_KEYS]
            except ValueError:  # a hand-edited value that isn't JSON
                raw = [None, None, None]
            try:
                rw_id, rw_secret = self._credentials.read("rw")
                ro_id, ro_secret = self._credentials.read("ro")
            except SecretStoreError as error:
                _log.warning("The S3 keys couldn't be read for the storage test (%s)", type(error).__name__)
                raise ApiError(503, "secrets_unavailable") from None
        for value in (rw_id, rw_secret, ro_id, ro_secret):
            if value is not None:
                register_secret(value)
        target = _strict_target(raw)
        if rw_id is None or rw_secret is None or ro_id is None or ro_secret is None:
            raise ApiError(409, "keys_missing")
        return target, S3Pair(rw_id, rw_secret), S3Pair(ro_id, ro_secret)


def _strict_target(raw: list[Any]) -> S3Target:
    """The stored endpoint, region and bucket, or 409 `storage_not_set`: an empty region or bucket, or any stored value
    the save rules would refuse. Never the default in place of an invalid value (L11)."""
    endpoint, region, bucket = raw
    if not (isinstance(endpoint, str) and isinstance(region, str) and isinstance(bucket, str)):
        raise ApiError(409, "storage_not_set")
    try:
        check_s3_endpoint(endpoint)
        check_s3_region(region)
        check_s3_bucket(bucket)
    except ValueError:
        raise ApiError(409, "storage_not_set") from None
    if region == "" or bucket == "":
        raise ApiError(409, "storage_not_set")
    return S3Target(endpoint or None, region, bucket)


def storage_test_response(outcome: StorageTestOutcome, tested_at: str) -> StorageTestResponse:
    return StorageTestResponse(
        ok=outcome.ok,
        tested_at=tested_at,
        latency_ms=outcome.latency_ms,
        steps=[
            StorageTestStep(
                step=step.step,
                key_pair=step.key_pair,
                state=step.state,
                latency_ms=step.latency_ms,
                reason=step.reason,
                aws_code=step.aws_code,
                http_status=step.http_status,
            )
            for step in outcome.steps
        ],
        left_behind=outcome.left_behind,
    )


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

    test_errors: dict[int | str, dict[str, Any]] = {409: {"model": ErrorResponse}, 503: {"model": ErrorResponse}}

    @router.post(STORAGE_TEST_PATH, response_model=StorageTestResponse, responses=test_errors)
    def test_storage() -> StorageTestResponse:
        return storage_test_response(*service.test())

    return router


__all__ = [
    "S3_RO_PATH",
    "S3_RW_PATH",
    "STORAGE_SETTINGS_PATH",
    "STORAGE_TEST_PATH",
    "StorageService",
    "StorageTestError",
    "StorageTestResponse",
    "StorageTestStep",
    "build_storage_service",
    "make_storage_router",
]
