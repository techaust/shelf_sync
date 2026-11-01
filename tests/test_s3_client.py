"""SET-02, ERR-03, NFR-5: the S3 client of `apply/s3.py` (isolation, settings, the requests it sends) and the pure parts
(`classify`, `safe_aws_code`, the test key). No socket is opened here: every answer comes from `FakeS3` through a
`before-send` hook, so the requests are recorded exactly as they would leave the PC."""

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest
from hypothesis import given
from hypothesis import strategies as st

from shelfsync.apply.s3 import (
    CONNECT_SECONDS,
    READ_SECONDS,
    TEST_KEY,
    TEST_PREFIX,
    Failure,
    S3Target,
    classify,
    client_config,
    make_client,
    new_test_object,
    run_storage_test,
    safe_aws_code,
)
from shelfsync.secure.redact import register_secret
from tests.s3_support import (
    AWS_TARGET,
    BUCKET,
    CUSTOM_ENDPOINT,
    CUSTOM_TARGET,
    REGION,
    RO_PAIR,
    RW_PAIR,
    FakeS3,
    canned_factory,
    s3_guard,  # noqa: F401  (autouse: the key guard and the outbound record)
)
from tests.storage_support import RW_ID, RW_SECRET

NOW = datetime(2026, 11, 2, 10, 0, 0, tzinfo=UTC)


def run_canned(target: S3Target, fake: FakeS3) -> Any:
    factory = canned_factory(fake)
    rw, ro = factory(target, RW_PAIR), factory(target, RO_PAIR)
    try:
        return run_storage_test(rw, ro, target.bucket, now=lambda: NOW)
    finally:
        rw.close()
        ro.close()


def client_error(code: str | None, status: int, message: str = "arn:aws:iam::123456789012:user/x") -> Exception:
    from botocore.exceptions import ClientError

    error: dict[str, Any] = {"Message": message}
    if code is not None:
        error["Code"] = code
    return ClientError({"Error": error, "ResponseMetadata": {"HTTPStatusCode": status}}, "PutObject")


# ---- classify: every reason ------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "status", "reason"),
    [
        ("AccessDenied", 403, "access_denied"),
        ("AllAccessDisabled", 403, "access_denied"),
        ("InvalidAccessKeyId", 403, "key_unknown"),
        ("SignatureDoesNotMatch", 403, "secret_wrong"),
        ("RequestTimeTooSkewed", 403, "clock_wrong"),
        ("NoSuchBucket", 404, "bucket_missing"),
        ("AuthorizationHeaderMalformed", 400, "wrong_region"),
        ("PermanentRedirect", 301, "wrong_region"),
        ("IllegalLocationConstraintException", 400, "wrong_region"),
        ("NoSuchKey", 404, "not_found"),
        ("SlowDown", 503, "server_error"),
        ("InternalError", 500, "server_error"),
        ("InvalidRequest", 400, "refused"),
        ("EntityTooLarge", 400, "refused"),
        ("Weird", 302, "bad_response"),
    ],
)
def test_classify_maps_each_s3_code(code: str, status: int, reason: str) -> None:
    assert classify(client_error(code, status)) == Failure(reason, code, status)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("status", "reason"),
    [(404, "not_found"), (403, "refused"), (400, "refused"), (503, "server_error"), (301, "bad_response")],
)
def test_a_code_botocore_made_up_from_the_status_is_not_kept(status: int, reason: str) -> None:
    """A HEAD answer has no body, so botocore uses the status as the Code: that is not S3's Code."""
    assert classify(client_error(str(status), status)) == Failure(reason, None, status)  # type: ignore[arg-type]


def test_a_client_error_without_a_status_is_a_bad_response() -> None:
    from botocore.exceptions import ClientError

    assert classify(ClientError({"Error": {"Code": "Odd"}}, "GetObject")) == Failure("bad_response", "Odd", None)
    assert classify(ClientError({}, "GetObject")).reason == "bad_response"


def test_classify_maps_the_connection_errors() -> None:
    from botocore.exceptions import (
        ConnectionClosedError,
        ConnectTimeoutError,
        EndpointConnectionError,
        FlexibleChecksumError,
        ProxyConnectionError,
        ReadTimeoutError,
        ResponseStreamingError,
        SSLError,
    )

    url = "https://s3.example.com/bucket/key"
    assert classify(ConnectTimeoutError(endpoint_url=url)) == Failure("timeout")
    assert classify(ReadTimeoutError(endpoint_url=url)) == Failure("timeout")
    assert classify(TimeoutError()) == Failure("timeout")
    assert classify(SSLError(endpoint_url=url, error="bad")) == Failure("tls_error")
    assert classify(EndpointConnectionError(endpoint_url=url)) == Failure("unreachable")
    assert classify(ConnectionClosedError(endpoint_url=url)) == Failure("unreachable")
    assert classify(ProxyConnectionError(proxy_url="x", error="x")) == Failure("unreachable")
    assert classify(ResponseStreamingError(error="x")) == Failure("unreachable")
    assert classify(FlexibleChecksumError(error_msg="x")) == Failure("mismatch")
    assert classify(ValueError("anything else")) == Failure("bad_response")


def test_a_parser_error_is_a_bad_response() -> None:
    from botocore.parsers import ResponseParserError

    assert classify(ResponseParserError("Unable to parse")) == Failure("bad_response")


# ---- safe_aws_code ---------------------------------------------------------------------------------------------------


def test_safe_aws_code_keeps_a_plain_code_only() -> None:
    assert safe_aws_code("AccessDenied") == "AccessDenied"
    assert safe_aws_code("Client.Error.1") == "Client.Error.1"
    for bad in (None, 403, "", "A" * 65, "Access Denied", "<Code>", "arn:aws:iam::1:user/x", "x/y"):
        assert safe_aws_code(bad) is None


def test_safe_aws_code_never_returns_a_registered_secret_or_a_key_id() -> None:
    register_secret(RW_SECRET.replace("/", "").replace("+", "").replace("=", ""))
    assert safe_aws_code(RW_SECRET.replace("/", "").replace("+", "").replace("=", "")) is None
    assert safe_aws_code(RW_ID) == RW_ID  # not registered, and 19 characters: not an AWS key ID's shape
    register_secret(RW_ID)
    assert safe_aws_code(RW_ID) is None
    assert safe_aws_code("AKIA" + "ABCDEFGHIJKLMNOP") is None  # an AWS key ID's shape: masked even unregistered


@given(st.text(max_size=80) | st.from_regex(r"[A-Za-z0-9.]{1,70}", fullmatch=True))
def test_safe_aws_code_is_a_pattern_match_or_none(code: str) -> None:
    result = safe_aws_code(code)
    if result is not None:
        assert result == code and 1 <= len(result) <= 64
        assert all(c.isascii() and (c.isalnum() or c == ".") for c in result)


@given(st.from_regex(r"[A-Za-z0-9]{16,64}", fullmatch=True))
def test_a_registered_secret_is_never_passed_on_as_a_code(secret: str) -> None:
    register_secret(secret)
    assert safe_aws_code(secret) is None


# ---- the test key ----------------------------------------------------------------------------------------------------


def test_the_test_key_is_under_its_prefix_and_new_each_time() -> None:
    key, body = new_test_object(NOW)
    again, _ = new_test_object(NOW)
    assert key.startswith(TEST_PREFIX + "20261102T100000Z-") and key.endswith(".txt")
    assert TEST_KEY.fullmatch(key) and key != again
    assert body == b"ShelfSync storage test " + key[-36:-4].encode() + b"\n"


# ---- the client: its settings ----------------------------------------------------------------------------------------


def test_the_config_is_explicit_and_follows_the_endpoint_kind() -> None:
    aws, custom = client_config(AWS_TARGET), client_config(CUSTOM_TARGET)
    for config in (aws, custom):
        assert (config.connect_timeout, config.read_timeout) == (CONNECT_SECONDS, READ_SECONDS) == (5, 10)
        assert config.retries == {"mode": "standard", "total_max_attempts": 2}
        assert config.proxies == {}
        assert config.ignore_configured_endpoint_urls is True
        assert config.use_fips_endpoint is False and config.use_dualstack_endpoint is False
        assert config.defaults_mode == "legacy" and config.signature_version == "s3v4"
    assert aws.request_checksum_calculation == aws.response_checksum_validation == "when_supported"
    assert custom.request_checksum_calculation == custom.response_checksum_validation == "when_required"
    assert aws.s3 == {"addressing_style": "auto"} and custom.s3 == {"addressing_style": "path"}


def test_a_client_has_no_proxy_and_the_default_trust() -> None:
    client: Any = make_client(CUSTOM_TARGET, RW_PAIR)
    try:
        session = client._endpoint.http_session
        assert session._proxy_config._proxies == {}
        assert session._verify is True
        assert client.meta.region_name == REGION
    finally:
        client.close()


# ---- the requests it sends (V10, L5, L6) -----------------------------------------------------------------------------


def test_a_custom_endpoint_gets_path_style_md5_and_no_flexible_checksum() -> None:
    """V10: for a non-AWS endpoint no `x-amz-sdk-checksum-algorithm` or `x-amz-checksum-*` header is sent, and the
    write carries `Content-MD5`; path style, to the configured host."""
    fake = FakeS3()
    outcome = run_canned(CUSTOM_TARGET, fake)
    assert outcome.ok
    assert fake.methods() == ["PUT", "GET", "DELETE", "HEAD"]
    for sent in fake.sent:
        parts = urlsplit(sent.url)
        assert f"{parts.scheme}://{parts.netloc}" == CUSTOM_ENDPOINT
        assert parts.path == f"/{BUCKET}/{outcome.key}"
        lowered = {name.lower() for name in sent.headers}
        assert not any(name.startswith(("x-amz-checksum", "x-amz-sdk-checksum")) for name in lowered), sent
        assert "x-amz-security-token" not in lowered
        assert f"Credential={RW_ID if sent.method != 'GET' else RO_PAIR.key_id}/" in sent.headers["Authorization"]
    put = fake.sent[0]
    assert put.headers["Content-MD5"]
    assert put.headers["Content-Type"] == "text/plain; charset=utf-8"
    assert put.body.startswith(b"ShelfSync storage test ")


@pytest.mark.parametrize(("bucket", "host_style"), [("plain-bucket", True), ("my.bucket", False)])
def test_aws_addressing_is_recorded_for_plain_and_dotted_buckets(bucket: str, host_style: bool) -> None:
    """L6, recorded: on AWS with `auto`, botocore puts a plain bucket name in the host and a dotted one in the path (a
    dotted name can't match the `*.s3.<region>.amazonaws.com` certificate). AWS also gets the 1.36 default: a CRC32
    checksum on the write, beside the Content-MD5 ShelfSync sends."""
    fake = FakeS3()
    outcome = run_canned(S3Target(None, REGION, bucket), fake)
    assert outcome.ok
    for sent in fake.sent:
        parts = urlsplit(sent.url)
        if host_style:
            assert parts.netloc == f"{bucket}.s3.{REGION}.amazonaws.com" and parts.path == f"/{outcome.key}"
        else:
            assert parts.netloc == f"s3.{REGION}.amazonaws.com" and parts.path == f"/{bucket}/{outcome.key}"
    put = fake.sent[0]
    assert put.headers["Content-MD5"]
    assert put.headers.get("x-amz-sdk-checksum-algorithm") == "CRC32"


# ---- isolation from the environment (L9) -----------------------------------------------------------------------------


def hostile_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.write_text(
        "[default]\nregion = eu-west-3\nendpoint_url = https://evil-config.example\nretry_mode = adaptive\n"
        "max_attempts = 9\nrequest_checksum_calculation = when_supported\nca_bundle = "
        + str(tmp_path / "ca.pem")
        + "\n"
        "s3 =\n  addressing_style = virtual\n\n[profile missing-not]\nregion = eu-west-1\n",
        encoding="utf-8",
    )
    (tmp_path / "ca.pem").write_text("not a certificate", encoding="utf-8")
    credentials = tmp_path / "credentials"
    credentials.write_text(
        "[default]\naws_access_key_id = AKIAEVILEVILEVIL0000\naws_secret_access_key = evilsecretevilsecret\n",
        encoding="utf-8",
    )
    # a planted S3 model that would break the client if it were ever loaded (AWS_DATA_PATH and ~/.aws/models)
    for root in (tmp_path / "data", tmp_path / "home-models"):
        planted = root / "s3" / "2099-01-01"
        planted.mkdir(parents=True)
        (planted / "service-2.json").write_text("{not json", encoding="utf-8")
    import botocore.loaders

    monkeypatch.setattr(botocore.loaders.Loader, "CUSTOMER_DATA_PATH", str(tmp_path / "home-models"))
    for name, value in {
        "AWS_ENDPOINT_URL": "https://evil-endpoint.example",
        "AWS_ENDPOINT_URL_S3": "https://evil-s3.example",
        "AWS_PROFILE": "missing",
        "AWS_DEFAULT_PROFILE": "missing",
        "AWS_CONFIG_FILE": str(config),
        "AWS_SHARED_CREDENTIALS_FILE": str(credentials),
        "AWS_DATA_PATH": str(tmp_path / "data"),
        "AWS_USE_FIPS_ENDPOINT": "true",
        "AWS_USE_DUALSTACK_ENDPOINT": "true",
        "AWS_CA_BUNDLE": str(tmp_path / "ca.pem"),
        "REQUESTS_CA_BUNDLE": str(tmp_path / "ca.pem"),
        "HTTPS_PROXY": "http://proxy.evil.example:8080",
        "HTTP_PROXY": "http://proxy.evil.example:8080",
        "AWS_ACCESS_KEY_ID": "AKIAEVILEVILEVIL1111",
        "AWS_SECRET_ACCESS_KEY": "evilsecretevilsecretevilsecret",
        "AWS_SESSION_TOKEN": "evil-session-token",
        "AWS_REQUEST_CHECKSUM_CALCULATION": "when_supported",
        "AWS_RESPONSE_CHECKSUM_VALIDATION": "when_supported",
        "AWS_RETRY_MODE": "adaptive",
        "AWS_MAX_ATTEMPTS": "9",
        "AWS_DEFAULTS_MODE": "standard",
        "AWS_REGION": "eu-west-3",
        "AWS_DEFAULT_REGION": "eu-west-3",
    }.items():
        monkeypatch.setenv(name, value)


@pytest.mark.parametrize("target", [CUSTOM_TARGET, AWS_TARGET], ids=["custom", "aws"])
def test_a_hostile_environment_changes_nothing(
    target: S3Target, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    hostile_environment(monkeypatch, tmp_path)
    fake = FakeS3()
    client: Any = canned_factory(fake)(target, RW_PAIR)
    try:
        session = client._endpoint.http_session
        assert session._proxy_config._proxies == {}  # no proxy from HTTPS_PROXY or Windows
        assert session._verify is True  # not AWS_CA_BUNDLE, REQUESTS_CA_BUNDLE or the config file's ca_bundle
        assert client.meta.region_name == REGION
    finally:
        client.close()
    outcome = run_canned(target, fake)
    assert outcome.ok
    expected_host = "s3.example.com" if target.endpoint else f"{BUCKET}.s3.{REGION}.amazonaws.com"
    for sent in fake.sent:
        assert urlsplit(sent.url).netloc == expected_host  # no fips, dualstack, env or config endpoint
        assert "x-amz-security-token" not in {name.lower() for name in sent.headers}
        assert "AKIAEVIL" not in sent.headers["Authorization"]
        assert f"/{REGION}/s3/aws4_request" in sent.headers["Authorization"]
    if target.endpoint:
        assert not any(name.lower().startswith("x-amz-sdk-checksum") for name in fake.sent[0].headers)


def test_the_hostile_environment_does_break_a_client_that_isnt_isolated(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The control: the same environment does reach a plain botocore client, so the test above proves something."""
    import botocore.exceptions
    import botocore.session

    hostile_environment(monkeypatch, tmp_path)
    with pytest.raises(botocore.exceptions.ProfileNotFound):
        botocore.session.Session().create_client("s3", region_name=REGION)
    monkeypatch.delenv("AWS_PROFILE")
    monkeypatch.delenv("AWS_DEFAULT_PROFILE")
    with pytest.raises(ValueError):  # the planted model is read (and isn't JSON)
        botocore.session.Session().create_client("s3", region_name=REGION)
    monkeypatch.delenv("AWS_DATA_PATH")
    with pytest.raises(ValueError):  # ~/.aws/models alone is enough
        botocore.session.Session().create_client("s3", region_name=REGION)


def test_a_hostile_environment_does_not_raise_the_retries(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """`AWS_MAX_ATTEMPTS=9` and `max_attempts = 9` in a config file are ignored: two attempts, then the answer."""
    hostile_environment(monkeypatch, tmp_path)
    fake = FakeS3()
    for n in range(1, 10):
        fake.script[("PUT", n)] = (500, b"", {})
    outcome = run_canned(CUSTOM_TARGET, fake)
    assert fake.methods() == ["PUT", "PUT"]
    assert outcome.steps[0].reason == "server_error" and outcome.steps[0].http_status == 500


# ---- start-up doesn't load botocore (L10, NFR-3) ---------------------------------------------------------------------


def test_starting_the_server_module_does_not_import_botocore() -> None:
    backend = Path(__file__).resolve().parents[1] / "backend"
    code = (
        "import sys; import shelfsync.server, shelfsync.api.app, shelfsync.api.storage; "
        "print(sorted(m for m in sys.modules if m.split('.')[0] in ('botocore', 'boto3', 's3transfer')))"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", f"import sys; sys.path.insert(0, {str(backend)!r}); {code}"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert result.stdout.strip() == "[]"
