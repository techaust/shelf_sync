"""Helpers for the Storage Test (M2.7). No live AWS, bucket or store is ever reached:

- `s3_guard` (autouse in every S3 test module, imported with `# noqa: F401`): records every S3 operation any botocore
  client makes and fails the test if one ever PUTs or DELETEs a key outside `shelfsync-test/<pattern>`. It also fails
  the test on any blocked outbound attempt: botocore wraps whatever a socket raises in its own errors, so the conftest
  guard's failure could otherwise be read as `unreachable` and pass.
- `FakeS3`: canned answers through a `before-send` hook on a real ShelfSync client (no socket): a tiny object store
  that records each request, with per-call overrides for what moto can't model (SlowDown, RequestTimeTooSkewed, ...).
- `aws_setup_env`: an environment for moto's own setup clients that reads nothing from this PC's `~/.aws`.
- The two IAM policies of 06 section 5, exactly, and IAM users holding them (moto, in-process).
- `ScriptedServer`: a plain HTTP server on 127.0.0.1 whose answers can be held back (timeouts, a late write).
"""

import io
import json
import re
import socket
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import pytest

from shelfsync.apply.s3 import TEST_KEY, ClientFactory, S3Client, S3Target, make_client
from shelfsync.secure.credentials import S3Pair
from tests.conftest import OutboundNetworkBlocked
from tests.storage_support import RO_ID, RO_SECRET, RW_ID, RW_SECRET

BUCKET = "shelfsync-test-bucket"
REGION = "ap-south-1"
AWS_TARGET = S3Target(None, REGION, BUCKET)
CUSTOM_ENDPOINT = "https://s3.example.com"
CUSTOM_TARGET = S3Target(CUSTOM_ENDPOINT, REGION, BUCKET)
RW_PAIR = S3Pair(RW_ID, RW_SECRET)
RO_PAIR = S3Pair(RO_ID, RO_SECRET)

# Operations that change an object: each must name a Storage Test key, or the test fails.
_OBJECT_WRITES = re.compile(r"(Put|Delete|Copy|Create|Upload|Complete|Restore|Abort)\w*")


# ---- the guard -------------------------------------------------------------------------------------------------------


@dataclass
class S3Guard:
    calls: list[tuple[str, str | None]] = field(default_factory=list)  # (operation, Key)
    blocked: list[str] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def operations(self) -> list[str]:
        with self.lock:
            return [name for name, _ in self.calls]


@pytest.fixture(autouse=True)
def s3_guard(no_outbound_network: None, monkeypatch: pytest.MonkeyPatch) -> Iterator[S3Guard]:
    import botocore.session

    guard = S3Guard()
    real_create_client = botocore.session.Session.create_client

    def create_client(self: Any, *args: Any, **kwargs: Any) -> Any:
        client = real_create_client(self, *args, **kwargs)

        def record(params: dict[str, Any], model: Any, **_: Any) -> None:
            key = params.get("Key")
            with guard.lock:
                guard.calls.append((model.name, key if isinstance(key, str) else None))

        client.meta.events.register("before-parameter-build.s3", record)
        return client

    monkeypatch.setattr(botocore.session.Session, "create_client", create_client)

    guarded_getaddrinfo = socket.getaddrinfo
    guarded_connect = socket.socket.connect

    def getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            return guarded_getaddrinfo(host, *args, **kwargs)
        except OutboundNetworkBlocked:
            guard.blocked.append(str(host))
            raise

    def connect(self: socket.socket, address: Any) -> None:
        try:
            guarded_connect(self, address)
        except OutboundNetworkBlocked:
            guard.blocked.append(str(address))
            raise

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(socket.socket, "connect", connect)
    yield guard
    assert guard.blocked == [], f"outbound attempts were made: {guard.blocked}"
    with guard.lock:
        for name, key in guard.calls:
            if _OBJECT_WRITES.fullmatch(name) and name not in ("CreateBucket", "DeleteBucket"):
                assert key is not None and TEST_KEY.fullmatch(key), f"{name} on a key that isn't a test key: {key}"


@pytest.fixture
def aws_setup_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """For moto's setup clients (IAM, CreateBucket): fake keys, and no `~/.aws` file or AWS_* variable of this PC."""
    import os

    for name in list(os.environ):
        if name.startswith("AWS_") or name.upper() in ("HTTPS_PROXY", "HTTP_PROXY", "REQUESTS_CA_BUNDLE"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "no-aws-config"))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "no-aws-credentials"))
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)


def setup_client(service: str, endpoint_url: str | None = None) -> Any:
    """A boto3 client for moto's setup (never one of ShelfSync's). Use with `aws_setup_env`."""
    import boto3

    return boto3.session.Session(region_name=REGION).client(service, endpoint_url=endpoint_url)


def create_bucket(endpoint_url: str | None = None, bucket: str = BUCKET) -> None:
    setup_client("s3", endpoint_url).create_bucket(
        Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": REGION}
    )


def keys_in(bucket: str = BUCKET, endpoint_url: str | None = None) -> list[str]:
    answer = setup_client("s3", endpoint_url).list_objects_v2(Bucket=bucket)
    return [item["Key"] for item in answer.get("Contents", [])]


# ---- the two policies of 06 section 5, exactly -----------------------------------------------------------------------


def rw_policy(
    bucket: str = BUCKET, actions: tuple[str, ...] = ("s3:GetObject", "s3:PutObject", "s3:DeleteObject")
) -> str:
    return json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "ShelfSyncObjects",
                    "Effect": "Allow",
                    "Action": list(actions),
                    "Resource": f"arn:aws:s3:::{bucket}/*",
                },
                {
                    "Sid": "ShelfSyncList",
                    "Effect": "Allow",
                    "Action": "s3:ListBucket",
                    "Resource": f"arn:aws:s3:::{bucket}",
                },
            ],
        }
    )


def ro_policy(bucket: str = BUCKET) -> str:
    return json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "ShelfSyncRead",
                    "Effect": "Allow",
                    "Action": "s3:GetObject",
                    "Resource": f"arn:aws:s3:::{bucket}/*",
                },
                {
                    "Sid": "ShelfSyncList",
                    "Effect": "Allow",
                    "Action": "s3:ListBucket",
                    "Resource": f"arn:aws:s3:::{bucket}",
                },
            ],
        }
    )


def iam_user(name: str, policy: str) -> S3Pair:
    """A moto IAM user holding `policy` inline; its new access key."""
    iam = setup_client("iam")
    iam.create_user(UserName=name)
    iam.put_user_policy(UserName=name, PolicyName=f"{name}-policy", PolicyDocument=policy)
    key = iam.create_access_key(UserName=name)["AccessKey"]
    return S3Pair(key["AccessKeyId"], key["SecretAccessKey"])


# ---- canned answers (no socket) --------------------------------------------------------------------------------------


@dataclass
class Sent:
    method: str
    url: str
    headers: dict[str, str]
    body: bytes


class _Raw(io.BytesIO):
    def stream(self, **_: Any) -> Iterator[bytes]:
        chunk = self.read()
        while chunk:
            yield chunk
            chunk = self.read()


def error_xml(code: str, message: str = "Account 123456789012 arn:aws:iam::123456789012:user/owner") -> bytes:
    """An S3 error body. The default Message holds an account ID and an ARN, which must never be passed on."""
    return f"<?xml version='1.0'?><Error><Code>{code}</Code><Message>{message}</Message></Error>".encode()


Answer = tuple[int, bytes, dict[str, str]] | BaseException


def _decode_aws_chunked(body: bytes) -> bytes:
    out = b""
    rest = body
    while rest:
        size_line, _, rest = rest.partition(b"\r\n")
        size = int(size_line.split(b";")[0], 16)
        if size == 0:
            break
        out += rest[:size]
        rest = rest[size + 2 :]
    return out


class FakeS3:
    """Answers S3 requests from a dict, like a bucket would. `script[(method, n)]` overrides the n-th (1-based) request
    of that method with a status, body and headers, or an exception to raise (as a socket error would be)."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.sent: list[Sent] = []
        self.script: dict[tuple[str, int], Answer] = {}
        self.counts: dict[str, int] = {}
        self.lock = threading.Lock()

    def __call__(self, request: Any, **_: Any) -> Any:
        from botocore.awsrequest import AWSResponse

        body = request.body
        if hasattr(body, "read"):
            body = body.read()
        body = body or b""
        if isinstance(body, str):
            body = body.encode()
        headers = {str(k): (v.decode() if isinstance(v, bytes) else str(v)) for k, v in request.headers.items()}
        if headers.get("Content-Encoding") == "aws-chunked":
            body = _decode_aws_chunked(body)
        with self.lock:
            self.sent.append(Sent(request.method, request.url, headers, body))
            n = self.counts[request.method] = self.counts.get(request.method, 0) + 1
            scripted = self.script.get((request.method, n))
        if isinstance(scripted, BaseException):
            raise scripted
        status, payload, extra = scripted if scripted is not None else self._default(request.method, request.url, body)
        all_headers = {"Content-Length": str(len(payload)), **extra}
        if request.method == "HEAD":
            payload = b""
        return AWSResponse(request.url, status, all_headers, _Raw(payload))

    def _default(self, method: str, url: str, body: bytes) -> tuple[int, bytes, dict[str, str]]:
        path = unquote(urlsplit(url).path)
        with self.lock:
            if method == "PUT":
                self.objects[path] = body
                return 200, b"", {"ETag": '"etag"'}
            if method == "DELETE":
                self.objects.pop(path, None)
                return 204, b"", {}
            stored = self.objects.get(path)
        if stored is None:
            return 404, error_xml("NoSuchKey") if method == "GET" else b"", {}
        return 200, stored, {"Content-Type": "text/plain; charset=utf-8"}

    def methods(self) -> list[str]:
        return [item.method for item in self.sent]


def canned_factory(fake: FakeS3) -> ClientFactory:
    """ShelfSync's own client factory, with `fake` answering every request before anything is sent."""

    def factory(target: S3Target, pair: S3Pair) -> S3Client:
        client = make_client(target, pair)
        client.meta.events.register_first("before-send.s3", fake)  # type: ignore[attr-defined]
        return client

    return factory


# ---- a plain HTTP server on 127.0.0.1 --------------------------------------------------------------------------------


class ScriptedServer:
    """An S3-shaped HTTP server on 127.0.0.1 (any port): PUT stores, GET reads, DELETE removes, HEAD answers 404 for a
    missing key. `hold[method]` makes that method wait until the event is set (a held answer, for the timeouts)."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.seen: list[tuple[str, str]] = []
        self.hold: dict[str, threading.Event] = {}
        self.done = threading.Event()  # set when a DELETE has been answered
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args: Any) -> None:  # quiet
                pass

            def _answer(self, status: int, body: bytes = b"", headers: dict[str, str] | None = None) -> None:
                self.send_response(status)
                for name, value in (headers or {}).items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(body)

            def _handle(self) -> None:
                path = unquote(urlsplit(self.path).path)
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                outer.seen.append((self.command, path))
                held = outer.hold.get(self.command)
                if held is not None:
                    held.wait(30)
                if self.command == "PUT":
                    outer.objects[path] = body
                    self._answer(200, b"", {"ETag": '"etag"'})
                elif self.command == "DELETE":
                    outer.objects.pop(path, None)
                    self._answer(204)
                    outer.done.set()
                elif path in outer.objects:
                    self._answer(200, outer.objects[path], {"Content-Type": "text/plain; charset=utf-8"})
                else:
                    self._answer(404, error_xml("NoSuchKey") if self.command == "GET" else b"")

            do_PUT = do_GET = do_DELETE = do_HEAD = _handle

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> ScriptedServer:
        self.thread.start()
        return self

    def __exit__(self, *_: Any) -> None:
        for event in self.hold.values():
            event.set()
        self.server.shutdown()
        self.server.server_close()

    def methods(self) -> list[str]:
        return [method for method, _ in self.seen]


def closed_port() -> int:
    """A port on 127.0.0.1 nothing listens on (bound, then closed)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
    return port


def wait_until(check: Callable[[], bool], seconds: float = 10.0) -> bool:
    event = threading.Event()
    for _ in range(int(seconds / 0.02)):
        if check():
            return True
        event.wait(0.02)
    return check()
