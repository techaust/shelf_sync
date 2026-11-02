"""m2.8 (the moto part): `testenv/moto_s3.py`, the S3 server of the test stack. It listens on 127.0.0.1 only, makes the
test bucket, reports a port it can't use instead of hanging, and ShelfSync's own Storage Test passes against it.
No live AWS, bucket or store is ever reached (the conftest guard allows loopback only)."""

import queue
import re
import secrets
import signal
import socket
import subprocess
import sys
import threading
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import IO

import pytest
from testenv import moto_s3

from shelfsync.api.storage import STORAGE_TEST_PATH
from shelfsync.secure.credentials import S3Credentials
from tests.s3_support import (
    RO_PAIR,
    RW_PAIR,
    aws_setup_env,  # noqa: F401  (a fixture)
    keys_in,
    s3_guard,  # noqa: F401  (autouse: the key guard)
)
from tests.storage_support import GOOD_SETTINGS, make_storage_rig
from tests.support import WRITE_HEADERS

SCRIPT = Path(__file__).resolve().parent.parent / "testenv" / "moto_s3.py"


def unique_bucket() -> str:
    """moto keeps its buckets for the whole process: each test gets its own name."""
    return f"shelfsync-t3-{uuid.uuid4().hex[:12]}"


@pytest.fixture
def running(request: pytest.FixtureRequest) -> Iterator[moto_s3.MotoS3]:
    request.getfixturevalue("aws_setup_env")
    stack = moto_s3.start(port=0, bucket=unique_bucket(), region="ap-south-1")
    try:
        yield stack
    finally:
        stack.stop()


def bucket_region(endpoint: str, bucket: str, region: str) -> str:
    """HEAD the bucket with a made-up key pair (any pair works) and return the region moto reports for it."""
    client = moto_s3.s3_client(endpoint, region, f"made-up-{secrets.token_hex(4)}", secrets.token_hex(16))
    try:
        answer = client.head_bucket(Bucket=bucket)
    finally:
        client.close()
    return str(answer["ResponseMetadata"]["HTTPHeaders"]["x-amz-bucket-region"])


def test_start_listens_on_127_0_0_1_only_and_makes_the_bucket(running: moto_s3.MotoS3) -> None:
    host, port = running.server.socket.getsockname()[:2]
    assert (host, port) == ("127.0.0.1", running.port)
    assert running.server.socket.family == socket.AF_INET
    assert port != 0 and running.endpoint == f"http://127.0.0.1:{port}"
    assert bucket_region(running.endpoint, running.bucket, running.region) == "ap-south-1"


def test_the_default_region_us_east_1_makes_its_bucket_without_a_location(request: pytest.FixtureRequest) -> None:
    request.getfixturevalue("aws_setup_env")
    stack = moto_s3.start(port=0, bucket=unique_bucket())
    try:
        assert stack.region == moto_s3.DEFAULT_REGION == "us-east-1"
        assert bucket_region(stack.endpoint, stack.bucket, stack.region) == "us-east-1"
    finally:
        stack.stop()


@pytest.mark.skipif(not hasattr(socket, "SO_EXCLUSIVEADDRUSE"), reason="Windows only: SO_EXCLUSIVEADDRUSE")
def test_on_windows_no_other_socket_can_share_the_port(running: moto_s3.MotoS3) -> None:
    """On Windows a plain SO_REUSEADDR socket can bind a port another plain one holds; the server's port can't be."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as other:
        other.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        with pytest.raises(OSError):
            other.bind(("127.0.0.1", running.port))


def test_a_port_in_use_is_reported_not_hung(capsys: pytest.CaptureFixture[str]) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as holder:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            holder.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        holder.bind(("127.0.0.1", 0))
        holder.listen(1)
        port = holder.getsockname()[1]
        with pytest.raises(moto_s3.PortUnavailable, match=f"Port {port} on 127.0.0.1 can't be used"):
            moto_s3.start(port=port, bucket=unique_bucket())
        assert moto_s3.main(["--port", str(port), "--bucket", unique_bucket()]) == 1
    err = capsys.readouterr().err
    assert f"Port {port} on 127.0.0.1 can't be used" in err and "another --port" in err


def test_main_prints_what_to_paste_and_stops_on_ctrl_c(
    request: pytest.FixtureRequest, capsys: pytest.CaptureFixture[str]
) -> None:
    request.getfixturevalue("aws_setup_env")
    bucket = unique_bucket()
    seen: list[moto_s3.MotoS3] = []

    def press_ctrl_c(stack: moto_s3.MotoS3) -> None:
        seen.append(stack)
        assert bucket_region(stack.endpoint, bucket, "eu-west-2") == "eu-west-2"
        raise KeyboardInterrupt

    assert moto_s3.main(["--port", "0", "--bucket", bucket, "--region", "eu-west-2"], wait=press_ctrl_c) == 0
    out = capsys.readouterr().out
    port = seen[0].port
    assert f"  Endpoint  http://127.0.0.1:{port}\n" in out
    assert "  Region    eu-west-2\n" in out and f"  Bucket    {bucket}\n" in out
    assert "any made-up access key ID and secret work" in out and "Never type real AWS keys here." in out
    assert "Listening on 127.0.0.1 only" in out and "in memory only" in out
    assert out.rstrip().endswith("Stopped. The bucket and its files are gone (they were in memory only).")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:  # stopped: nothing listens any more
        assert probe.connect_ex(("127.0.0.1", port)) != 0


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["--port", "65536"], "must be 0 to 65535"),
        (["--port", "-1"], "must be 0 to 65535"),
        (["--region", "US-EAST-1"], "lowercase letters"),
        (["--region=east-"], "lowercase letters"),
    ],
)
def test_bad_arguments_are_refused(argv: list[str], message: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stopped:
        moto_s3.parse_args(argv)
    assert stopped.value.code == 2
    assert message in capsys.readouterr().err


def test_a_bucket_name_botocore_refuses_is_reported(capsys: pytest.CaptureFixture[str]) -> None:
    assert moto_s3.main(["--port", "0", "--bucket", "not a bucket"]) == 1
    assert "The test bucket 'not a bucket' couldn't be created" in capsys.readouterr().err


def raw(port: int, request: str) -> bytes:
    """Send one raw HTTP request to 127.0.0.1:`port` and return the whole answer."""
    answer = b""
    with socket.create_connection(("127.0.0.1", port), timeout=5) as conn:
        conn.sendall(request.encode("latin-1"))
        while chunk := conn.recv(65536):
            answer += chunk
    return answer


def test_the_request_and_error_logs_never_show_a_query_string(running: moto_s3.MotoS3) -> None:
    lines: list[str] = []

    class Recorder(moto_s3._Handler):
        def log(self, type: str, message: str, *args: object) -> None:
            lines.append(message % args)

    running.server.RequestHandlerClass = Recorder
    host = f"Host: 127.0.0.1:{running.port}\r\nConnection: close\r\n\r\n"
    raw(running.port, f"GET /{running.bucket}/k\x1b[31m.txt?X-Amz-Credential=AKIDSECRETISH%2F HTTP/1.1\r\n{host}")
    raw(running.port, f"GET /{running.bucket}/k.txt?X-Amz-Credential=AKIDSECRETTWO HTTP/1.1 extra\r\n{host}")
    requests = [line for line in lines if line.startswith('"GET ')]
    assert requests[0].startswith(f'"GET /{running.bucket}/k?[31m.txt" '), lines
    assert any("Bad request" in line for line in lines), lines  # the second one: werkzeug's error line
    assert not any("AKIDSECRET" in line or "\x1b" in line for line in lines), lines


@pytest.mark.parametrize("host", ["evil.example", f"evil.example:{moto_s3.DEFAULT_PORT}", "127.0.0.1", ""])
def test_a_request_for_another_host_gets_403(running: moto_s3.MotoS3, host: str) -> None:
    """DNS rebinding: a page's request reaches 127.0.0.1 but names its own host. Only 127.0.0.1:<port> and
    localhost:<port> are answered (and a request with no Host, or without the port, is refused too)."""
    header = f"Host: {host}\r\n" if host else ""
    answer = raw(running.port, f"GET /{running.bucket} HTTP/1.1\r\n{header}Connection: close\r\n\r\n")
    assert answer.startswith(b"HTTP/1.1 403 "), answer[:80]
    assert b"127.0.0.1 and localhost only" in answer
    reset = raw(
        running.port, f"POST /moto-api/reset HTTP/1.1\r\n{header}Content-Length: 0\r\nConnection: close\r\n\r\n"
    )
    assert reset.startswith(b"HTTP/1.1 403 ")
    assert bucket_region(running.endpoint, running.bucket, running.region) == running.region  # not reset


def cors_answers(port: int, bucket: str) -> list[bytes]:
    origin = "Origin: https://some-page.example\r\n"
    host = f"Host: 127.0.0.1:{port}\r\nConnection: close\r\n"
    return [
        raw(port, f"GET /{bucket} HTTP/1.1\r\n{host}{origin}\r\n"),
        raw(
            port,
            f"OPTIONS /{bucket} HTTP/1.1\r\n{host}{origin}Access-Control-Request-Method: PUT\r\n\r\n",
        ),
    ]


def test_moto_s_global_cors_is_off(running: moto_s3.MotoS3) -> None:
    for answer in cors_answers(running.port, running.bucket):
        assert b"access-control-allow-origin" not in answer.lower(), answer[:400]


def test_recorded_moto_turns_cors_on_for_every_origin_unless_told_not_to(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Why the script sets `DISABLE_GLOBAL_CORS` in `moto.moto_server.werkzeug_app` (read when moto makes its S3 app;
    `moto.settings` is copied there at import, so setting it there does nothing): moto 5.2.4's default answers any
    origin. If moto changes that, this test says so."""
    import moto.moto_server.werkzeug_app as moto_app
    from moto.server import ThreadedMotoServer

    request.getfixturevalue("aws_setup_env")
    monkeypatch.setattr(moto_app, "DISABLE_GLOBAL_CORS", False)
    server = ThreadedMotoServer(ip_address="127.0.0.1", port=0, verbose=False)
    server.start()
    try:
        port = server.get_host_and_port()[1]
        bucket = unique_bucket()
        moto_s3.create_bucket(f"http://127.0.0.1:{port}", bucket, "us-east-1")
        get, _ = cors_answers(port, bucket)
        assert b"access-control-allow-origin:" in get.lower(), get[:400]
    finally:
        server.stop()


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost"])
def test_shelfsyncs_storage_test_passes_against_the_scripts_server(running: moto_s3.MotoS3, host: str) -> None:
    """The Done check of T3: the Storage Test through ShelfSync's own client, against the bucket the script made."""
    endpoint = running.endpoint.replace("127.0.0.1", host)
    rig = make_storage_rig()
    settings = {**GOOD_SETTINGS, "s3_endpoint": endpoint, "s3_region": running.region, "s3_bucket": running.bucket}
    assert rig.client.put("/api/settings/storage", json=settings, headers=WRITE_HEADERS).status_code == 200
    credentials = S3Credentials(rig.secrets)
    credentials.save("rw", RW_PAIR.key_id, RW_PAIR.secret)
    credentials.save("ro", RO_PAIR.key_id, RO_PAIR.secret)
    body = rig.client.post(STORAGE_TEST_PATH, headers=WRITE_HEADERS).json()
    assert body["ok"] is True, body
    assert [step["state"] for step in body["steps"]] == ["passed"] * 3
    assert keys_in(running.bucket, running.endpoint) == []


def _lines(stream: IO[str], into: queue.Queue[str]) -> None:
    for line in stream:
        into.put(line)


def test_the_script_run_as_a_command(tmp_path: Path) -> None:
    """The real command, in its own process, on any free port (`--port 0`): it prints the settings, the bucket is there,
    and (off Windows, where a test can send it SIGINT) Ctrl+C stops it cleanly. On Windows the process is ended."""
    bucket = unique_bucket()
    process = subprocess.Popen(
        [sys.executable, "-I", str(SCRIPT), "--port", "0", "--bucket", bucket],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=tmp_path,
    )
    out: queue.Queue[str] = queue.Queue()
    reader = threading.Thread(target=_lines, args=(process.stdout, out), daemon=True)
    reader.start()
    seen: list[str] = []
    try:
        while not seen or seen[-1].strip() != "Press Ctrl+C to stop.":
            seen.append(out.get(timeout=60))
        text = "".join(seen)
        found = re.search(r"  Endpoint  http://127\.0\.0\.1:(\d+)\n", text)
        assert found is not None, text
        endpoint = f"http://127.0.0.1:{found.group(1)}"
        assert f"  Bucket    {bucket}\n" in text and "  Region    us-east-1\n" in text
        assert bucket_region(endpoint, bucket, "us-east-1") == "us-east-1"
        if sys.platform == "win32":
            process.terminate()
            process.wait(timeout=30)
        else:
            process.send_signal(signal.SIGINT)
            assert process.wait(timeout=30) == 0
            reader.join(timeout=10)
            rest = []
            while not out.empty():
                rest.append(out.get())
            assert "Stopped. The bucket and its files are gone" in "".join(rest)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=30)
        for pipe in (process.stdout, process.stderr):
            if pipe is not None:
                pipe.close()
