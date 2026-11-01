"""SET-02, ERR-03: the Storage Test, `POST /api/storage/test`, end to end. moto in-process stands in for AWS (with IAM
users holding the exact 06 section 5 policies), `FakeS3` for what moto can't model, and plain servers on 127.0.0.1 for
the network failures. No live AWS, bucket or store is ever reached."""

import json
import logging
import sqlite3
import threading
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from moto import mock_aws
from moto.core import enable_iam_authentication

from shelfsync import logs
from shelfsync.api.storage import STORAGE_TEST_PATH, StorageService, StorageTestError
from shelfsync.apply.s3 import TEST_KEY, ClientFactory, S3Client, S3Target, make_client
from shelfsync.db.settings import check_s3_region
from shelfsync.secure.credentials import S3Credentials, S3Pair
from tests.s3_support import (
    BUCKET,
    REGION,
    FakeS3,
    ScriptedServer,
    aws_setup_env,  # noqa: F401  (a fixture)
    canned_factory,
    closed_port,
    create_bucket,
    error_xml,
    iam_user,
    keys_in,
    ro_policy,
    rw_policy,
    s3_guard,  # noqa: F401  (autouse: the key guard and the outbound record)
    wait_until,
)
from tests.storage_support import GOOD_SETTINGS, RO_ID, RO_SECRET, RW_ID, RW_SECRET, StorageRig, make_storage_rig
from tests.store_support import FailingSecretStore
from tests.support import WRITE_HEADERS

NOW = datetime(2026, 11, 2, 10, 0, 0, tzinfo=UTC)


def rig_with(
    factory: ClientFactory | None = None,
    *,
    endpoint: str = "",
    keys: bool = True,
    secrets: FailingSecretStore | None = None,
    **seams: Any,
) -> StorageRig:
    if factory is not None:
        seams["client_factory"] = factory
    rig = make_storage_rig(secrets, now=lambda: NOW, **seams)
    settings = {**GOOD_SETTINGS, "s3_endpoint": endpoint, "s3_region": REGION, "s3_bucket": BUCKET}
    assert rig.client.put("/api/settings/storage", json=settings, headers=WRITE_HEADERS).status_code == 200
    if keys:
        store_keys(rig, S3Pair(RW_ID, RW_SECRET), S3Pair(RO_ID, RO_SECRET))
    return rig


def store_keys(rig: StorageRig, rw: S3Pair, ro: S3Pair) -> None:
    credentials = S3Credentials(rig.secrets)
    credentials.save("rw", rw.key_id, rw.secret)
    credentials.save("ro", ro.key_id, ro.secret)


def run_test(rig: StorageRig) -> Any:
    return rig.client.post(STORAGE_TEST_PATH, headers=WRITE_HEADERS)


def steps(body: dict[str, Any]) -> list[tuple[str, str, str | None]]:
    return [(step["step"], step["state"], step["reason"]) for step in body["steps"]]


def assert_nothing_private(text: str, *also: str) -> None:
    for value in (RW_ID, RW_SECRET, RO_ID, RO_SECRET, BUCKET, "s3.example.com", "amazonaws", *also):
        assert value not in text


# ---- moto, in-process: AWS itself ------------------------------------------------------------------------------------


@pytest.mark.usefixtures("aws_setup_env")
def test_a_full_pass_writes_reads_and_deletes_the_test_file() -> None:
    with mock_aws():
        create_bucket()
        rig = rig_with()
        response = run_test(rig)
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True and body["left_behind"] is None
        assert steps(body) == [("write", "passed", None), ("read", "passed", None), ("delete", "passed", None)]
        assert [step["key_pair"] for step in body["steps"]] == ["rw", "ro", "rw"]
        assert all(isinstance(step["latency_ms"], int) for step in body["steps"])
        assert body["tested_at"] == "2026-11-02T10:00:00.000000Z"
        assert keys_in() == []  # the object is gone
        assert_nothing_private(response.text)


@pytest.mark.usefixtures("aws_setup_env")
def test_a_missing_bucket_is_bucket_missing_err_03() -> None:
    with mock_aws():
        response = run_test(rig_with())
    body = response.json()
    assert response.status_code == 200 and body["ok"] is False
    assert body["steps"][0] == {
        "step": "write",
        "key_pair": "rw",
        "state": "failed",
        "latency_ms": body["steps"][0]["latency_ms"],
        "reason": "bucket_missing",
        "aws_code": "NoSuchBucket",
        "http_status": 404,
    }
    assert steps(body)[1:] == [("read", "not_run", None), ("delete", "not_run", None)]
    assert body["left_behind"] is None
    assert_nothing_private(response.text)


# ---- moto with IAM: the two policies of 06 section 5 -----------------------------------------------------------------


def iam_rig(rw_actions: tuple[str, ...] | None = None) -> tuple[StorageRig, S3Pair, S3Pair]:
    create_bucket()
    rw = iam_user("shelfsync-rw", rw_policy() if rw_actions is None else rw_policy(actions=rw_actions))
    ro = iam_user("shelfsync-ro", ro_policy())
    rig = rig_with(keys=False)
    return rig, rw, ro


@pytest.mark.usefixtures("aws_setup_env")
def test_with_the_two_policies_the_test_passes() -> None:
    with mock_aws():
        rig, rw, ro = iam_rig()
        store_keys(rig, rw, ro)
        with enable_iam_authentication():
            body = run_test(rig).json()
        assert body["ok"] is True, body
        assert keys_in() == []


@pytest.mark.usefixtures("aws_setup_env")
def test_the_read_only_key_cant_write() -> None:
    """The pairs swapped: the read-only key is refused on the write; nothing else runs."""
    with mock_aws():
        rig, rw, ro = iam_rig()
        store_keys(rig, ro, rw)
        with enable_iam_authentication():
            response = run_test(rig)
    body = response.json()
    assert steps(body) == [("write", "failed", "access_denied"), ("read", "not_run", None), ("delete", "not_run", None)]
    assert body["steps"][0]["aws_code"] == "AccessDenied" and body["steps"][0]["http_status"] == 403
    assert "123456789012" not in response.text and "arn:" not in response.text  # never the Message


@pytest.mark.usefixtures("aws_setup_env")
def test_an_unknown_key_id_and_a_wrong_secret() -> None:
    with mock_aws():
        rig, rw, ro = iam_rig()
        store_keys(rig, S3Pair("AKIA" + "UNKNOWNUNKNOWN00", rw.secret), ro)
        with enable_iam_authentication():
            unknown = run_test(rig).json()
        store_keys(rig, S3Pair(rw.key_id, "x" * 40), ro)
        with enable_iam_authentication():
            wrong = run_test(rig).json()
    assert steps(unknown)[0] == ("write", "failed", "key_unknown")
    assert unknown["steps"][0]["aws_code"] == "InvalidAccessKeyId"
    assert steps(wrong)[0] == ("write", "failed", "secret_wrong")
    assert wrong["steps"][0]["aws_code"] == "SignatureDoesNotMatch"


@pytest.mark.usefixtures("aws_setup_env")
def test_a_read_and_write_key_without_delete_leaves_the_file_and_says_so() -> None:
    with mock_aws():
        rig, rw, ro = iam_rig(rw_actions=("s3:GetObject", "s3:PutObject"))
        store_keys(rig, rw, ro)
        with enable_iam_authentication():
            body = run_test(rig).json()
        left = keys_in()
    assert steps(body) == [("write", "passed", None), ("read", "passed", None), ("delete", "failed", "access_denied")]
    assert body["left_behind"] is not None and TEST_KEY.fullmatch(body["left_behind"])
    assert left == [body["left_behind"]]


# ---- canned answers: what moto can't model ---------------------------------------------------------------------------


def canned_rig(fake: FakeS3, endpoint: str = "https://s3.example.com") -> StorageRig:
    return rig_with(canned_factory(fake), endpoint=endpoint)


@pytest.mark.parametrize(
    ("method", "answer", "expected"),
    [
        ("PUT", (503, error_xml("SlowDown"), {}), ("write", "server_error", "SlowDown", 503)),
        ("PUT", (403, error_xml("RequestTimeTooSkewed"), {}), ("write", "clock_wrong", "RequestTimeTooSkewed", 403)),
        (
            "PUT",
            (400, error_xml("AuthorizationHeaderMalformed"), {}),
            ("write", "wrong_region", "AuthorizationHeaderMalformed", 400),
        ),
        ("PUT", (400, b"<not xml", {}), ("write", "refused", None, 400)),
        ("GET", (404, error_xml("NoSuchKey"), {}), ("read", "not_found", "NoSuchKey", 404)),
        ("GET", (200, b"something else entirely", {}), ("read", "mismatch", None, None)),
        ("HEAD", (403, b"", {}), ("delete", "confirm_forbidden", None, 403)),
        ("HEAD", (200, b"", {}), ("delete", "still_there", None, 200)),
        ("DELETE", (403, error_xml("AccessDenied"), {}), ("delete", "access_denied", "AccessDenied", 403)),
    ],
)
def test_each_canned_failure(method: str, answer: Any, expected: tuple[str, str, str | None, int | None]) -> None:
    fake = FakeS3()
    for n in (1, 2):  # the retry gets the same answer
        fake.script[(method, n)] = answer
    response = run_test(canned_rig(fake))
    body = response.json()
    step, reason, code, status = expected
    failed = next(item for item in body["steps"] if item["step"] == step)
    assert (failed["state"], failed["reason"], failed["http_status"], failed["aws_code"]) == (
        "failed",
        reason,
        status,
        code,
    )
    if method != "PUT":  # a passed write is always deleted, whatever the read did
        assert "DELETE" in fake.methods()
    assert (body["left_behind"] is not None) == (step == "delete")
    assert_nothing_private(response.text)


def test_a_failed_read_is_still_followed_by_the_delete() -> None:
    fake = FakeS3()
    fake.script[("GET", 1)] = fake.script[("GET", 2)] = (403, error_xml("AccessDenied"), {})
    body = run_test(canned_rig(fake)).json()
    assert steps(body) == [("write", "passed", None), ("read", "failed", "access_denied"), ("delete", "passed", None)]
    assert fake.methods() == ["PUT", "GET", "DELETE", "HEAD"]  # a 403 is not retried
    assert body["left_behind"] is None and body["ok"] is False


def test_a_failed_write_runs_nothing_else() -> None:
    fake = FakeS3()
    fake.script[("PUT", 1)] = fake.script[("PUT", 2)] = (403, error_xml("AccessDenied"), {})
    body = run_test(canned_rig(fake)).json()
    assert fake.methods() == ["PUT"]  # a 403 is not retried
    assert steps(body)[1:] == [("read", "not_run", None), ("delete", "not_run", None)]
    assert [body["steps"][1]["latency_ms"], body["steps"][2]["latency_ms"]] == [None, None]


def test_a_failed_delete_leaves_the_key_for_the_owner() -> None:
    fake = FakeS3()
    fake.script[("HEAD", 1)] = (200, b"", {})
    body = run_test(canned_rig(fake)).json()
    assert body["left_behind"] == fake.sent[0].url.split("/s3.example.com/" + BUCKET + "/")[-1]
    assert TEST_KEY.fullmatch(body["left_behind"])


def test_the_read_never_takes_more_than_one_byte_past_the_written_length() -> None:
    fake = FakeS3()
    fake.script[("GET", 1)] = (200, b"x" * 1_000_000, {})
    body = run_test(canned_rig(fake)).json()
    assert steps(body)[1] == ("read", "failed", "mismatch")


# ---- the network: local listeners on 127.0.0.1 -----------------------------------------------------------------------


def test_a_closed_port_is_unreachable() -> None:
    body = run_test(rig_with(endpoint=f"http://127.0.0.1:{closed_port()}")).json()
    assert steps(body)[0] == ("write", "failed", "unreachable")
    assert body["steps"][0]["aws_code"] is None and body["steps"][0]["http_status"] is None


def test_plain_tcp_on_an_https_address_is_a_tls_error() -> None:
    with ScriptedServer() as server:
        body = run_test(rig_with(endpoint=f"https://localhost:{server.port}")).json()
    assert steps(body)[0] == ("write", "failed", "tls_error")


def test_the_whole_test_through_a_real_socket_passes() -> None:
    with ScriptedServer() as server:
        body = run_test(rig_with(endpoint=f"http://127.0.0.1:{server.port}")).json()
        assert body["ok"] is True, body
        assert server.methods() == ["PUT", "GET", "DELETE", "HEAD"]
        assert all(path.startswith(f"/{BUCKET}/shelfsync-test/") for _, path in server.seen)  # path style
        assert server.objects == {}


def test_a_service_that_never_answers_times_out_within_the_limit() -> None:
    with ScriptedServer() as server:
        server.hold["PUT"] = threading.Event()  # never set until the end
        rig = rig_with(endpoint=f"http://127.0.0.1:{server.port}", limit_seconds=2.0, grace_seconds=0.2)
        started = datetime.now(UTC)
        body = run_test(rig).json()
        took = (datetime.now(UTC) - started).total_seconds()
        assert took < 5.0  # the limit (2 s, room for building the clients) plus the grace, not 20 s of retries
        assert steps(body) == [("write", "failed", "timeout"), ("read", "not_run", None), ("delete", "not_run", None)]
        assert body["left_behind"] is not None and TEST_KEY.fullmatch(body["left_behind"])  # the write may land (L13)
        assert run_test(rig).json() == {"error": "busy"}  # held until the worker really ends
        server.hold["PUT"].set()  # the write lands late: the worker still deletes it
        assert server.done.wait(10)
        assert wait_until(lambda: run_test(rig).status_code != 409)
    assert "GET" not in server.methods()[:3]  # the late worker skipped the read


def test_a_late_write_is_still_deleted_and_logged(caplog: pytest.LogCaptureFixture) -> None:
    with ScriptedServer() as server:
        server.hold["PUT"] = threading.Event()
        rig = rig_with(endpoint=f"http://127.0.0.1:{server.port}", limit_seconds=2.0, grace_seconds=0.2)
        with caplog.at_level("INFO", logger="shelfsync.storage"):
            body = run_test(rig).json()
            assert steps(body)[0] == ("write", "failed", "timeout")
            assert body["left_behind"] is not None
            server.hold["PUT"].set()
            assert server.done.wait(10)
            assert wait_until(lambda: "after the answer was sent" in caplog.text)
        assert server.methods() == ["PUT", "DELETE", "HEAD"]
        assert server.objects == {}
    assert "ran out of time" in caplog.text
    assert "read failed (timeout" in caplog.text


def test_running_out_of_time_during_the_read_still_deletes() -> None:
    """The write passed, the read hangs: the answer names the key (step 3 didn't pass), and the worker deletes it."""
    with ScriptedServer() as server:
        server.hold["GET"] = threading.Event()
        rig = rig_with(endpoint=f"http://127.0.0.1:{server.port}", limit_seconds=2.0, grace_seconds=0.2)
        body = run_test(rig).json()
        assert steps(body) == [("write", "passed", None), ("read", "failed", "timeout"), ("delete", "not_run", None)]
        assert body["steps"][1]["latency_ms"] is None
        assert body["left_behind"] is not None and TEST_KEY.fullmatch(body["left_behind"])
        server.hold["GET"].set()
        assert server.done.wait(10)
        assert wait_until(lambda: run_test(rig).status_code != 409)
        assert server.methods()[:4] == ["PUT", "GET", "DELETE", "HEAD"]


# ---- a write that may have reached S3 (L13) --------------------------------------------------------------------------


def test_a_write_that_got_500_twice_is_cleaned_up() -> None:
    fake = FakeS3()
    fake.script[("PUT", 1)] = fake.script[("PUT", 2)] = (500, error_xml("InternalError"), {})
    body = run_test(canned_rig(fake)).json()
    assert fake.methods() == ["PUT", "PUT", "DELETE", "HEAD"]
    assert steps(body) == [("write", "failed", "server_error"), ("read", "not_run", None), ("delete", "not_run", None)]
    assert body["left_behind"] is None  # the clean-up's HEAD answered 404
    assert body["ok"] is False


def test_a_cleanup_that_cant_confirm_names_the_key() -> None:
    fake = FakeS3()
    fake.script[("PUT", 1)] = fake.script[("PUT", 2)] = (500, error_xml("InternalError"), {})
    fake.script[("HEAD", 1)] = (403, b"", {})
    body = run_test(canned_rig(fake)).json()
    assert fake.methods() == ["PUT", "PUT", "DELETE", "HEAD"]
    assert steps(body)[1:] == [("read", "not_run", None), ("delete", "not_run", None)]
    assert body["left_behind"] is not None and TEST_KEY.fullmatch(body["left_behind"])


def test_a_lost_answer_to_the_write_is_cleaned_up() -> None:
    from botocore.exceptions import ReadTimeoutError

    fake = FakeS3()
    lost = ReadTimeoutError(endpoint_url="https://s3.example.com")
    fake.script[("PUT", 1)] = fake.script[("PUT", 2)] = lost
    body = run_test(canned_rig(fake)).json()
    assert steps(body)[0] == ("write", "failed", "timeout")
    assert fake.methods() == ["PUT", "PUT", "DELETE", "HEAD"]
    assert body["left_behind"] is None


@pytest.mark.parametrize(
    "answer",
    [(403, error_xml("AccessDenied"), {}), (503, error_xml("SlowDown"), {}), (400, error_xml("InvalidRequest"), {})],
    ids=["403", "SlowDown", "400"],
)
def test_a_write_that_never_happened_is_not_cleaned_up(answer: Any) -> None:
    fake = FakeS3()
    fake.script[("PUT", 1)] = fake.script[("PUT", 2)] = answer
    body = run_test(canned_rig(fake)).json()
    assert "DELETE" not in fake.methods() and "HEAD" not in fake.methods()
    assert body["left_behind"] is None


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("lost", "connect_timeout"),  # the first PUT may have landed; its retry never left the PC
        ("500", "SlowDown"),
        ("lost", "unreachable"),
        ("500", "400"),
    ],
)
def test_any_attempt_that_may_have_landed_triggers_the_cleanup(first: str, second: str) -> None:
    """M1 (review): the clean-up is decided from every attempt of the write, not only the last one's error."""
    from botocore.exceptions import ConnectTimeoutError, EndpointConnectionError, ReadTimeoutError

    url = "https://s3.example.com"
    answers: dict[str, Any] = {
        "lost": ReadTimeoutError(endpoint_url=url),
        "500": (500, error_xml("InternalError"), {}),
        "connect_timeout": ConnectTimeoutError(endpoint_url=url),
        "unreachable": EndpointConnectionError(endpoint_url=url),
        "SlowDown": (503, error_xml("SlowDown"), {}),
        "400": (400, error_xml("RequestTimeout"), {}),
    }
    fake = FakeS3()
    fake.script[("PUT", 1)] = answers[first]
    fake.script[("PUT", 2)] = answers[second]
    body = run_test(canned_rig(fake)).json()
    assert body["steps"][0]["state"] == "failed"
    assert fake.methods() == ["PUT", "PUT", "DELETE", "HEAD"]
    assert steps(body)[1:] == [("read", "not_run", None), ("delete", "not_run", None)]
    assert body["left_behind"] is None  # confirmed gone


def test_a_write_retried_after_slowdown_and_refused_is_not_cleaned_up() -> None:
    """Neither attempt can have landed (SlowDown, then 403): nothing is deleted."""
    fake = FakeS3()
    fake.script[("PUT", 1)] = (503, error_xml("SlowDown"), {})
    fake.script[("PUT", 2)] = (403, error_xml("AccessDenied"), {})
    body = run_test(canned_rig(fake)).json()
    assert fake.methods() == ["PUT", "PUT"] and body["left_behind"] is None


def test_running_out_of_time_while_the_clients_are_built_sends_nothing_and_names_no_key() -> None:
    """M3 (review): an overrun before the test key exists answers `left_behind: null` (not ""), and the late worker,
    finding the time already gone, sends nothing at all."""
    release = threading.Event()
    fake = FakeS3()

    def slow(target: S3Target, pair: S3Pair) -> S3Client:
        release.wait(10)
        return canned_factory(fake)(target, pair)

    rig = rig_with(slow, limit_seconds=0.3, grace_seconds=0.1)
    body = run_test(rig).json()
    assert steps(body) == [("write", "failed", "timeout"), ("read", "not_run", None), ("delete", "not_run", None)]
    assert body["left_behind"] is None
    release.set()
    assert wait_until(lambda: not rig.service._testing)  # the late worker has ended
    assert fake.methods() == []  # it found the time already gone and sent nothing


@pytest.mark.parametrize("region", ["12", "eu-west-", "-eu"])
def test_a_region_botocore_would_refuse_is_refused_at_save(region: str) -> None:
    """M2 (review): one rule for the save and the Test, so neither can reach botocore's InvalidRegionError (a 500)."""
    rig = rig_with(canned_factory(FakeS3()))
    settings = {**GOOD_SETTINGS, "s3_region": region, "s3_bucket": BUCKET}
    response = rig.client.put("/api/settings/storage", json=settings, headers=WRITE_HEADERS)
    assert (response.status_code, response.json()) == (422, {"error": "invalid_request"})


@given(st.from_regex(r"[a-z0-9-]{2,32}", fullmatch=True))
def test_every_region_the_save_accepts_botocore_accepts(region: str) -> None:
    from botocore.exceptions import InvalidRegionError
    from botocore.utils import validate_region_name

    try:
        check_s3_region(region)
    except ValueError:
        return
    try:
        validate_region_name(region)
    except InvalidRegionError:  # pragma: no cover - the failure this test exists to catch
        pytest.fail(f"accepted at save but refused by botocore: {region!r}")


def test_a_connect_timeout_on_the_write_is_not_cleaned_up() -> None:
    from botocore.exceptions import ConnectTimeoutError

    fake = FakeS3()
    fake.script[("PUT", 1)] = fake.script[("PUT", 2)] = ConnectTimeoutError(endpoint_url="https://s3.example.com")
    body = run_test(canned_rig(fake)).json()
    assert steps(body)[0] == ("write", "failed", "timeout")
    assert fake.methods() == ["PUT", "PUT"] and body["left_behind"] is None


def test_a_closed_port_is_not_cleaned_up(request: pytest.FixtureRequest) -> None:
    guard = request.getfixturevalue("s3_guard")
    body = run_test(rig_with(endpoint=f"http://127.0.0.1:{closed_port()}")).json()
    assert steps(body)[0] == ("write", "failed", "unreachable")
    assert "DeleteObject" not in guard.operations() and "HeadObject" not in guard.operations()
    assert body["left_behind"] is None


def test_running_out_of_time_during_the_cleanup_names_the_key(caplog: pytest.LogCaptureFixture) -> None:
    with ScriptedServer() as server:
        server.raw["PUT"] = b"HTTP/1.1 500 Internal Server Error\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
        server.hold["DELETE"] = threading.Event()
        rig = rig_with(endpoint=f"http://127.0.0.1:{server.port}", limit_seconds=2.5, grace_seconds=0.2)
        with caplog.at_level("INFO", logger="shelfsync.storage"):
            body = run_test(rig).json()
            assert steps(body) == [
                ("write", "failed", "server_error"),
                ("read", "not_run", None),
                ("delete", "not_run", None),
            ]
            assert body["left_behind"] is not None and TEST_KEY.fullmatch(body["left_behind"])
            server.hold["DELETE"].set()
            assert wait_until(lambda: "cleanup confirmed" in caplog.text)
        assert server.methods() == ["PUT", "PUT", "DELETE", "HEAD"]


# ---- the logs: no address, bucket or key, from ShelfSync or the libraries (C1) ---------------------------------------

MALFORMED_HEADER = b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\nthis header line has no colon\r\n\r\n"


@pytest.mark.parametrize("configure", [logs.configure_logging, None, logs.configure_append_logging])
def test_the_http_libraries_never_log_an_address_bucket_or_key(
    configure: Any, caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    """urllib3 logs a header it can't parse at WARNING with the full URL (`Failed to parse headers (url=...)`), and
    botocore logs URLs and headers at DEBUG. With ShelfSync's logging set up, neither reaches a log."""
    saved = {name: logging.getLogger(name).level for name in logs.QUIET_LOGGERS}
    for name in logs.QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.NOTSET)  # undo any earlier setup (setLevel clears the cache)
    handler = None
    try:
        with ScriptedServer() as server:
            server.raw["PUT"] = MALFORMED_HEADER
            rig = rig_with(endpoint=f"http://127.0.0.1:{server.port}")
            if configure is not None:
                handler = configure(tmp_path, 1) if configure is logs.configure_logging else configure(tmp_path)
                for name, level in logs.QUIET_LOGGERS.items():
                    assert logging.getLogger(name).level == level
            caplog.clear()
            caplog.set_level(logging.DEBUG)
            run_test(rig)
            records = list(caplog.records)
            port = server.port
    finally:
        if handler is not None:
            logs.remove_logging(handler)
        for name, level in saved.items():
            logging.getLogger(name).setLevel(level)
    text = "\n".join(
        record.getMessage() + (caplog.handler.format(record) if record.exc_info else "") for record in records
    )
    private = (f"127.0.0.1:{port}", BUCKET, "shelfsync-test/")
    if configure is None:  # without the setup the libraries do log them: so the checks below mean something
        assert "Failed to parse headers" in text and all(item in text for item in private)
        return
    assert "Failed to parse headers" not in text
    for item in private:
        assert item not in text


# ---- the API: guard, errors, one at a time ---------------------------------------------------------------------------


def test_the_route_needs_a_session_origin_and_csrf_header() -> None:
    rig = rig_with(canned_factory(FakeS3()))
    assert rig.harness.client().post(STORAGE_TEST_PATH, headers=WRITE_HEADERS).json() == {"error": "signed_out"}
    for headers in (
        {},
        {"Origin": "http://evil.example", "X-ShelfSync": "1"},
        {"X-ShelfSync": "1"},
        {"Origin": WRITE_HEADERS["Origin"]},
    ):
        assert rig.client.post(STORAGE_TEST_PATH, headers=headers).status_code == 403


@pytest.mark.parametrize("change", [{"s3_region": ""}, {"s3_bucket": ""}, {"s3_region": "", "s3_bucket": ""}])
def test_an_empty_region_or_bucket_is_storage_not_set(change: dict[str, str]) -> None:
    fake = FakeS3()
    rig = rig_with(canned_factory(fake))
    settings = {**GOOD_SETTINGS, **change}
    assert rig.client.put("/api/settings/storage", json=settings, headers=WRITE_HEADERS).status_code == 200
    response = run_test(rig)
    assert (response.status_code, response.json()) == (409, {"error": "storage_not_set"})
    assert fake.sent == []


@pytest.mark.parametrize(
    ("key", "raw"),
    [
        ("s3_endpoint", '"ftp://s3.example.com"'),
        ("s3_endpoint", '"https://user@s3.example.com"'),
        ("s3_endpoint", "7"),
        ("s3_region", '"Not A Region"'),
        ("s3_bucket", '"Bad_Bucket"'),
        ("s3_bucket", "not json"),
        ("s3_region", '"12"'),  # botocore refuses an all-digit region (InvalidRegionError, which was a 500)
        ("s3_region", '"eu-west-"'),
    ],
)
def test_a_hand_edited_invalid_setting_is_storage_not_set_never_aws(key: str, raw: str) -> None:
    """L11: the read for the Test is strict. An invalid endpoint must not quietly become "" (AWS)."""
    fake = FakeS3()
    rig = rig_with(canned_factory(fake))
    with closing(rig.service._connect()) as connection:
        connection.execute("UPDATE setting SET value_json = ? WHERE key = ?", (raw, key))
    response = run_test(rig)
    assert (response.status_code, response.json()) == (409, {"error": "storage_not_set"})
    assert fake.sent == []


@pytest.mark.parametrize("missing", ["s3-rw-key-id", "s3-rw-secret", "s3-ro-key-id", "s3-ro-secret"])
def test_a_missing_key_value_is_keys_missing(missing: str) -> None:
    fake = FakeS3()
    rig = rig_with(canned_factory(fake))
    rig.secrets.delete(missing)
    response = run_test(rig)
    assert (response.status_code, response.json()) == (409, {"error": "keys_missing"})
    assert fake.sent == []


def test_an_unreadable_credential_manager_is_secrets_unavailable() -> None:
    fake = FakeS3()
    rig = rig_with(canned_factory(fake))
    rig.secrets.fail_get = True
    response = run_test(rig)
    assert (response.status_code, response.json()) == (503, {"error": "secrets_unavailable"})
    assert fake.sent == []


def test_two_tests_at_once_one_is_busy_and_a_key_save_isnt_blocked() -> None:
    entered, release = threading.Event(), threading.Event()

    def blocking(target: S3Target, pair: S3Pair) -> S3Client:
        client = canned_factory(FakeS3())(target, pair)
        entered.set()
        release.wait(10)
        return client

    rig = rig_with(blocking)
    results: list[Any] = []
    first = threading.Thread(target=lambda: results.append(run_test(rig)))
    first.start()
    try:
        assert entered.wait(10)
        second = run_test(rig)
        assert (second.status_code, second.json()) == (409, {"error": "busy"})
        # the storage lock isn't held while the Test runs: a key save goes through at once
        saved = rig.client.put(
            "/api/secrets/s3-ro", json={"access_key_id": RO_ID, "secret_access_key": RO_SECRET}, headers=WRITE_HEADERS
        )
        assert saved.status_code == 204
    finally:
        release.set()
        first.join(10)
    assert results[0].status_code == 200
    assert run_test(rig).status_code == 200  # free again


def test_a_client_that_cant_be_built_is_an_internal_error_and_frees_the_test() -> None:
    def broken(target: S3Target, pair: S3Pair) -> S3Client:
        raise RuntimeError("no client")

    rig = rig_with(broken)
    client = rig.harness.signed_in_client(raise_server_exceptions=False)
    assert client.post(STORAGE_TEST_PATH, headers=WRITE_HEADERS).status_code == 500
    rig.service._client_factory = canned_factory(FakeS3())
    assert run_test(rig).status_code == 200


def test_an_error_inside_the_test_never_carries_its_text_to_the_500() -> None:
    """C3: botocore's own errors can name the endpoint (`Invalid endpoint: ...`); the 500's exception holds only the
    kind of error, with no chained context, and the Test is free again after it."""

    def broken(target: S3Target, pair: S3Pair) -> S3Client:
        raise ValueError("Invalid endpoint: https://s3.example.com/" + BUCKET)

    rig = rig_with(broken)
    with pytest.raises(StorageTestError) as caught:
        rig.client.post(STORAGE_TEST_PATH, headers=WRITE_HEADERS)
    error = caught.value
    assert str(error) == "The storage test stopped (ValueError)"
    assert "s3.example.com" not in repr(error) and BUCKET not in str(error)
    assert error.__suppress_context__ and error.__cause__ is None
    rig.service._client_factory = canned_factory(FakeS3())
    assert run_test(rig).status_code == 200  # the busy flag was freed


def test_the_real_factory_is_the_default() -> None:
    assert StorageService.development()._client_factory is make_client


def test_the_settings_and_keys_are_read_once_before_the_test() -> None:
    seen: list[S3Target] = []
    fake = FakeS3()

    def factory(target: S3Target, pair: S3Pair) -> S3Client:
        seen.append(target)
        return canned_factory(fake)(target, pair)

    rig = rig_with(factory, endpoint="https://s3.example.com/")
    assert run_test(rig).json()["ok"] is True
    assert seen == [S3Target("https://s3.example.com/", REGION, BUCKET)] * 2


def test_an_empty_endpoint_is_aws() -> None:
    seen: list[S3Target] = []

    def factory(target: S3Target, pair: S3Pair) -> S3Client:
        seen.append(target)
        return canned_factory(FakeS3())(target, pair)

    run_test(rig_with(factory, endpoint=""))
    assert seen[0].endpoint is None


def test_the_response_shape_is_fixed() -> None:
    body = run_test(canned_rig(FakeS3())).json()
    assert set(body) == {"ok", "tested_at", "latency_ms", "steps", "left_behind"}
    for step in body["steps"]:
        assert set(step) == {"step", "key_pair", "state", "latency_ms", "reason", "aws_code", "http_status"}
    assert json.dumps(body)  # plain JSON


def test_nothing_is_stored_by_a_test() -> None:
    rig = rig_with(canned_factory(FakeS3()))
    with closing(rig.service._connect()) as connection:
        before = connection.execute("SELECT key, value_json FROM setting ORDER BY key").fetchall()
    run_test(rig)
    with closing(rig.service._connect()) as connection:
        after = connection.execute("SELECT key, value_json FROM setting ORDER BY key").fetchall()
    assert before == after
    assert isinstance(sqlite3.sqlite_version, str)
