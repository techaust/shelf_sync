"""SET-02, V8 (partly): the Storage Test and ShelfSync's S3 client through the real HTTP stack, against moto's
server bound to 127.0.0.1 only (`ThreadedMotoServer(ip_address="127.0.0.1", port=0)`, never its `0.0.0.0` default).
No live AWS, bucket or store is ever reached."""

import base64
import hashlib
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from moto.server import ThreadedMotoServer

from shelfsync.api.storage import STORAGE_TEST_PATH
from shelfsync.apply.s3 import S3Target, make_client, new_test_object
from shelfsync.secure.credentials import S3Credentials
from tests.s3_support import (
    REGION,
    RO_PAIR,
    RW_PAIR,
    aws_setup_env,  # noqa: F401  (a fixture)
    create_bucket,
    keys_in,
    s3_guard,  # noqa: F401  (autouse: the key guard)
)
from tests.storage_support import GOOD_SETTINGS, make_storage_rig
from tests.support import WRITE_HEADERS


@pytest.fixture
def moto_endpoint(request: pytest.FixtureRequest) -> Iterator[str]:
    request.getfixturevalue("aws_setup_env")
    server = ThreadedMotoServer(ip_address="127.0.0.1", port=0, verbose=False)
    server.start()
    host, port = server.get_host_and_port()
    assert host == "127.0.0.1" and port != 0
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.stop()


def new_bucket(endpoint: str) -> str:
    """moto's server keeps its buckets for the whole process: each test gets its own."""
    bucket = f"shelfsync-v8-{uuid.uuid4().hex[:12]}"
    create_bucket(endpoint, bucket)
    return bucket


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost"])
def test_the_full_test_passes_through_the_real_http_stack(moto_endpoint: str, host: str) -> None:
    bucket = new_bucket(moto_endpoint)
    endpoint = moto_endpoint.replace("127.0.0.1", host)
    rig = make_storage_rig()
    settings = {**GOOD_SETTINGS, "s3_endpoint": endpoint, "s3_region": REGION, "s3_bucket": bucket}
    assert rig.client.put("/api/settings/storage", json=settings, headers=WRITE_HEADERS).status_code == 200
    credentials = S3Credentials(rig.secrets)
    credentials.save("rw", RW_PAIR.key_id, RW_PAIR.secret)
    credentials.save("ro", RO_PAIR.key_id, RO_PAIR.secret)
    body = rig.client.post(STORAGE_TEST_PATH, headers=WRITE_HEADERS).json()
    assert body["ok"] is True, body
    assert [step["state"] for step in body["steps"]] == ["passed"] * 3
    assert keys_in(bucket, moto_endpoint) == []


def test_v8_content_md5_head_and_a_range_get_through_shelfsyncs_client(moto_endpoint: str) -> None:
    """V8: `put_object` with `ContentMD5` is accepted, `head_object` answers the size and the MD5 ETag, and a ranged
    GET returns exactly the asked bytes (APL-02's upload path and the M4/M5 range reads)."""
    bucket = new_bucket(moto_endpoint)
    client = make_client(S3Target(moto_endpoint, REGION, bucket), RW_PAIR)
    key, body = new_test_object(datetime.now(UTC))
    digest = hashlib.md5(body, usedforsecurity=False)
    try:
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=body,
            ContentType="text/plain; charset=utf-8",
            ContentMD5=base64.b64encode(digest.digest()).decode("ascii"),
        )
        head = client.head_object(Bucket=bucket, Key=key)
        assert head["ContentLength"] == len(body)
        assert head["ETag"] == f'"{digest.hexdigest()}"'
        ranged = client.get_object(Bucket=bucket, Key=key, Range="bytes=0-8")
        try:
            assert ranged["Body"].read() == body[:9]
        finally:
            ranged["Body"].close()
        assert ranged["ResponseMetadata"]["HTTPStatusCode"] == 206
        assert ranged["ContentRange"] == f"bytes 0-8/{len(body)}"
    finally:
        client.delete_object(Bucket=bucket, Key=key)
        client.close()
    assert keys_in(bucket, moto_endpoint) == []


def test_v8_recorded_moto_does_not_reject_a_wrong_content_md5(moto_endpoint: str) -> None:
    """Recorded for M5: moto 5.2.4 accepts a `Content-MD5` that doesn't match the body (no `BadDigest`), so APL-02's
    corrupted-body test needs a Stubber or `FakeS3`, not moto. If moto starts refusing it, this test says so."""
    bucket = new_bucket(moto_endpoint)
    client = make_client(S3Target(moto_endpoint, REGION, bucket), RW_PAIR)
    key, body = new_test_object(datetime.now(UTC))
    wrong = base64.b64encode(hashlib.md5(b"another body", usedforsecurity=False).digest()).decode("ascii")
    try:
        answer = client.put_object(Bucket=bucket, Key=key, Body=body, ContentMD5=wrong)
        assert answer["ResponseMetadata"]["HTTPStatusCode"] == 200
    finally:
        client.delete_object(Bucket=bucket, Key=key)
        client.close()
