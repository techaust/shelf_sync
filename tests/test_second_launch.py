"""SYS-03: a second launch opens a new signed-in tab in the running copy, after checking who owns the port, and never
starts a second server. HTTP is stubbed with httpx's MockTransport; one test talks to a real server."""

import asyncio
import json
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

import httpx
import pytest

from shelfsync import messages, server
from shelfsync.api.app import create_app
from shelfsync.paths import DataPaths, write_runtime_json
from shelfsync.platform.notify import FakeNotifier
from shelfsync.platform.secrets import MemorySecretStore, SecretStoreError
from shelfsync.platform.shell import FakeShell, ShellError
from shelfsync.platform.sockets import Verdict
from shelfsync.secure.sessions import sign_in_url
from shelfsync.secure.token import INSTALL_TOKEN_NAME, InstallToken
from shelfsync.tray import second_launch as sl

PORT = 47615
PID = 4321
TOKEN = "t" * 43
TICKET = "ticket_" + "x" * 36


class Harness:
    """A running copy that answers the way ShelfSync does, as far as the second launch looks."""

    def __init__(self, data_paths: DataPaths) -> None:
        self.paths = data_paths
        self.requests: list[httpx.Request] = []
        self.health = {"app": "shelfsync", "version": "0.1.0"}
        self.ticket_status = 200
        self.ticket_body: object = {"ticket": TICKET, "expires_in": 60}
        self.notifier = FakeNotifier()
        self.shell = FakeShell()
        self.store = MemorySecretStore()
        self.store.set(INSTALL_TOKEN_NAME, TOKEN)
        self.verdict = Verdict.TRUSTED
        self.owner_checks: list[tuple[int, int]] = []
        self.now = 0.0
        self.sleeps: list[float] = []
        self.clients_made = 0
        self.client_of: dict[int, int] = {}  # request -> the number of the client that sent it

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        self.client_of[id(request)] = self.clients_made
        if request.url.path == "/api/health":
            return httpx.Response(200, json=self.health)
        if request.url.path == "/api/session/ticket":
            return httpx.Response(self.ticket_status, json=self.ticket_body)
        return httpx.Response(404)

    def client(self) -> httpx.Client:
        self.clients_made += 1
        number = self.clients_made

        def handler(request: httpx.Request) -> httpx.Response:
            self.clients_made, previous = number, self.clients_made
            try:
                return self.handler(request)
            finally:
                self.clients_made = previous

        return sl.make_client(transport=httpx.MockTransport(handler))

    def owner_check(self, port: int, pid: int) -> Verdict:
        self.owner_checks.append((port, pid))
        return self.verdict

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def write_runtime(self, port: int = PORT, pid: int = PID) -> None:
        self.paths.root.mkdir(parents=True, exist_ok=True)
        write_runtime_json(self.paths, port, pid)

    def launch(self, store: object = None, wait_seconds: float = 2.0) -> int:
        return sl.second_launch(
            self.paths,
            self.notifier,
            self.shell,
            store if store is not None else self.store,  # type: ignore[arg-type]
            client_factory=self.client,
            owner_check=self.owner_check,
            wait_seconds=wait_seconds,
            sleep=self.sleep,
            clock=lambda: self.now,
        )

    @property
    def authorized_requests(self) -> list[httpx.Request]:
        return [request for request in self.requests if "authorization" in request.headers]


@pytest.fixture
def harness(data_paths: DataPaths) -> Harness:
    return Harness(data_paths)


def test_a_second_launch_opens_a_signed_in_tab_and_exits_0(harness: Harness) -> None:
    """SYS-03: health, owner check, the ticket route, then the sign-in address on 127.0.0.1."""
    harness.write_runtime()
    assert harness.launch() == sl.EXIT_OPENED == 0
    assert harness.shell.urls == [sign_in_url(PORT, TICKET)]
    assert harness.shell.urls[0].startswith("http://127.0.0.1:47615/#t=")
    assert "localhost" not in harness.shell.urls[0]
    assert harness.notifier.messages == []
    assert harness.owner_checks == [(PORT, PID)]


def test_the_install_token_goes_only_in_one_authorization_header_with_no_origin(harness: Harness) -> None:
    """SYS-03 (M1a.2 contract): Bearer token, no Origin; the token is in no URL, body or cookie, nor the tab address."""
    harness.write_runtime()
    harness.launch()
    (ticket_request,) = harness.authorized_requests
    assert ticket_request.method == "POST" and ticket_request.url.path == "/api/session/ticket"
    assert ticket_request.headers["authorization"] == f"Bearer {TOKEN}"
    assert "origin" not in ticket_request.headers
    for request in harness.requests:
        assert TOKEN not in str(request.url)
        assert TOKEN.encode() not in request.content
        assert "cookie" not in request.headers
    assert TOKEN not in harness.shell.urls[0]


def test_the_token_goes_over_a_fresh_connection_not_the_one_probed_before_the_owner_check(harness: Harness) -> None:
    """SYS-03 (review 7): the probe's connection could be to another program than the one the owner check looked at;
    the token is sent by a new client."""
    harness.write_runtime()
    harness.launch()
    probe_numbers = {harness.client_of[id(r)] for r in harness.requests if r.url.path == "/api/health"}
    ticket_numbers = {harness.client_of[id(r)] for r in harness.authorized_requests}
    assert len(probe_numbers) == 1 and len(ticket_numbers) == 1
    assert probe_numbers.isdisjoint(ticket_numbers)
    assert harness.clients_made >= 2


def test_the_token_is_never_logged(harness: Harness, caplog: pytest.LogCaptureFixture) -> None:
    """LOG-01: no token, ticket or address in any log line, on success or failure."""
    harness.write_runtime()
    with caplog.at_level("DEBUG"):
        harness.launch()
        harness.ticket_status = 401
        harness.ticket_body = {"error": "bad_token"}
        harness.launch()
    assert TOKEN not in caplog.text and TICKET not in caplog.text and "#t=" not in caplog.text


def test_the_install_token_is_read_never_created(harness: Harness) -> None:
    """SYS-03 (M1a.2 review #6): only the copy that holds the instance lock may make a token."""
    harness.write_runtime()
    empty = MemorySecretStore()
    assert harness.launch(store=empty) == sl.EXIT_NO_SIGN_IN
    assert empty.get(INSTALL_TOKEN_NAME) is None
    assert harness.authorized_requests == []
    assert harness.notifier.messages == [messages.LAUNCH_NO_SIGN_IN]


def test_an_unreadable_secret_store_is_a_notice_not_a_crash(harness: Harness) -> None:
    """SYS-03."""

    class Broken(MemorySecretStore):
        def get(self, name: str) -> str | None:
            raise SecretStoreError("Credential Manager read failed (OSError)")

    harness.write_runtime()
    assert harness.launch(store=Broken()) == sl.EXIT_NO_SIGN_IN
    assert harness.shell.urls == []


@pytest.mark.parametrize(
    "verdict",
    [Verdict.NOBODY, Verdict.OTHER_USER, Verdict.OTHER_PROGRAM, Verdict.STALE_PID, Verdict.LOOKUP_FAILED],
)
def test_when_the_owner_check_fails_the_token_is_never_read_or_sent(harness: Harness, verdict: Verdict) -> None:
    """SYS-03 (port squatting, 06 section 10): another user's program that answers /api/health like ShelfSync gets
    nothing. One notification, exit 5, a log line with the reason and no token."""

    class Spy(MemorySecretStore):
        reads = 0

        def get(self, name: str) -> str | None:
            Spy.reads += 1
            return TOKEN

    harness.write_runtime()
    harness.verdict = verdict
    assert harness.launch(store=Spy()) == sl.EXIT_REFUSED == 5
    assert Spy.reads == 0  # not even read
    assert harness.authorized_requests == []
    assert harness.shell.urls == []
    assert harness.notifier.messages == [messages.LAUNCH_REFUSED]


def test_a_refusal_logs_the_reason_without_a_secret(harness: Harness, caplog: pytest.LogCaptureFixture) -> None:
    """SYS-03: the log says why."""
    harness.write_runtime()
    harness.verdict = Verdict.OTHER_USER
    with caplog.at_level("WARNING"):
        harness.launch()
    assert "other_user" in caplog.text and TOKEN not in caplog.text


def test_no_runtime_json_waits_then_notifies_once_and_exits_non_zero(harness: Harness) -> None:
    """SYS-03: the first copy hasn't answered within the wait: one notification, a non-zero exit, no second server."""
    assert harness.launch(wait_seconds=2.0) == sl.EXIT_NO_ANSWER != 0
    assert harness.notifier.messages == [messages.LAUNCH_NO_ANSWER]
    assert harness.requests == [] and harness.shell.urls == []
    assert 1.5 <= sum(harness.sleeps) <= 2.5  # it waited about the budget, on the injected clock


def test_it_keeps_trying_while_the_first_copy_starts(harness: Harness) -> None:
    """SYS-03: runtime.json appears after a second."""
    real_sleep = harness.sleep

    def sleep_then_start(seconds: float) -> None:
        real_sleep(seconds)
        if harness.now >= 1.0 and not harness.paths.runtime_json.exists():
            harness.write_runtime()

    harness.sleep = sleep_then_start  # type: ignore[method-assign]
    assert harness.launch(wait_seconds=5.0) == sl.EXIT_OPENED


def test_a_program_that_answers_health_as_something_else_is_not_shelfsync(harness: Harness) -> None:
    """SYS-03: the identity check."""
    harness.write_runtime()
    harness.health = {"app": "something-else", "version": "1"}
    assert harness.launch(wait_seconds=1.0) == sl.EXIT_NO_ANSWER
    assert harness.owner_checks == [] and harness.authorized_requests == []


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        "[]",
        "{}",
        '{"port": 47615}',
        '{"port": "47615", "pid": 4321}',
        '{"port": 47615, "pid": 0}',
        '{"port": 47615, "pid": true}',
        '{"port": 80, "pid": 4321}',
        '{"port": 47625, "pid": 4321}',
        '{"port": 47615.0, "pid": 4321}',
    ],
)
def test_a_damaged_or_odd_runtime_json_is_treated_as_missing(harness: Harness, content: str) -> None:
    """SYS-03: only a port inside 47615-47624 and a positive whole PID count; anything else is no answer."""
    harness.paths.root.mkdir(parents=True)
    harness.paths.runtime_json.write_text(content, encoding="utf-8")
    assert sl.read_runtime(harness.paths) is None
    assert harness.launch(wait_seconds=0.5) == sl.EXIT_NO_ANSWER
    assert harness.requests == []


def test_a_ticket_refusal_is_a_notice_and_no_tab(harness: Harness) -> None:
    """SYS-03: 401 (the token was reset in between, say)."""
    harness.write_runtime()
    harness.ticket_status = 401
    harness.ticket_body = {"error": "bad_token"}
    assert harness.launch() == sl.EXIT_NO_SIGN_IN
    assert harness.shell.urls == [] and harness.notifier.messages == [messages.LAUNCH_NO_SIGN_IN]


@pytest.mark.parametrize("body", [{"ticket": 5}, {}, [], "text", None])
def test_an_odd_ticket_body_is_a_notice_and_no_tab(harness: Harness, body: object) -> None:
    """SYS-03."""
    harness.write_runtime()
    harness.ticket_body = body
    assert harness.launch() == sl.EXIT_NO_SIGN_IN
    assert harness.shell.urls == []


def test_a_ticket_that_isnt_url_safe_is_refused_before_it_reaches_the_address(harness: Harness) -> None:
    """SYS-03: sign_in_url only takes letters, digits, - and _; the program on the port doesn't get to inject."""
    harness.write_runtime()
    harness.ticket_body = {"ticket": "x&y=http://evil.example"}
    assert harness.launch() == sl.EXIT_NO_SIGN_IN
    assert harness.shell.urls == []


def test_a_shell_that_cant_open_the_address_is_a_notice(harness: Harness) -> None:
    """SYS-03."""

    class NoBrowser(FakeShell):
        def open_url(self, url: str) -> None:
            raise ShellError("Windows couldn't open the address (OSError)")

    harness.write_runtime()
    harness.shell = NoBrowser()
    assert harness.launch() == sl.EXIT_NO_SIGN_IN
    assert harness.notifier.messages == [messages.LAUNCH_NO_SIGN_IN]


def test_a_redirect_is_not_followed_so_the_token_stays_on_127_0_0_1(harness: Harness) -> None:
    """SYS-03: the program on the port can't bounce the token to another address."""
    seen: list[str] = []

    def redirecting(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.path == "/api/health":
            return httpx.Response(200, json=harness.health)
        return httpx.Response(307, headers={"location": "http://evil.example/steal"})

    harness.write_runtime()
    harness.client = lambda: sl.make_client(transport=httpx.MockTransport(redirecting))  # type: ignore[method-assign]
    assert harness.launch() == sl.EXIT_NO_SIGN_IN
    assert all(url.startswith("http://127.0.0.1:47615/") for url in seen)


def test_the_real_client_ignores_proxy_settings_and_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    """SYS-03: HTTP_PROXY in the environment would send the install token to the proxy."""
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.example:8080")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:8080")
    monkeypatch.setenv("ALL_PROXY", "http://proxy.example:8080")
    with sl.make_client() as client:
        assert client._trust_env is False
        assert client.follow_redirects is False
        assert client.timeout.read == 5.0


# ---- against a real server -------------------------------------------------------------------------------------------


@contextmanager
def real_copy(data_paths: DataPaths, store: MemorySecretStore) -> Iterator[int]:
    import uvicorn

    sock = server.bind_first_free([0])
    assert sock is not None
    port = sock.getsockname()[1]
    app = create_app(port, InstallToken(store))
    uv = uvicorn.Server(server.make_uvicorn_config(app, port))
    thread = threading.Thread(target=lambda: asyncio.run(uv.serve(sockets=[sock])), daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not uv.started and time.monotonic() < deadline:
            time.sleep(0.05)
        assert uv.started
        yield port
    finally:
        uv.should_exit = True
        thread.join(timeout=10)
        sock.close()


def test_against_a_real_server_the_tab_address_holds_a_ticket_that_signs_in(
    data_paths: DataPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SYS-03: the whole flow on a real uvicorn: the ticket in the address is single-use and signs the tab in."""
    store = MemorySecretStore()
    with real_copy(data_paths, store) as port:
        # runtime.json must name a port in the range, so ask the module to accept this ephemeral one
        monkeypatch.setattr(sl, "DEFAULT_PORT", 1024)
        monkeypatch.setattr(sl, "LAST_PORT", 65535)
        data_paths.root.mkdir(parents=True, exist_ok=True)
        write_runtime_json(data_paths, port, 4321)
        notifier, shell = FakeNotifier(), FakeShell()
        code = sl.second_launch(
            data_paths, notifier, shell, store, owner_check=lambda p, pid: Verdict.TRUSTED, wait_seconds=3.0
        )
        assert code == 0 and notifier.messages == []
        (url,) = shell.urls
        assert url.startswith(f"http://127.0.0.1:{port}/#t=")
        ticket = url.split("#t=", 1)[1]
        browser = httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False)
        headers = {"Origin": f"http://127.0.0.1:{port}", "X-ShelfSync": "1"}
        first = browser.post("/api/session", json={"ticket": ticket}, headers=headers)
        assert first.status_code == 204 and "shelfsync_session" in browser.cookies
        again = browser.post("/api/session", json={"ticket": ticket}, headers=headers)
        assert again.status_code == 401  # single use
        assert json.loads(again.text) == {"error": "bad_ticket"}
        browser.close()
