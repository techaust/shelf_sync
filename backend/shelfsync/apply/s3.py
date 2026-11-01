"""The S3 client and the Storage Test (SET-02, ERR-03; 04 section 5, 06 sections 3 and 5).

Rules this module keeps:
- **Isolated from the PC's environment** (L9). Without it botocore sends signed requests wherever the environment tells
  it to: `AWS_ENDPOINT_URL*` and `~/.aws/config` replace an empty endpoint, `HTTPS_PROXY` and the Windows proxy are
  used when no proxies are given, `AWS_CA_BUNDLE`/`REQUESTS_CA_BUNDLE` replace TLS trust, an `AWS_PROFILE` naming a
  missing profile makes the client fail to build, and `~/.aws/models` can replace S3's service model. So each client
  is built from a fresh botocore Session whose profile and config files are switched off, whose service models come
  only from botocore's own data folder, with explicit keys, region, `verify=True`, no proxy and every `Config` value
  set (`_config`).
- **Lazy import** (L10): botocore is imported inside the factory and `classify`, so starting the app doesn't load it
  (NFR-3); types are under `TYPE_CHECKING`.
- **No public put or delete that takes a caller's key.** The only writes are the Test's, on the key the Test made
  (`shelfsync-test/...`, which can't collide with a real `<slug>-<version>.zip` at the bucket root, CAT-04; APL-07).
- **Nothing from an S3 answer is passed on as text except the error Code**, and only when it matches
  `^[A-Za-z0-9.]{1,64}$` and isn't a registered secret (`safe_aws_code`; L4). Never the Message: it can hold the
  account ID and ARNs. Logs hold the step, reason, code, status and time; never `str(error)` (an
  `EndpointConnectionError` names the URL), the endpoint, the bucket or the object key.

`run_storage_test` is the Test of Settings > Storage: write a tiny object with the read-and-write key, read it back
with the read-only key, delete it with the read-and-write key and confirm with a HEAD that answers 404 (L3). A passed
write is always followed by the delete, even when the read failed (L2).
"""

import base64
import hashlib
import logging
import re
import secrets
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol

from shelfsync.secure.credentials import S3Pair
from shelfsync.secure.redact import redact

if TYPE_CHECKING:
    from botocore.config import Config

_log = logging.getLogger("shelfsync.storage")

# ---- the limits (L7) ---------------------------------------------------------------------------------------------

CONNECT_SECONDS = 5
READ_SECONDS = 10
TOTAL_MAX_ATTEMPTS = 2  # the first try and one retry ("standard" mode)
TEST_LIMIT_SECONDS = 30.0  # the whole Test
TEST_GRACE_SECONDS = 5.0  # how long past the limit the request waits for the worker to report

TEST_PREFIX = "shelfsync-test/"
TEST_KEY = re.compile(r"shelfsync-test/[0-9]{8}T[0-9]{6}Z-[0-9a-f]{32}\.txt")
TEST_CONTENT_TYPE = "text/plain; charset=utf-8"
_AWS_CODE = re.compile(r"[A-Za-z0-9.]{1,64}")

StepName = Literal["write", "read", "delete"]
KeyPairName = Literal["rw", "ro"]
StepState = Literal["passed", "failed", "not_run"]
Reason = Literal[
    "access_denied",
    "key_unknown",
    "secret_wrong",
    "clock_wrong",
    "bucket_missing",
    "wrong_region",
    "not_found",
    "mismatch",
    "confirm_forbidden",
    "still_there",
    "refused",
    "server_error",
    "unreachable",
    "timeout",
    "tls_error",
    "bad_response",
]
STEPS: tuple[tuple[StepName, KeyPairName], ...] = (("write", "rw"), ("read", "ro"), ("delete", "rw"))

# S3 error Codes, mapped to a reason (anything else is decided by the HTTP status, in `classify`)
_CODE_REASONS: dict[str, Reason] = {
    "AccessDenied": "access_denied",
    "AllAccessDisabled": "access_denied",
    "InvalidAccessKeyId": "key_unknown",
    "SignatureDoesNotMatch": "secret_wrong",
    "RequestTimeTooSkewed": "clock_wrong",
    "NoSuchBucket": "bucket_missing",
    # a wrong region that survived botocore's region redirector
    "AuthorizationHeaderMalformed": "wrong_region",
    "PermanentRedirect": "wrong_region",
    "IllegalLocationConstraintException": "wrong_region",
    "NoSuchKey": "not_found",
    "SlowDown": "server_error",
}


@dataclass(frozen=True)
class S3Target:
    """Where the bucket is. `endpoint` None is AWS itself; otherwise an address `check_s3_endpoint` accepted."""

    endpoint: str | None
    region: str
    bucket: str


class S3Client(Protocol):
    """The four calls the Test makes (botocore's client has them all). `Any` stays inside this module."""

    def put_object(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def get_object(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def delete_object(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def head_object(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def close(self) -> None: ...


ClientFactory = Callable[[S3Target, S3Pair], S3Client]


# ---- the client --------------------------------------------------------------------------------------------------


def _never_a_file() -> str:
    """A path that can never exist: a child of botocore's own `__init__.py`, which is a file. No `$` or `%` is added
    (botocore expands both in config paths)."""
    import botocore

    return str(Path(botocore.__file__) / "shelfsync-no-aws-config")


def _isolated_session_vars() -> dict[str, tuple[Any, Any, Any, Any]]:
    """Every botocore session variable `(config file key, env vars, default, conversion)` with its environment and
    config-file slots emptied (the defaults kept), so none is read from the environment or `~/.aws`; no profile, no
    model folder, and config and credentials files that don't exist. Built from botocore's own table, so a variable a
    later botocore adds is closed too."""
    from botocore.configprovider import BOTOCORE_DEFAUT_SESSION_VARIABLES

    variables: dict[str, tuple[Any, Any, Any, Any]] = {
        name: (None, None, default, convert)
        for name, (_, _, default, convert) in BOTOCORE_DEFAUT_SESSION_VARIABLES.items()
    }
    nowhere = _never_a_file()
    variables.update(
        {
            "profile": (None, None, None, None),
            "config_file": (None, None, nowhere, None),
            "credentials_file": (None, None, nowhere, None),
            "data_path": (None, None, None, None),
        }
    )
    return variables


def client_config(target: S3Target) -> Config:
    """Every value explicit, so nothing comes from the environment or a config file (L5, L6, L7, L9)."""
    from botocore.config import Config

    custom = target.endpoint is not None
    return Config(
        connect_timeout=CONNECT_SECONDS,
        read_timeout=READ_SECONDS,
        retries={"mode": "standard", "total_max_attempts": TOTAL_MAX_ATTEMPTS},
        proxies={},  # not None: None makes botocore read HTTPS_PROXY and the Windows proxy settings
        ignore_configured_endpoint_urls=True,
        use_fips_endpoint=False,
        use_dualstack_endpoint=False,
        defaults_mode="legacy",
        signature_version="s3v4",
        # 1.36 made checksums the default; some S3-compatible servers reject them (V10). AWS gets the new default.
        request_checksum_calculation="when_required" if custom else "when_supported",
        response_checksum_validation="when_required" if custom else "when_supported",
        # The `s3` section is also read from AWS_S3_* variables: every key that changes where a request goes is set.
        s3={
            "addressing_style": "path" if custom else "auto",
            "us_east_1_regional_endpoint": "regional",
            "use_arn_region": False,
            "s3_disable_multiregion_access_points": True,
            "use_accelerate_endpoint": False,
        },
    )


def make_client(target: S3Target, pair: S3Pair) -> S3Client:
    """A new, isolated S3 client for one key pair. A fresh botocore Session each time: Sessions aren't thread-safe
    (clients are). The caller closes it."""
    import botocore.session
    from botocore.loaders import Loader

    session = botocore.session.Session(session_vars=_isolated_session_vars())
    # Only botocore's own models: never `~/.aws/models` or AWS_DATA_PATH, which could replace S3's service model.
    session.register_component(
        "data_loader", Loader(extra_search_paths=[Loader.BUILTIN_DATA_PATH], include_default_search_paths=False)
    )
    client: S3Client = session.create_client(
        "s3",
        region_name=target.region,
        endpoint_url=target.endpoint,
        verify=True,
        aws_access_key_id=pair.key_id,
        aws_secret_access_key=pair.secret,
        aws_session_token=None,
        config=client_config(target),
    )
    return client


# ---- what went wrong ----------------------------------------------------------------------------------------------


def safe_aws_code(code: object) -> str | None:
    """The S3 error Code when it is a short plain word (letters, digits, dots) that holds nothing secret; else None."""
    if not isinstance(code, str) or _AWS_CODE.fullmatch(code) is None:
        return None
    return code if redact(code) == code else None


@dataclass(frozen=True)
class Failure:
    reason: Reason
    aws_code: str | None = None
    http_status: int | None = None
    # The request may have reached S3 and been carried out (an answer lost on the way back, or a 5xx). Used only
    # inside the Test, to clean up after a write (L13); never in a response.
    maybe_sent: bool = False


def _client_error_parts(error: Exception) -> tuple[str | None, int | None]:
    """The Code (None when botocore made it up from the status, as for a HEAD, which has no body) and the status."""
    response = getattr(error, "response", None)
    if not isinstance(response, Mapping):
        return None, None
    details = response.get("Error")
    meta = response.get("ResponseMetadata")
    raw_code = details.get("Code") if isinstance(details, Mapping) else None
    raw_status = meta.get("HTTPStatusCode") if isinstance(meta, Mapping) else None
    status = raw_status if type(raw_status) is int and 100 <= raw_status <= 599 else None
    code = safe_aws_code(raw_code)
    if code is not None and status is not None and code == str(status):
        code = None  # botocore's stand-in for a missing Code, not S3's
    return code, status


def classify(error: BaseException) -> Failure:
    """The fixed reason for an exception from a client call. Pure: reads only the exception's type, Code and status."""
    from botocore.exceptions import (
        ClientError,
        ConnectionClosedError,
        ConnectionError,
        ConnectTimeoutError,
        FlexibleChecksumError,
        HTTPClientError,
        IncompleteReadError,
        ReadTimeoutError,
        ResponseStreamingError,
        SSLError,
    )

    # Sent, then the answer was lost: the request may have been carried out. A connect timeout, a refused connection,
    # a TLS failure and any 4xx mean it never was.
    lost = isinstance(error, (ReadTimeoutError, ConnectionClosedError, ResponseStreamingError))
    if isinstance(error, ClientError):
        code, status = _client_error_parts(error)
        reason = _CODE_REASONS.get(code) if code is not None else None
        if reason is None:
            if status is None:
                reason = "bad_response"
            elif status >= 500:
                reason = "server_error"
            elif status == 404:
                reason = "not_found"
            elif status >= 400:
                reason = "refused"
            else:
                reason = "bad_response"
        maybe_sent = status is not None and status >= 500 and code != "SlowDown"
        return Failure(reason, code, status, maybe_sent)
    if isinstance(error, (ConnectTimeoutError, ReadTimeoutError, TimeoutError)):
        return Failure("timeout", maybe_sent=lost)
    if isinstance(error, SSLError):
        return Failure("tls_error")
    if isinstance(error, (ConnectionError, ConnectionClosedError, HTTPClientError)):
        return Failure("unreachable", maybe_sent=lost)
    if isinstance(error, (FlexibleChecksumError, IncompleteReadError)):
        return Failure("mismatch")  # the bytes read back didn't match the answer's checksum or its length
    return Failure("bad_response")


# ---- the Test -----------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class StepResult:
    step: StepName
    key_pair: KeyPairName
    state: StepState
    latency_ms: int | None = None
    reason: Reason | None = None
    aws_code: str | None = None
    http_status: int | None = None
    maybe_sent: bool = False  # internal (see `Failure`); never in a response


def not_run(step: StepName, key_pair: KeyPairName) -> StepResult:
    return StepResult(step, key_pair, "not_run")


Cleanup = Literal["confirmed", "failed"]


@dataclass(frozen=True)
class StorageTestOutcome:
    steps: tuple[StepResult, StepResult, StepResult]
    key: str
    latency_ms: int
    # The test key when the test file may still be in the bucket: the write passed and the delete didn't; a write that
    # may have reached S3 wasn't confirmed gone (L13); or the time ran out while either was running.
    left_behind: str | None
    cleanup: Cleanup | None = None  # after a failed write that may have reached S3 (L13)

    @property
    def ok(self) -> bool:
        return all(step.state == "passed" for step in self.steps)


def _left_after_delete(steps: tuple[StepResult, StepResult, StepResult], key: str) -> str | None:
    write, _, delete = steps
    return key if write.state == "passed" and delete.state != "passed" else None


@dataclass
class StorageTestProgress:
    """What the worker has done so far, so the request can answer on time when the worker overruns. Thread-safe."""

    key: str = ""
    done: list[StepResult] = field(default_factory=list)
    cleanup_running: bool = False  # the clean-up after a write that may have reached S3 (L13)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def record(self, result: StepResult) -> None:
        with self._lock:
            self.done.append(result)

    def start_cleanup(self) -> None:
        with self._lock:
            self.cleanup_running = True

    def overrun(self, latency_ms: int) -> StorageTestOutcome:
        """The answer when the Test ran out of time: the steps done stand, the running one is `timeout`, the rest
        `not_run`. While the write, or the clean-up after a failed one, is running, steps 2 and 3 are `not_run` and the
        key is named: the write may still land."""
        with self._lock:
            done = list(self.done)
            cleanup_running = self.cleanup_running
        if not done or cleanup_running:
            write = done[0] if done else StepResult("write", "rw", "failed", None, "timeout")
            steps = (write, not_run("read", "ro"), not_run("delete", "rw"))
            return StorageTestOutcome(steps, self.key, latency_ms, self.key)
        listed: list[StepResult] = []
        for index, (step, pair) in enumerate(STEPS):
            if index < len(done):
                listed.append(done[index])
            elif index == len(done):
                listed.append(StepResult(step, pair, "failed", None, "timeout"))
            else:
                listed.append(not_run(step, pair))
        steps = (listed[0], listed[1], listed[2])
        return StorageTestOutcome(steps, self.key, latency_ms, _left_after_delete(steps, self.key))


def new_test_object(now: datetime) -> tuple[str, bytes]:
    """A fresh test key and body: `shelfsync-test/<UTC time>-<32 hex>.txt`, never one that exists already."""
    nonce = secrets.token_hex(16)
    key = f"{TEST_PREFIX}{now.astimezone(UTC).strftime('%Y%m%dT%H%M%SZ')}-{nonce}.txt"
    return key, b"ShelfSync storage test " + nonce.encode("ascii") + b"\n"


def _elapsed_ms(monotonic: Callable[[], float], start: float) -> int:
    return max(0, round((monotonic() - start) * 1000))


def _failed(step: StepName, pair: KeyPairName, ms: int, failure: Failure) -> StepResult:
    return StepResult(
        step, pair, "failed", ms, failure.reason, failure.aws_code, failure.http_status, failure.maybe_sent
    )


def _only_a_test_key(key: str) -> None:
    """The Test writes and deletes nothing but its own `shelfsync-test/...` object (APL-07, CAT-04)."""
    if TEST_KEY.fullmatch(key) is None:
        raise ValueError("not a test key")


def _write(rw: S3Client, bucket: str, key: str, body: bytes) -> None:
    _only_a_test_key(key)
    md5 = base64.b64encode(hashlib.md5(body, usedforsecurity=False).digest()).decode("ascii")
    rw.put_object(Bucket=bucket, Key=key, Body=body, ContentType=TEST_CONTENT_TYPE, ContentMD5=md5)


def _read(ro: S3Client, bucket: str, key: str, body: bytes) -> Failure | None:
    answer = ro.get_object(Bucket=bucket, Key=key)
    stream = answer["Body"]
    try:
        got = stream.read(len(body) + 1)  # never more than one byte past what was written
        if len(got) == len(body):
            # One more read, which must find the end: only then does botocore check the answer's Content-Length and
            # its checksum (AWS), so a short or corrupted answer can't pass.
            got += stream.read(1)
    finally:
        stream.close()
    return None if got == body else Failure("mismatch")


def _delete(rw: S3Client, bucket: str, key: str) -> Failure | None:
    """DELETE, then a HEAD that must answer 404 (L3): the proof the object is gone, and that the read-and-write key
    has `s3:ListBucket` (without it S3 answers 403 for a missing key, V52)."""
    from botocore.exceptions import ClientError

    _only_a_test_key(key)
    rw.delete_object(Bucket=bucket, Key=key)
    try:
        rw.head_object(Bucket=bucket, Key=key)
    except ClientError as error:
        code, status = _client_error_parts(error)
        if status == 404:
            return None
        if status == 403:
            return Failure("confirm_forbidden", code, status)
        return classify(error)
    return Failure("still_there", None, 200)


def _step(
    run: Callable[[], Failure | None],
    step: StepName,
    pair: KeyPairName,
    monotonic: Callable[[], float],
) -> StepResult:
    start = monotonic()
    try:
        failure = run()
    except Exception as error:  # every failure becomes a fixed reason; the text of the error is never kept
        return _failed(step, pair, _elapsed_ms(monotonic, start), classify(error))
    ms = _elapsed_ms(monotonic, start)
    return StepResult(step, pair, "passed", ms) if failure is None else _failed(step, pair, ms, failure)


def run_storage_test(
    rw: S3Client,
    ro: S3Client,
    bucket: str,
    *,
    monotonic: Callable[[], float] = time.monotonic,
    now: Callable[[], datetime],
    abandoned: Callable[[], bool] = lambda: False,
    progress: StorageTestProgress | None = None,
) -> StorageTestOutcome:
    """The three steps. `abandoned` turns true when the Test is out of time (or the request stopped waiting): the read
    is then skipped (`timeout`), but a passed write is still deleted. A failed write that may still have reached S3 is
    cleaned up the same way (DELETE, then HEAD; L13), while steps 2 and 3 show `not_run`. The caller logs the outcome
    (`log_outcome`)."""
    progress = progress if progress is not None else StorageTestProgress()
    key, body = new_test_object(now())
    progress.key = key
    start = monotonic()

    write_result = _step(lambda: _write(rw, bucket, key, body), "write", "rw", monotonic)
    written = write_result.state == "passed"
    if not written and write_result.maybe_sent:
        progress.start_cleanup()  # before the write is recorded, so an overrun in between still names the key
    progress.record(write_result)
    if not written:
        read_result = not_run("read", "ro")
    elif abandoned():
        read_result = StepResult("read", "ro", "failed", None, "timeout")
    else:
        read_result = _step(lambda: _read(ro, bucket, key, body), "read", "ro", monotonic)
    progress.record(read_result)
    cleanup: Cleanup | None = None
    if written:  # always, after a passed write, whatever the read did (L2)
        delete_result = _step(lambda: _delete(rw, bucket, key), "delete", "rw", monotonic)
    else:
        delete_result = not_run("delete", "rw")
        if write_result.maybe_sent:  # the write may have landed: delete it all the same (L13)
            confirmed = _step(lambda: _delete(rw, bucket, key), "delete", "rw", monotonic).state == "passed"
            cleanup = "confirmed" if confirmed else "failed"
    progress.record(delete_result)
    steps = (write_result, read_result, delete_result)
    left = _left_after_delete(steps, key) if written else (key if cleanup == "failed" else None)
    return StorageTestOutcome(steps, key, _elapsed_ms(monotonic, start), left, cleanup)


def log_outcome(outcome: StorageTestOutcome, *, late: bool = False) -> None:
    """One INFO line: per step the state, reason, Code, status and time. Never a key, address, bucket or error text."""
    parts = []
    for step in outcome.steps:
        text = f"{step.step} {step.state}"
        if step.state == "failed":
            text += f" ({step.reason}, {step.aws_code or '-'}, HTTP {step.http_status or '-'})"
        if step.latency_ms is not None:
            text += f" in {step.latency_ms} ms"
        parts.append(text)
    if outcome.cleanup is not None:
        parts.append(f"cleanup {outcome.cleanup}")
    left = "; the test file may be left behind" if outcome.left_behind is not None else ""
    when = " (finished after the answer was sent)" if late else ""
    _log.info("Storage test %s%s: %s%s", "passed" if outcome.ok else "failed", when, "; ".join(parts), left)


def close_quietly(client: S3Client | None) -> None:
    if client is None:
        return
    try:
        client.close()
    except Exception as error:  # a close that fails changes nothing for the caller
        _log.debug("An S3 client didn't close cleanly (%s)", type(error).__name__)


__all__ = [
    "STEPS",
    "TEST_GRACE_SECONDS",
    "TEST_KEY",
    "TEST_LIMIT_SECONDS",
    "TEST_PREFIX",
    "Cleanup",
    "ClientFactory",
    "Failure",
    "Reason",
    "S3Client",
    "S3Target",
    "StepResult",
    "StorageTestOutcome",
    "StorageTestProgress",
    "classify",
    "client_config",
    "close_quietly",
    "log_outcome",
    "make_client",
    "new_test_object",
    "not_run",
    "run_storage_test",
    "safe_aws_code",
]
