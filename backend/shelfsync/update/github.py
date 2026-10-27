"""Reading GitHub Releases (SYS-06, 04 section 7, 04-A V26, V45).

Rules this module keeps:
- one client with `trust_env=False` (a proxy variable or a `.netrc` file must never receive the token), explicit
  timeouts, and **no automatic redirects**: they are followed by hand, at most 3, HTTPS only, and only to the three
  hosts in `ALLOWED_HOSTS`. Any other host is refused and the log names that host only.
- the token (optional, a read-only fine-grained token) goes to `api.github.com` in the first request only, never
  across a redirect, never to the asset host.
- nothing logs a URL with a query string or any header value.
- every answer is classified into one of the fixed `Outcome` values; nothing from a response is shown as text.

An asset is requested at the API's own URL, built here from its numeric id, with `Accept: application/octet-stream`.
GitHub answers that with 200 or 302 (V45); both are handled.
"""

import json
import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

import httpx

from shelfsync.update.versions import VersionError, parse_version

_log = logging.getLogger("shelfsync.update")

# httpx logs every request at INFO with its full URL, and a signed asset link carries its signature in the query
# string. Nothing in this module may log such a URL, so httpx's own request lines are turned down to warnings.
logging.getLogger("httpx").setLevel(logging.WARNING)

REPO = "techaust/shelf_sync"
API_HOST = "api.github.com"
ALLOWED_HOSTS = frozenset({API_HOST, "github.com", "release-assets.githubusercontent.com"})
MAX_REDIRECTS = 3
EXPIRY_HEADER = "github-authentication-token-expiration"
EXPIRY_NOTICE_DAYS = 14
MAX_JSON_BYTES = 2 * 1024 * 1024
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class Outcome(StrEnum):
    OK = "ok"
    NO_RELEASE = "no_release"
    TOKEN_REFUSED = "token_refused"  # nosec B105  # an outcome name, not a password
    RATE_LIMITED = "rate_limited"
    NOT_PUBLIC = "not_public"
    UNREACHABLE = "unreachable"


class DownloadRefused(Exception):
    """A request was refused before or while it ran. `code`: `host_not_allowed`, `too_many_redirects`, `bad_status`,
    `unreachable`. The message never holds a URL or header."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    id: int
    size: int


@dataclass(frozen=True)
class Release:
    tag: str
    assets: dict[str, ReleaseAsset]


@dataclass(frozen=True)
class CheckResult:
    outcome: Outcome
    release: Release | None = None
    token_expires_at: datetime | None = None  # only when a token was sent and GitHub said


def parse_expiry(value: str | None) -> datetime | None:
    """The token expiry GitHub reports, as an aware UTC datetime; None if the header is missing or in a form this
    doesn't recognise (V26: the exact form is verified at the exit test). A missing header means no early notice."""
    if not value:
        return None
    text = value.strip()
    if text.endswith(" UTC"):
        text = text[:-4] + "+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)


def expiry_notice(expires_at: datetime | None, now: datetime) -> bool:
    """True from 14 days before the token expires (SYS-06), and after. Unknown expiry: no notice."""
    return expires_at is not None and expires_at - now <= timedelta(days=EXPIRY_NOTICE_DAYS)


def _printable(text: str, limit: int = 100) -> str:
    return "".join(ch if ch.isprintable() else "?" for ch in text[:limit])


def check_url_allowed(url: httpx.URL) -> None:
    """HTTPS, an allowed host, the default port, no user information. Anything else raises DownloadRefused."""
    host = url.host.lower() if url.host else ""
    if url.scheme != "https" or host not in ALLOWED_HOSTS or url.port not in (None, 443) or url.userinfo:
        _log.warning("An update request was refused: host %s is not allowed", _printable(host))
        raise DownloadRefused("host_not_allowed")


def _classify_status(status: int, headers: httpx.Headers, token_set: bool) -> Outcome:
    """Every answer that isn't 200 or 404. A limit shows as 429, or as 403 with no requests remaining (V45); a 403
    for any other reason is the token's doing when one was sent."""
    limited = headers.get("x-ratelimit-remaining") == "0" or "retry-after" in headers
    if status == 429 or (status == 403 and limited):
        return Outcome.RATE_LIMITED
    if status == 401 or (status == 403 and token_set):
        return Outcome.TOKEN_REFUSED
    return Outcome.UNREACHABLE


def _parse_release(body: bytes) -> Release | None:
    try:
        data = json.loads(body.decode("utf-8"))
        tag = data["tag_name"]
        if not isinstance(tag, str) or not tag.startswith("v"):
            return None
        parse_version(tag[1:])
        assets: dict[str, ReleaseAsset] = {}
        for item in data["assets"]:
            name, asset_id, size = item["name"], item["id"], item["size"]
            if (
                isinstance(name, str)
                and type(asset_id) is int
                and type(size) is int
                and item.get("state", "uploaded") == "uploaded"
            ):
                assets[name] = ReleaseAsset(name, asset_id, size)
    except ValueError, KeyError, TypeError, VersionError, UnicodeDecodeError:
        return None
    return Release(tag, assets)


class GitHubClient:
    """The one place the updater talks to GitHub. `token_source` returns the token or None, each time it is asked.
    `transport` is for tests (httpx.MockTransport)."""

    def __init__(self, token_source: Callable[[], str | None], transport: httpx.BaseTransport | None = None) -> None:
        self._token_source = token_source
        self._transport = transport

    def _client(self) -> httpx.Client:
        return httpx.Client(transport=self._transport, trust_env=False, follow_redirects=False, timeout=_TIMEOUT)

    @staticmethod
    def _headers(accept: str, token: str | None, host: str) -> dict[str, str]:
        headers = {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "ShelfSync-updater"}
        if token and host == API_HOST:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _api_get(self, client: httpx.Client, path: str, token: str | None) -> tuple[int, httpx.Headers, bytes]:
        url = httpx.URL(f"https://{API_HOST}/repos/{REPO}{path}")
        check_url_allowed(url)
        with client.stream(
            "GET", url, headers=self._headers("application/vnd.github+json", token, API_HOST)
        ) as response:
            body = b""
            if response.status_code == 200:
                for chunk in response.iter_bytes():
                    body += chunk
                    if len(body) > MAX_JSON_BYTES:
                        raise DownloadRefused("bad_status")
            return response.status_code, response.headers, body

    def latest(self) -> CheckResult:
        """`GET /repos/<repo>/releases/latest`: the newest release that is neither a draft nor a pre-release."""
        return self._release("/releases/latest")

    def release_for(self, version: str) -> CheckResult:
        """The release with the tag `v<version>` (the running version's own manifest, on the first check)."""
        parse_version(version)
        return self._release(f"/releases/tags/v{version}")

    def _release(self, path: str) -> CheckResult:
        token = self._token_source()
        try:
            with self._client() as client:
                status, headers, body = self._api_get(client, path, token)
                expires = parse_expiry(headers.get(EXPIRY_HEADER)) if token else None
                if status == 200:
                    release = _parse_release(body)
                    if release is None:
                        return CheckResult(Outcome.NO_RELEASE, None, expires)
                    return CheckResult(Outcome.OK, release, expires)
                if status == 404:
                    return CheckResult(self._classify_not_found(client, token), None, expires)
                return CheckResult(_classify_status(status, headers, token is not None), None, expires)
        except httpx.HTTPError, DownloadRefused:
            return CheckResult(Outcome.UNREACHABLE)

    def _classify_not_found(self, client: httpx.Client, token: str | None) -> Outcome:
        """GitHub answers 404 both for "no such release" and "you can't see this repository". One more request
        (the repository itself) tells them apart."""
        status, headers, _ = self._api_get(client, "", token)
        if status == 200:
            return Outcome.NO_RELEASE
        if status == 404:
            return Outcome.TOKEN_REFUSED if token else Outcome.NOT_PUBLIC
        return _classify_status(status, headers, token is not None)  # a limit hit on this request is rate_limited too

    # ---- asset download ----------------------------------------------------------------------------------------

    @contextmanager
    def open_asset(self, asset: ReleaseAsset) -> Iterator[httpx.Response]:
        """The asset's bytes as an open streamed response (status 200 checked). Redirects are followed here, by hand."""
        token = self._token_source()
        client = self._client()
        response: httpx.Response | None = None
        try:
            try:
                response = self._follow(client, f"https://{API_HOST}/repos/{REPO}/releases/assets/{asset.id}", token)
            except httpx.HTTPError:
                raise DownloadRefused("unreachable") from None
            if response.status_code != 200:
                raise DownloadRefused("bad_status")
            try:
                yield response
            except httpx.HTTPError:  # the stream failed part-way: a fixed refusal, never a traceback
                raise DownloadRefused("unreachable") from None
        finally:
            if response is not None:
                response.close()
            client.close()

    def _follow(self, client: httpx.Client, first_url: str, token: str | None) -> httpx.Response:
        url = httpx.URL(first_url)
        for hop in range(MAX_REDIRECTS + 1):
            check_url_allowed(url)
            host = url.host.lower()
            # the token only on the first request, and only to api.github.com
            headers = self._headers("application/octet-stream", token if hop == 0 else None, host)
            response = client.send(client.build_request("GET", url, headers=headers), stream=True)
            if response.status_code not in _REDIRECT_STATUSES:
                return response
            location = response.headers.get("location")
            response.close()
            if hop == MAX_REDIRECTS:
                raise DownloadRefused("too_many_redirects")
            if not location:
                raise DownloadRefused("bad_status")
            try:
                url = url.join(location)
            except httpx.InvalidURL:
                raise DownloadRefused("bad_status") from None
        raise DownloadRefused("too_many_redirects")  # not reached: the loop returns or raises
