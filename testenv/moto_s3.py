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
- **This PC's programs only:** a request whose `Host` isn't `127.0.0.1:<port>` or `localhost:<port>` gets 403 (a
  DNS-rebinding page can't reach it), and moto's global CORS (on for every origin by default) is turned off, so a web
  page open in the browser can't read, write or reset it. The S3 extension's download links are navigations, which
  need no CORS (04-A V6, still to confirm on the test stack).
- The request and error logs never show a query string (a presigned URL's holds the key ID).

Developer tooling for the test stack: never shipped with the app, and it never reaches anything outside this PC.
"""

import argparse
import re
import socket
import sys
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Any
from wsgiref.types import StartResponse, WSGIApplication, WSGIEnvironment

import moto.moto_server.werkzeug_app as moto_app
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
_QUERY = re.compile(r"\?[^\s'\"]*")
_LOG_MAX = 300
_BACKEND = Path(__file__).resolve().parent.parent / "backend"


class PortUnavailable(Exception):
    """The port on 127.0.0.1 can't be used (another program has it, or Windows keeps it reserved)."""


def scrub(text: str) -> str:
    """A log line without any query string (`?...`) or unprintable character, at most 300 characters."""
    return "".join(c if c.isprintable() else "?" for c in _QUERY.sub("?...", text))[:_LOG_MAX]


class _Handler(WSGIRequestHandler):
    """werkzeug's handler, but its request and error lines drop query strings and unprintable characters."""

    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        path = str(getattr(self, "path", "-")).split("?", 1)[0]
        self.log("info", "%s", scrub(f'"{getattr(self, "command", "-")} {path}" {code}'))

    def log_error(self, format: str, *args: Any) -> None:  # "Bad request syntax ('GET /k?X-Amz-...')", say
        self.log("error", "%s", scrub(format % args))

    def log_message(self, format: str, *args: Any) -> None:
        self.log("info", "%s", scrub(format % args))


class _LoopbackHostOnly:
    """403 for any request whose `Host` isn't `127.0.0.1:<port>` or `localhost:<port>` (DNS rebinding)."""

    def __init__(self, app: WSGIApplication) -> None:
        self.app = app
        self.port = 0  # set once the socket is bound

    def __call__(self, environ: WSGIEnvironment, start_response: StartResponse) -> Any:
        host = str(environ.get("HTTP_HOST", "")).lower()
        if host not in (f"127.0.0.1:{self.port}", f"localhost:{self.port}"):
            body = b"This test server answers requests for 127.0.0.1 and localhost only.\n"
            start_response("403 Forbidden", [("Content-Type", "text/plain"), ("Content-Length", str(len(body)))])
            return [body]
        return self.app(environ, start_response)


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
    """ShelfSync's own isolated S3 client (`shelfsync.apply.s3.make_client`): path-style for this endpoint, every
    setting explicit, and nothing taken from this PC's `~/.aws` files, `AWS_*` variables, proxy settings or extra
    botocore models. The caller closes it."""
    if str(_BACKEND) not in sys.path:  # run as `python testenv/moto_s3.py`: backend/ isn't on the path yet
        sys.path.insert(0, str(_BACKEND))
    from shelfsync.apply.s3 import S3Target, make_client
    from shelfsync.secure.credentials import S3Pair

    client: Any = make_client(S3Target(endpoint, region, ""), S3Pair(key_id, secret))
    return client


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
    # moto turns on CORS for every origin unless this is set; it's read when moto makes its S3 app (first request).
    # It's copied there from moto.settings at import (so setting moto.settings does nothing) and not re-exported.
    moto_app.DISABLE_GLOBAL_CORS = True  # type: ignore[attr-defined]
    app = _LoopbackHostOnly(moto_app.DomainDispatcherApplication(moto_app.create_backend_app))
    server = _Server(HOST, port, app, handler=_Handler)
    app.port = int(server.server_address[1])
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
