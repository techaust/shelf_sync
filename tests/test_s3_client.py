"""SET-02, ERR-03, NFR-5: the S3 client of `apply/s3.py` (isolation, settings, the requests it sends) and the pure parts
(`classify`, `safe_aws_code`, the test key). No socket is opened here: every answer comes from `FakeS3` through a
`before-send` hook, so the requests are recorded exactly as they would leave the PC."""

import contextlib
import socket
import subprocess
import sys
import zlib
from base64 import b64encode
from collections.abc import Iterator
from dataclasses import dataclass
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
    maybe_sent = status >= 500 and code != "SlowDown"  # L13
    assert classify(client_error(code, status)) == Failure(reason, code, status, maybe_sent)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("status", "reason"),
    [(404, "not_found"), (403, "refused"), (400, "refused"), (503, "server_error"), (301, "bad_response")],
)
def test_a_code_botocore_made_up_from_the_status_is_not_kept(status: int, reason: str) -> None:
    """A HEAD answer has no body, so botocore uses the status as the Code: that is not S3's Code."""
    expected = Failure(reason, None, status, status >= 500)  # type: ignore[arg-type]
    assert classify(client_error(str(status), status)) == expected


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
        IncompleteReadError,
        ProxyConnectionError,
        ReadTimeoutError,
        ResponseStreamingError,
        SSLError,
    )

    url = "https://s3.example.com/bucket/key"
    assert classify(ConnectTimeoutError(endpoint_url=url)) == Failure("timeout")
    assert classify(ReadTimeoutError(endpoint_url=url)) == Failure("timeout", maybe_sent=True)  # sent, answer lost
    assert classify(TimeoutError()) == Failure("timeout")
    assert classify(SSLError(endpoint_url=url, error="bad")) == Failure("tls_error")
    assert classify(EndpointConnectionError(endpoint_url=url)) == Failure("unreachable")
    assert classify(ConnectionClosedError(endpoint_url=url)) == Failure("unreachable", maybe_sent=True)
    assert classify(ProxyConnectionError(proxy_url="x", error="x")) == Failure("unreachable")
    assert classify(ResponseStreamingError(error="x")) == Failure("unreachable", maybe_sent=True)
    assert classify(IncompleteReadError(actual_bytes=1, expected_bytes=2)) == Failure("mismatch")
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
    where = {
        "us_east_1_regional_endpoint": "regional",
        "use_arn_region": False,
        "s3_disable_multiregion_access_points": True,
        "use_accelerate_endpoint": False,
    }
    assert aws.s3 == {"addressing_style": "auto", **where} and custom.s3 == {"addressing_style": "path", **where}


def test_every_botocore_session_variable_is_closed() -> None:
    """C5: built from botocore's own table, so none reads the environment or a config file; the defaults are kept."""
    from botocore.configprovider import BOTOCORE_DEFAUT_SESSION_VARIABLES

    from shelfsync.apply.s3 import _isolated_session_vars

    variables = _isolated_session_vars()
    assert set(variables) == set(BOTOCORE_DEFAUT_SESSION_VARIABLES)
    for name, (config_key, env, default, _) in variables.items():
        assert (config_key, env) == (None, None), name
        if name not in ("profile", "config_file", "credentials_file", "data_path"):
            assert default == BOTOCORE_DEFAUT_SESSION_VARIABLES[name][2], name
    assert variables["profile"][2] is None and variables["data_path"][2] is None
    nowhere = variables["config_file"][2]
    assert nowhere == variables["credentials_file"][2] and not Path(nowhere).exists()
    assert Path(nowhere).parent.is_file()  # a child of a file: it can never exist


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


def test_a_short_answer_to_the_read_is_a_mismatch() -> None:
    """C6: a Content-Length larger than the bytes sent; the extra read finds the end, and botocore's length check
    runs."""
    fake = FakeS3()
    fake_default = fake._default

    def short(method: str, url: str, body: bytes) -> tuple[int, bytes, dict[str, str]]:
        status, payload, headers = fake_default(method, url, body)
        if method == "GET" and status == 200:
            headers = {**headers, "Content-Length": str(len(payload) + 5)}
        return status, payload, headers

    fake._default = short  # type: ignore[method-assign]
    outcome = run_canned(CUSTOM_TARGET, fake)
    assert (outcome.steps[1].state, outcome.steps[1].reason) == ("failed", "mismatch")
    assert outcome.steps[2].state == "passed"  # still deleted


def test_a_wrong_checksum_on_aws_is_a_mismatch() -> None:
    """C6: on AWS the read asks for the checksum (`x-amz-checksum-mode`); a wrong `x-amz-checksum-crc32` is caught only
    when the body is read to its end, which the extra read makes sure of."""
    fake = FakeS3()
    wrong = b64encode(zlib.crc32(b"not the body").to_bytes(4, "big")).decode()
    fake_default = fake._default

    def corrupt(method: str, url: str, body: bytes) -> tuple[int, bytes, dict[str, str]]:
        status, payload, headers = fake_default(method, url, body)
        if method == "GET" and status == 200:
            headers = {**headers, "x-amz-checksum-crc32": wrong}
        return status, payload, headers

    fake._default = corrupt  # type: ignore[method-assign]
    outcome = run_canned(AWS_TARGET, fake)
    assert fake.sent[1].headers.get("x-amz-checksum-mode") == "ENABLED"
    assert (outcome.steps[1].state, outcome.steps[1].reason) == ("failed", "mismatch")


def test_the_right_checksum_on_aws_passes() -> None:
    fake = FakeS3()
    fake_default = fake._default

    def checked(method: str, url: str, body: bytes) -> tuple[int, bytes, dict[str, str]]:
        status, payload, headers = fake_default(method, url, body)
        if method == "GET" and status == 200:
            headers = {**headers, "x-amz-checksum-crc32": b64encode(zlib.crc32(payload).to_bytes(4, "big")).decode()}
        return status, payload, headers

    fake._default = checked  # type: ignore[method-assign]
    assert run_canned(AWS_TARGET, fake).ok


def test_the_write_and_delete_refuse_any_key_but_a_test_key() -> None:
    """C7: an `if`, not an `assert`: nothing is sent for another key."""
    from shelfsync.apply.s3 import _delete, _write

    fake = FakeS3()
    client = canned_factory(fake)(CUSTOM_TARGET, RW_PAIR)
    try:
        for key in ("product-1.0.zip", "shelfsync-test/x.txt", "shelfsync-test/../product-1.0.zip"):
            with pytest.raises(ValueError, match="not a test key"):
                _write(client, BUCKET, key, b"x")
            with pytest.raises(ValueError, match="not a test key"):
                _delete(client, BUCKET, key)
    finally:
        client.close()
    assert fake.sent == []


def test_the_real_factory_against_an_outside_host_is_unreachable_and_recorded(no_outbound_network: list[str]) -> None:
    """C2: botocore turns the guard's error into `HTTPClientError` (`unreachable`), so only the record shows the
    attempt. Every other test fails on a non-empty record; this one empties it after checking."""
    rw, ro = make_client(CUSTOM_TARGET, RW_PAIR), make_client(CUSTOM_TARGET, RO_PAIR)
    try:
        outcome = run_storage_test(rw, ro, BUCKET, now=lambda: NOW)
    finally:
        rw.close()
        ro.close()
    assert (outcome.steps[0].state, outcome.steps[0].reason) == ("failed", "unreachable")
    assert no_outbound_network and all("s3.example.com" in item for item in no_outbound_network)
    no_outbound_network.clear()


# ---- isolation from the environment (L9) -----------------------------------------------------------------------------


@dataclass
class Hostile:
    csm: socket.socket  # a UDP listener on 127.0.0.1 where AWS_CSM_* would send client-side monitoring datagrams

    def csm_datagrams(self) -> list[bytes]:
        got: list[bytes] = []
        self.csm.setblocking(False)
        with contextlib.suppress(BlockingIOError, OSError):
            while True:
                got.append(self.csm.recv(65535))
        return got


@pytest.fixture
def csm_listener() -> Iterator[socket.socket]:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        yield sock


def junk_s3_and_session_variables(monkeypatch: pytest.MonkeyPatch, csm: socket.socket) -> None:
    """C5: the `s3` section's AWS_S3_* variables and other session variables set to junk, and client-side monitoring
    turned on towards a local UDP listener (it would carry the access key ID)."""
    for name, value in {
        "AWS_S3_US_EAST_1_REGIONAL_ENDPOINT": "junk",
        "AWS_S3_USE_ARN_REGION": "junk",
        "AWS_S3_DISABLE_MULTIREGION_ACCESS_POINTS": "junk",
        "AWS_S3_DISABLE_EXPRESS_SESSION_AUTH": "junk",
        "AWS_CSM_ENABLED": "true",
        "AWS_CSM_HOST": "127.0.0.1",
        "AWS_CSM_PORT": str(csm.getsockname()[1]),
        "AWS_CSM_CLIENT_ID": "evil",
        "AWS_REQUEST_MIN_COMPRESSION_SIZE_BYTES": "junk",
        "AWS_DISABLE_REQUEST_COMPRESSION": "junk",
        "AWS_ACCOUNT_ID_ENDPOINT_MODE": "junk",
        "AWS_IGNORE_CONFIGURED_ENDPOINT_URLS": "false",
        "AWS_METADATA_SERVICE_TIMEOUT": "junk",
        "AWS_METADATA_SERVICE_NUM_ATTEMPTS": "junk",
        "AWS_SIGV4A_SIGNING_REGION_SET": "junk",
        "AWS_AUTH_SCHEME_PREFERENCE": "junk",
        "AWS_STS_REGIONAL_ENDPOINTS": "junk",
        "AWS_ENDPOINT_DISCOVERY_ENABLED": "junk",
        "AWS_DISABLE_HOST_PREFIX_INJECTION": "junk",
        "AWS_PARAMETER_VALIDATION": "junk",
        "AWS_TCP_KEEPALIVE": "junk",
    }.items():
        monkeypatch.setenv(name, value)


def hostile_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, csm: socket.socket) -> Hostile:
    config = tmp_path / "config"
    config.write_text(
        "[default]\nregion = eu-west-3\nendpoint_url = https://evil-config.example\nretry_mode = adaptive\n"
        "max_attempts = 9\nrequest_checksum_calculation = when_supported\nca_bundle = "
        + str(tmp_path / "ca.pem")
        + "\n"
        "s3 =\n  addressing_style = virtual\n  use_accelerate_endpoint = true\n  us_east_1_regional_endpoint = legacy\n"
        "\n[profile missing-not]\nregion = eu-west-1\n",
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
    junk_s3_and_session_variables(monkeypatch, csm)
    return Hostile(csm)


US_EAST_1_TARGET = S3Target(None, "us-east-1", BUCKET)


@pytest.mark.parametrize(
    ("target", "host"),
    [
        (CUSTOM_TARGET, "s3.example.com"),
        (AWS_TARGET, f"{BUCKET}.s3.{REGION}.amazonaws.com"),
        # regional, never the global `s3.amazonaws.com` that `us_east_1_regional_endpoint = legacy` would give
        (US_EAST_1_TARGET, f"{BUCKET}.s3.us-east-1.amazonaws.com"),
    ],
    ids=["custom", "aws", "aws-us-east-1"],
)
def test_a_hostile_environment_changes_nothing(
    target: S3Target, host: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, csm_listener: socket.socket
) -> None:
    hostile = hostile_environment(monkeypatch, tmp_path, csm_listener)
    fake = FakeS3()
    client: Any = canned_factory(fake)(target, RW_PAIR)
    try:
        session = client._endpoint.http_session
        assert session._proxy_config._proxies == {}  # no proxy from HTTPS_PROXY or Windows
        assert session._verify is True  # not AWS_CA_BUNDLE, REQUESTS_CA_BUNDLE or the config file's ca_bundle
        assert client.meta.region_name == target.region
    finally:
        client.close()
    outcome = run_canned(target, fake)
    assert outcome.ok
    for sent in fake.sent:
        assert urlsplit(sent.url).netloc == host  # no fips, dualstack, accelerate, env or config endpoint
        assert "x-amz-security-token" not in {name.lower() for name in sent.headers}
        assert "AKIAEVIL" not in sent.headers["Authorization"]
        assert f"/{target.region}/s3/aws4_request" in sent.headers["Authorization"]
    if target.endpoint:
        assert not any(name.lower().startswith("x-amz-sdk-checksum") for name in fake.sent[0].headers)
    assert hostile.csm_datagrams() == []  # no client-side monitoring


def test_the_hostile_environment_does_break_a_client_that_isnt_isolated(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, csm_listener: socket.socket
) -> None:
    """The control: the same environment does reach a plain botocore client, so the test above proves something."""
    import botocore.exceptions
    import botocore.session

    hostile_environment(monkeypatch, tmp_path, csm_listener)
    with pytest.raises(botocore.exceptions.ProfileNotFound):
        botocore.session.Session().create_client("s3", region_name=REGION)
    monkeypatch.delenv("AWS_PROFILE")
    monkeypatch.delenv("AWS_DEFAULT_PROFILE")
    with pytest.raises(ValueError):  # the planted model is read (and isn't JSON)
        botocore.session.Session().create_client("s3", region_name=REGION)
    monkeypatch.delenv("AWS_DATA_PATH")
    with pytest.raises(ValueError):  # ~/.aws/models alone is enough
        botocore.session.Session().create_client("s3", region_name=REGION)


def test_the_junk_variables_do_reach_a_client_that_isnt_isolated(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, csm_listener: socket.socket
) -> None:
    """The control for C5: one junk variable at a time breaks a plain client, and client-side monitoring sends
    datagrams from one; ShelfSync's client with all of them set does neither (above, and at the end here)."""
    import botocore.exceptions
    import botocore.session

    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "none"))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "none"))
    for name in ("AWS_PROFILE", "AWS_DEFAULT_PROFILE", "AWS_DATA_PATH"):
        monkeypatch.delenv(name, raising=False)
    keys = {"aws_access_key_id": RW_PAIR.key_id, "aws_secret_access_key": RW_PAIR.secret}
    breaking = {
        "AWS_S3_US_EAST_1_REGIONAL_ENDPOINT": botocore.exceptions.InvalidS3UsEast1RegionalEndpointConfigError,
        "AWS_STS_REGIONAL_ENDPOINTS": botocore.exceptions.InvalidSTSRegionalEndpointsConfigError,
    }
    for name, error in breaking.items():
        monkeypatch.setenv(name, "junk")
        with pytest.raises(error):
            botocore.session.Session().create_client("s3", region_name="us-east-1", **keys)
        monkeypatch.delenv(name)
    hostile = Hostile(csm_listener)
    monkeypatch.setenv("AWS_CSM_ENABLED", "true")
    monkeypatch.setenv("AWS_CSM_HOST", "127.0.0.1")
    monkeypatch.setenv("AWS_CSM_PORT", str(csm_listener.getsockname()[1]))
    plain: Any = botocore.session.Session().create_client("s3", region_name=REGION, **keys)
    plain.meta.events.register_first("before-send.s3", FakeS3())
    try:
        with contextlib.suppress(Exception):  # the answer doesn't matter here: the monitoring datagram does
            plain.head_object(Bucket=BUCKET, Key="shelfsync-test/x")
    finally:
        plain.close()
    sent = hostile.csm_datagrams()
    assert sent and any(RW_PAIR.key_id.encode() in datagram for datagram in sent)  # it even carries the key ID
    junk_s3_and_session_variables(monkeypatch, csm_listener)
    assert run_canned(US_EAST_1_TARGET, FakeS3()).ok
    assert hostile.csm_datagrams() == []  # ShelfSync's client sends none


def test_a_hostile_environment_does_not_raise_the_retries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, csm_listener: socket.socket
) -> None:
    """`AWS_MAX_ATTEMPTS=9` and `max_attempts = 9` in a config file are ignored: two attempts, then the answer."""
    hostile_environment(monkeypatch, tmp_path, csm_listener)
    fake = FakeS3()
    for n in range(1, 10):
        fake.script[("PUT", n)] = (500, b"", {})
    outcome = run_canned(CUSTOM_TARGET, fake)
    assert fake.methods().count("PUT") == 2
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
