"""A second launch (SYS-03): ShelfSync is already running, so open a new signed-in tab and exit. Never a second server.

Order, and why:
1. Wait a few seconds for `runtime.json` and for `GET /api/health` to answer as ShelfSync (the first copy may still be
   starting). No answer: one notification, exit 4.
2. Ask Windows who owns the listening socket (V33). Only a process of the same Windows user, running ShelfSync's own
   Python, with the PID in runtime.json, may receive the install token (06 section 10, port squatting). Otherwise:
   log why (no token), one notification, exit 5.
3. Read the install token from Credential Manager (read only: only the first copy may create it), ask the ticket
   route for a ticket, open `sign_in_url()`.

The token goes in one `Authorization` header to `127.0.0.1`, over a client that ignores proxy settings and
redirects. It is never logged.
"""

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from shelfsync import messages
from shelfsync.paths import DataPaths
from shelfsync.platform.notify import Notifier
from shelfsync.platform.secrets import SecretStore, SecretStoreError
from shelfsync.platform.shell import Shell, ShellError
from shelfsync.platform.sockets import Verdict, check_listener
from shelfsync.ports import DEFAULT_PORT, LAST_PORT
from shelfsync.secure.middleware import HEALTH_PATH, TICKET_PATH
from shelfsync.secure.sessions import sign_in_url
from shelfsync.secure.token import INSTALL_TOKEN_NAME

_log = logging.getLogger("shelfsync.launcher")

EXIT_OPENED = 0
EXIT_NO_ANSWER = 4
EXIT_REFUSED = 5
EXIT_NO_SIGN_IN = 6

ANSWER_WAIT_SECONDS = 5.0
_POLL_SECONDS = 0.25
_HTTP_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class Running:
    port: int
    pid: int


def read_runtime(paths: DataPaths) -> Running | None:
    """The port and PID in runtime.json, or None if it is missing, damaged or holds anything unexpected."""
    try:
        data = json.loads(paths.runtime_json.read_text(encoding="utf-8"))
        port, pid = data["port"], data["pid"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if type(port) is not int or type(pid) is not int or pid <= 0 or not DEFAULT_PORT <= port <= LAST_PORT:
        return None
    return Running(port, pid)


def make_client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    """A client for ShelfSync's own address only: no proxy or other settings from the environment (a proxy variable
    would send the install token to the proxy), no redirects. `transport` is for tests."""
    return httpx.Client(transport=transport, trust_env=False, follow_redirects=False, timeout=_HTTP_TIMEOUT_SECONDS)


def answers_as_shelfsync(client: httpx.Client, port: int) -> bool:
    """`GET /api/health` returns ShelfSync's identity. This sends no secret."""
    try:
        response = client.get(f"http://127.0.0.1:{port}{HEALTH_PATH}")
        return response.status_code == 200 and response.json().get("app") == "shelfsync"
    except (httpx.HTTPError, ValueError, AttributeError):
        return False


def second_launch(
    paths: DataPaths,
    notifier: Notifier,
    shell: Shell,
    secrets: SecretStore,
    *,
    client_factory: Callable[[], httpx.Client] = make_client,
    owner_check: Callable[[int, int], Verdict] = check_listener,
    wait_seconds: float = ANSWER_WAIT_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> int:
    with client_factory() as probe:
        running = _wait_for_first_copy(paths, probe, wait_seconds, sleep, clock)
    if running is None:
        _log.warning("Second launch: the running copy didn't answer in %.0f seconds", wait_seconds)
        notifier.notify(messages.LAUNCH_NO_ANSWER)
        return EXIT_NO_ANSWER

    verdict = owner_check(running.port, running.pid)
    if verdict is not Verdict.TRUSTED:
        # Why, and nothing that could be a secret: no token has been read yet.
        _log.warning("Second launch refused: the socket owner check said %s", verdict.value)
        notifier.notify(messages.LAUNCH_REFUSED)
        return EXIT_REFUSED

    # A new client for the token: the probe's connection was opened before the owner check, so it could be talking to
    # a different program than the one the check looked at. A fresh client opens a fresh connection, which narrows the
    # gap (a program could still take the port between the owner check and this connection) but doesn't close it.
    with client_factory() as sender:
        ticket = _ask_for_ticket(sender, running.port, secrets)
    if ticket is None:
        notifier.notify(messages.LAUNCH_NO_SIGN_IN)
        return EXIT_NO_SIGN_IN
    try:
        shell.open_url(sign_in_url(running.port, ticket))
    except (ShellError, ValueError) as error:
        _log.warning("Second launch: the tab couldn't be opened (%s)", type(error).__name__)
        notifier.notify(messages.LAUNCH_NO_SIGN_IN)
        return EXIT_NO_SIGN_IN
    return EXIT_OPENED


def _wait_for_first_copy(
    paths: DataPaths,
    client: httpx.Client,
    wait_seconds: float,
    sleep: Callable[[float], None],
    clock: Callable[[], float],
) -> Running | None:
    deadline = clock() + wait_seconds
    while True:
        running = read_runtime(paths)
        if running is not None and answers_as_shelfsync(client, running.port):
            return running
        if clock() >= deadline:
            return None
        sleep(_POLL_SECONDS)


def _ask_for_ticket(client: httpx.Client, port: int, secrets: SecretStore) -> str | None:
    try:
        token = secrets.get(INSTALL_TOKEN_NAME)
    except SecretStoreError as error:
        _log.warning("Second launch: the install token couldn't be read (%s)", type(error).__name__)
        return None
    if token is None:
        _log.warning("Second launch: there is no install token to sign in with")
        return None
    try:
        # No Origin (httpx sends none): the ticket route refuses any Origin.
        response = client.post(f"http://127.0.0.1:{port}{TICKET_PATH}", headers={"Authorization": f"Bearer {token}"})
        ticket = response.json().get("ticket") if response.status_code == 200 else None
    except (httpx.HTTPError, ValueError, AttributeError):
        ticket = None
    if not isinstance(ticket, str):
        _log.warning("Second launch: the running copy gave no ticket")
        return None
    return ticket
