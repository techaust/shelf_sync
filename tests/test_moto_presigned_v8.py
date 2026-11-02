"""04-A V8, presigned URLs (m2.8): what moto 5.2.4's server does with a presigned GET, the kind of link the S3
extension on the test stack's store hands a buyer (V6). Server bound to 127.0.0.1 only, port 0; no live AWS.

The presigned URLs are made by a plain boto3 client **in this test only**: ShelfSync's own client never presigns
(m2.7's L-rules). Recorded: moto serves a good URL, but checks neither the expiry nor the signature, so a test against
the test stack can't prove that a link expires or that a changed one is refused; and with moto's IAM checks turned on,
every presigned GET fails with a 500 (moto reads an `Authorization` header a presigned GET doesn't have)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit

import botocore.auth
import httpx
import pytest
from botocore.config import Config
from moto import settings as moto_settings
from moto.server import ThreadedMotoServer

from shelfsync.apply.s3 import new_test_object
from tests.s3_support import (
    REGION,
    aws_setup_env,  # noqa: F401  (a fixture)
    create_bucket,
    s3_guard,  # noqa: F401  (autouse: the key guard)
    setup_client,
)

# moto's server keeps its state for the whole process: the bucket is emptied and deleted after each test.
BUCKET = f"shelfsync-v8-presigned-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def moto_endpoint(request: pytest.FixtureRequest) -> Iterator[str]:
    request.getfixturevalue("aws_setup_env")
    server = ThreadedMotoServer(ip_address="127.0.0.1", port=0, verbose=False)
    server.start()
    host, port = server.get_host_and_port()
    assert host == "127.0.0.1" and port != 0
    endpoint = f"http://127.0.0.1:{port}"
    try:
        create_bucket(endpoint, BUCKET)
        yield endpoint
        client = setup_client("s3", endpoint)
        try:
            for item in client.list_objects_v2(Bucket=BUCKET).get("Contents", []):
                client.delete_object(Bucket=BUCKET, Key=item["Key"])
            client.delete_bucket(Bucket=BUCKET)
        finally:
            client.close()
    finally:
        server.stop()


def presigning_client(endpoint: str, key_id: str = "testing", secret: str = "testing") -> Any:
    """A plain boto3 client, for this test only: SigV4, path-style (the endpoint is an IP address), no proxy."""
    import boto3

    return boto3.session.Session(region_name=REGION).client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=key_id,
        aws_secret_access_key=secret,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}, proxies={}),
    )


def put_test_object(endpoint: str) -> tuple[str, bytes]:
    key, body = new_test_object(datetime.now(UTC))
    client = presigning_client(endpoint)
    try:
        client.put_object(Bucket=BUCKET, Key=key, Body=body, ContentType="text/plain; charset=utf-8")
    finally:
        client.close()
    return key, body


def presigned_get(client: Any, key: str, seconds: int = 60) -> str:
    url: str = client.generate_presigned_url("get_object", Params={"Bucket": BUCKET, "Key": key}, ExpiresIn=seconds)
    return url


def signed_two_hours_ago(client: Any, key: str, monkeypatch: pytest.MonkeyPatch) -> str:
    """A 60-second URL signed two hours ago: expired on real S3 (botocore's signing clock moved back)."""
    real_now = botocore.auth.get_current_datetime
    with monkeypatch.context() as patch:
        patch.setattr(botocore.auth, "get_current_datetime", lambda: real_now() - timedelta(hours=2))
        url = presigned_get(client, key)
    signed_at = datetime.strptime(parse_qs(urlsplit(url).query)["X-Amz-Date"][0], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    assert datetime.now(UTC) - signed_at >= timedelta(hours=1), url  # the premise: long past its 60 s
    return url


def with_changed_signature(url: str) -> str:
    start = url.index("X-Amz-Signature=") + len("X-Amz-Signature=")
    changed = "0" if url[start] != "0" else "1"
    return url[:start] + changed + url[start + 1 :]


def fetch(url: str) -> httpx.Response:
    with httpx.Client(trust_env=False, timeout=10) as client:
        return client.get(url)


def test_v8_a_presigned_get_answers_200_and_the_bytes(moto_endpoint: str) -> None:
    key, body = put_test_object(moto_endpoint)
    client = presigning_client(moto_endpoint)
    try:
        url = presigned_get(client, key)
    finally:
        client.close()
    assert url.startswith(f"{moto_endpoint}/{BUCKET}/") and "X-Amz-Signature=" in url and "X-Amz-Expires=60" in url
    answer = fetch(url)
    assert answer.status_code == 200
    assert answer.content == body


def test_v8_recorded_moto_serves_an_expired_presigned_url(moto_endpoint: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Recorded: real S3 answers 403 AccessDenied ("Request has expired"); moto 5.2.4 serves the file. If moto starts
    refusing it, this test says so."""
    key, body = put_test_object(moto_endpoint)
    client = presigning_client(moto_endpoint)
    try:
        url = signed_two_hours_ago(client, key, monkeypatch)
    finally:
        client.close()
    answer = fetch(url)
    assert (answer.status_code, answer.content) == (200, body)


def test_v8_recorded_moto_serves_a_presigned_url_with_a_changed_signature_or_key(moto_endpoint: str) -> None:
    """Recorded: real S3 answers 403 SignatureDoesNotMatch for both; moto 5.2.4 serves the file, and a URL pointed at
    another key serves that other file."""
    key, body = put_test_object(moto_endpoint)
    other_key, other_body = put_test_object(moto_endpoint)
    client = presigning_client(moto_endpoint)
    try:
        url = presigned_get(client, key)
    finally:
        client.close()
    changed = fetch(with_changed_signature(url))
    assert (changed.status_code, changed.content) == (200, body)
    moved = fetch(url.replace(f"/{key}?", f"/{other_key}?"))
    assert (moved.status_code, moved.content) == (200, other_body)


def test_v8_recorded_with_moto_iam_checks_on_every_presigned_get_fails(
    moto_endpoint: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Recorded: turning on moto's IAM checks (`INITIAL_NO_AUTH_ACTION_COUNT=0`) doesn't make it check presigned URLs:
    a good one fails with 500 too (moto 5.2.4 reads the `Authorization` header, which a presigned GET hasn't got),
    while a signed SDK GET with the same user's keys still works. So no moto setting gives a real expiry test."""
    key, body = put_test_object(moto_endpoint)
    iam = setup_client("iam", moto_endpoint)
    user = f"v8-presigner-{uuid.uuid4().hex[:8]}"
    try:
        iam.create_user(UserName=user)
        iam.put_user_policy(
            UserName=user,
            PolicyName="v8-read",
            PolicyDocument=(
                '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":"s3:GetObject",'
                f'"Resource":"arn:aws:s3:::{BUCKET}/*"}}]}}'
            ),
        )
        access = iam.create_access_key(UserName=user)["AccessKey"]
    finally:
        iam.close()
    client = presigning_client(moto_endpoint, access["AccessKeyId"], access["SecretAccessKey"])
    # Set and put back by hand, not with monkeypatch: the fixture's teardown (which empties the bucket with the setup
    # keys) runs before monkeypatch's, and must run with the checks off again.
    before = moto_settings.INITIAL_NO_AUTH_ACTION_COUNT
    moto_settings.INITIAL_NO_AUTH_ACTION_COUNT = 0
    try:
        sdk = client.get_object(Bucket=BUCKET, Key=key)
        try:
            assert sdk["Body"].read() == body
        finally:
            sdk["Body"].close()
        good = fetch(presigned_get(client, key))
        expired = fetch(signed_two_hours_ago(client, key, monkeypatch))
    finally:
        moto_settings.INITIAL_NO_AUTH_ACTION_COUNT = before
        client.close()
    assert (good.status_code, expired.status_code) == (500, 500)
