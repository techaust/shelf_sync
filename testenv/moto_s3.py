"""The S3 server of ShelfSync's test stack (m2.8; 04 section 10, 07 section 5, 04-A V6 to V8).

Starts moto's S3 server on 127.0.0.1 only, creates the test bucket and keeps running until Ctrl+C:

    UV_PYTHON_DOWNLOADS=never uv run python testenv/moto_s3.py [--port 47630] [--bucket shelfsync-test-stack]
                                                                [--region us-east-1]

- **127.0.0.1 only**, never moto's own `0.0.0.0` default, and on Windows with `SO_EXCLUSIVEADDRUSE`, so no other
  program can share the port (a plain `SO_REUSEADDR` socket there could be bound twice).
- **In memory only.** moto 5.2.4 has no state file (its recorder replays requests, it doesn't keep a store), so there
  is no `--data` folder: stopping the server removes the bucket and every file in it, and nothing is written to disk.
- **Any key pair works:** this server checks no keys or signatures (moto without its IAM checks; 04-A V8). Use
  made-up keys here, never real AWS ones.
- The request log shows each request's method, path and status, never its query string (a presigned URL's query
  holds the key ID).

Developer tooling for the test stack: never shipped with the app, and it never reaches anything outside this PC.
"""

import argparse
import os
import re
import socket
import sys
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from importlib.metadata import version
from typing import Any

from moto.moto_server.werkzeug_app import DomainDispatcherApplication, create_backend_app
from werkzeug.serving import ThreadedWSGIServer, WSGIRequestHandler

HOST = "127.0.0.1"
# Outside ShelfSync's own 47615-47624 (SET-06), below Windows' ephemeral range (49152-65535, so no outgoing connection
# ever holds it), and not 5000 (moto's default, which other development servers use too).
DEFAULT_PORT = 47630
DEFAULT_BUCKET = "shelfsync-test-stack"
DEFAULT_REGION = "us-east-1"
# Any pair works (no IAM checks); these only sign the script's own CreateBucket.
SETUP_KEY_ID = "shelfsync-test-stack"
SETUP_SECRET = "any-secret-works-here"  # a made-up value: this server checks no keys

_REGION = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])")
_LOG_PATH_MAX = 200


class PortUnavailable(Exception):
    """The port on 127.0.0.1 can't be used (another program has it, or Windows keeps it reserved)."""


class _Handler(WSGIRequestHandler):
    """werkzeug's handler, but its request log line drops the query string and any unprintable character."""

    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        path = str(getattr(self, "path", "-")).split("?", 1)[0][:_LOG_PATH_MAX]
        shown = "".join(c if c.isprintable() else "?" for c in path)
        self.log("info", '"%s %s" %s', getattr(self, "command", "-"), shown, code)


class _Server(ThreadedWSGIServer):
    # Windows: SO_EXCLUSIVEADDRUSE instead of SO_REUSEADDR (which there lets a second socket bind the same port).
    allow_reuse_address = not hasattr(socket, "SO_EXCLUSIVEADDRUSE")

    def server_bind(self) -> None:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            super().server_bind()
        except OSError as error:
            # Not an OSError: werkzeug would print its own notice and call sys.exit for one.
            port = self.server_address[1]
            raise PortUnavailable(f"Port {port} on {HOST} can't be used: {error.strerror or error}.") from error


@dataclass
class MotoS3:
    """A running moto S3 server and the bucket made on it."""

    server: _Server
    thread: threading.Thread
    bucket: str
    region: str

    @property
    def port(self) -> int:
        return int(self.server.server_address[1])

    @property
    def endpoint(self) -> str:
        return f"http://{HOST}:{self.port}"

    def stop(self) -> None:
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()


def s3_client(endpoint: str, region: str, key_id: str = SETUP_KEY_ID, secret: str = SETUP_SECRET) -> Any:
    """A botocore S3 client for this server only: path-style, no proxy, and nothing read from this PC's `~/.aws`
    files, `AWS_*` variables or proxy settings."""
    import botocore.session
    from botocore.config import Config

    nowhere = os.devnull
    session = botocore.session.Session(
        session_vars={
            "profile": (None, None, None, None),
            "config_file": (None, None, nowhere, None),
            "credentials_file": (None, None, nowhere, None),
        }
    )
    return session.create_client(
        "s3",
        region_name=region,
        endpoint_url=endpoint,
        aws_access_key_id=key_id,
        aws_secret_access_key=secret,
        aws_session_token=None,
        config=Config(
            proxies={},  # not None: None makes botocore read HTTPS_PROXY and the Windows proxy settings
            ignore_configured_endpoint_urls=True,
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            retries={"mode": "standard", "total_max_attempts": 1},
            connect_timeout=5,
            read_timeout=10,
        ),
    )


def create_bucket(endpoint: str, bucket: str, region: str) -> None:
    client = s3_client(endpoint, region)
    try:
        if region == "us-east-1":  # S3 refuses a LocationConstraint of us-east-1
            client.create_bucket(Bucket=bucket)
        else:
            client.create_bucket(Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": region})
    finally:
        client.close()


def start(port: int = DEFAULT_PORT, bucket: str = DEFAULT_BUCKET, region: str = DEFAULT_REGION) -> MotoS3:
    """Start moto's S3 server on 127.0.0.1:`port` (0: any free port) and create `bucket` in `region`.
    PortUnavailable if the port can't be used; a botocore error if the bucket can't be made (the server is stopped)."""
    app = DomainDispatcherApplication(create_backend_app)
    server = _Server(HOST, port, app, handler=_Handler)
    thread = threading.Thread(target=server.serve_forever, name="moto-s3", daemon=True)
    thread.start()
    running = MotoS3(server, thread, bucket, region)
    try:
        create_bucket(running.endpoint, bucket, region)
    except BaseException:
        running.stop()
        raise
    return running


def banner(running: MotoS3) -> str:
    return "\n".join(
        [
            f"ShelfSync test stack: moto S3 server (moto {version('moto')})",
            f"  Endpoint  {running.endpoint}",
            f"  Region    {running.region}",
            f"  Bucket    {running.bucket}",
            "  Keys      any made-up access key ID and secret work: this server checks no keys.",
            "            Never type real AWS keys here.",
            f"Listening on {HOST} only: nothing outside this PC can reach it.",
            "Everything is kept in memory only: stopping the server removes the bucket and every file in it.",
            "Press Ctrl+C to stop.",
        ]
    )


def wait_for_ctrl_c(_: MotoS3) -> None:
    """Block until Ctrl+C. Short waits, so the KeyboardInterrupt arrives within half a second on Windows too."""
    idle = threading.Event()
    while not idle.wait(0.5):
        pass


def say(text: str, stream: Any = None) -> None:
    out = stream if stream is not None else sys.stdout
    out.write(text + "\n")
    out.flush()


def _port(value: str) -> int:
    port = int(value)
    if not 0 <= port <= 65535:
        raise argparse.ArgumentTypeError("must be 0 to 65535 (0: any free port)")
    return port


def _region(value: str) -> str:
    if _REGION.fullmatch(value) is None:
        raise argparse.ArgumentTypeError("must be 2 to 32 lowercase letters, digits and hyphens, like us-east-1")
    return value


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="moto_s3.py",
        description="Start the moto S3 server of ShelfSync's test stack on 127.0.0.1 and keep it running until Ctrl+C.",
    )
    parser.add_argument("--port", type=_port, default=DEFAULT_PORT, help=f"port on 127.0.0.1 (default {DEFAULT_PORT})")
    parser.add_argument("--bucket", default=DEFAULT_BUCKET, help=f"test bucket to create (default {DEFAULT_BUCKET})")
    parser.add_argument("--region", type=_region, default=DEFAULT_REGION, help=f"its region (default {DEFAULT_REGION})")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None, wait: Callable[[MotoS3], None] = wait_for_ctrl_c) -> int:
    from botocore.exceptions import BotoCoreError, ClientError

    args = parse_args(argv)
    try:
        running = start(args.port, args.bucket, args.region)
    except PortUnavailable as error:
        say(f"{error} Stop the program using it, or start this one with another --port.", sys.stderr)
        return 1
    except (BotoCoreError, ClientError) as error:
        say(f"The test bucket {args.bucket!r} couldn't be created: {error}", sys.stderr)
        return 1
    say(banner(running))
    try:
        wait(running)
    except KeyboardInterrupt:
        pass
    finally:
        running.stop()
    say("Stopped. The bucket and its files are gone (they were in memory only).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
