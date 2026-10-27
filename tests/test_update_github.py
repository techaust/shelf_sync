"""SYS-06, 04-A V26 and V45: the GitHub reader (outcomes, the token, redirects, what is logged) and the download."""

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from shelfsync.update import github
from shelfsync.update.download import DownloadFailed, clear_downloads, download_zip, fetch_small, free_bytes
from shelfsync.update.github import (
    EXPIRY_HEADER,
    DownloadRefused,
    GitHubClient,
    Outcome,
    ReleaseAsset,
    check_url_allowed,
    expiry_notice,
    parse_expiry,
)
from shelfsync.update.manifest import zip_asset_name
from tests.update_support import FakeGitHub, build_release, make_keys

KEYS = make_keys(1)
TOKEN = "github_pat_" + "A1b2C3d4E5" * 4  # a made-up value; never a real token


def client_for(fake: FakeGitHub, token: str | None = None) -> GitHubClient:
    return GitHubClient(lambda: token, transport=fake.transport())


def fake_with(version: str = "0.0.2") -> tuple[FakeGitHub, str]:
    release = build_release(version, KEYS)
    fake = FakeGitHub(releases={release.tag: release}, latest_tag=release.tag)
    return fake, release.tag


# ---- outcomes --------------------------------------------------------------------------------------------------------


def test_a_release_is_read_with_its_assets() -> None:
    fake, tag = fake_with()
    result = client_for(fake).latest()
    assert result.outcome is Outcome.OK and result.release is not None
    assert result.release.tag == tag
    assert {"manifest.json", "manifest.json.sig", zip_asset_name("0.0.2")} <= set(result.release.assets)
    assert result.token_expires_at is None


def test_no_release_on_a_public_repository() -> None:
    fake = FakeGitHub()  # latest answers 404, the repository answers 200
    assert client_for(fake).latest().outcome is Outcome.NO_RELEASE
    assert [path for _, _, path, _ in fake.requests][-1].endswith("/shelf_sync")


def test_not_public_is_a_404_for_both_the_release_and_the_repository() -> None:
    fake = FakeGitHub(repo_status=404)
    assert client_for(fake).latest().outcome is Outcome.NOT_PUBLIC


def test_a_token_that_cannot_see_the_repository_is_refused() -> None:
    fake = FakeGitHub(repo_status=404)
    assert client_for(fake, TOKEN).latest().outcome is Outcome.TOKEN_REFUSED


def test_an_unreadable_repository_check_is_unreachable() -> None:
    assert client_for(FakeGitHub(repo_status=500)).latest().outcome is Outcome.UNREACHABLE


def test_a_401_is_token_refused() -> None:
    assert client_for(FakeGitHub(latest_status=401), TOKEN).latest().outcome is Outcome.TOKEN_REFUSED


@pytest.mark.parametrize("status", [403, 429])
def test_rate_limited_is_403_or_429_with_nothing_remaining(status: int) -> None:
    fake = FakeGitHub(latest_status=status, latest_headers={"x-ratelimit-remaining": "0"})
    assert client_for(fake).latest().outcome is Outcome.RATE_LIMITED


def test_a_429_is_a_limit_even_without_the_header() -> None:
    assert client_for(FakeGitHub(latest_status=429)).latest().outcome is Outcome.RATE_LIMITED


def test_a_retry_after_on_a_403_is_a_limit() -> None:
    fake = FakeGitHub(latest_status=403, latest_headers={"retry-after": "30"})
    assert client_for(fake).latest().outcome is Outcome.RATE_LIMITED


def test_a_403_without_a_limit_is_the_tokens_doing_when_one_is_set() -> None:
    fake = FakeGitHub(latest_status=403, latest_headers={"x-ratelimit-remaining": "42"})
    assert client_for(fake, TOKEN).latest().outcome is Outcome.TOKEN_REFUSED
    assert client_for(fake).latest().outcome is Outcome.UNREACHABLE


@pytest.mark.parametrize("status", [500, 502, 503, 301, 418])
def test_other_statuses_are_unreachable(status: int) -> None:
    assert client_for(FakeGitHub(latest_status=status)).latest().outcome is Outcome.UNREACHABLE


def test_a_network_failure_is_unreachable() -> None:
    fake = FakeGitHub(raise_error=httpx.ConnectError("no route"))
    assert client_for(fake).latest().outcome is Outcome.UNREACHABLE
    assert client_for(FakeGitHub(raise_error=httpx.ReadTimeout("slow"))).latest().outcome is Outcome.UNREACHABLE


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b"[]",
        b'{"tag_name":"latest","assets":[]}',
        b'{"tag_name":"v1.2","assets":[]}',
        b'{"tag_name":"v1.2.3"}',
    ],
)
def test_a_release_that_cannot_be_read_is_no_release(body: bytes) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=body))
    assert GitHubClient(lambda: None, transport=transport).latest().outcome is Outcome.NO_RELEASE


def test_the_release_for_a_version_is_read_by_its_tag() -> None:
    fake, tag = fake_with("0.0.1")
    result = client_for(fake).release_for("0.0.1")
    assert result.outcome is Outcome.OK and result.release is not None and result.release.tag == tag
    assert client_for(fake).release_for("0.0.9").outcome is Outcome.NO_RELEASE


# ---- the token ---------------------------------------------------------------------------------------------------


def test_the_token_goes_to_the_api_host_only_and_only_when_set() -> None:
    fake, _ = fake_with()
    client_for(fake).latest()
    assert not any(has_auth for *_, has_auth in fake.requests)
    fake.requests.clear()
    client_for(fake, TOKEN).latest()
    assert all(has_auth and host == "api.github.com" for _, host, _, has_auth in fake.requests)


def test_an_asset_download_sends_the_token_to_the_api_host_and_not_across_the_redirect() -> None:
    fake, _ = fake_with()
    asset_id = fake.asset_id("0.0.2", "manifest.json")
    release = client_for(fake, TOKEN).latest().release
    assert release is not None
    with client_for(fake, TOKEN).open_asset(release.assets["manifest.json"]) as response:
        assert response.status_code == 200
    api_asset = [r for r in fake.requests if r[2].endswith(f"/releases/assets/{asset_id}")]
    cdn = [r for r in fake.requests if r[1] == "release-assets.githubusercontent.com"]
    assert api_asset and api_asset[0][3] is True
    assert cdn and not any(r[3] for r in cdn)


def test_the_client_ignores_the_environment_and_does_not_follow_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}
    real = httpx.Client

    def spy(*args: object, **kwargs: object) -> httpx.Client:
        seen.update(kwargs)
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(github.httpx, "Client", spy)
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:3128")
    fake, _ = fake_with()
    client_for(fake, TOKEN).latest()
    assert seen["trust_env"] is False and seen["follow_redirects"] is False
    assert isinstance(seen["timeout"], httpx.Timeout)


# ---- the expiry (SYS-06: a notice 14 days before) --------------------------------------------------------------------

NOW = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(("days", "expected"), [(10, True), (14, True), (15, False), (60, False), (-1, True)])
def test_the_notice_starts_14_days_before_the_expiry(days: int, expected: bool) -> None:
    assert expiry_notice(NOW + timedelta(days=days), NOW) is expected


def test_no_expiry_means_no_notice() -> None:
    assert expiry_notice(None, NOW) is False


@pytest.mark.parametrize(
    ("text", "year"),
    [
        ("2026-11-30 10:00:00 UTC", 2026),
        ("2026-11-30T10:00:00Z", 2026),
        ("2026-11-30T10:00:00+02:00", 2026),
        ("2026-11-30 10:00:00", 2026),
    ],
)
def test_the_expiry_header_is_read_in_the_forms_github_uses(text: str, year: int) -> None:
    parsed = parse_expiry(text)
    assert parsed is not None and parsed.tzinfo is not None and parsed.year == year


@pytest.mark.parametrize("text", [None, "", "soon", "30/11/2026", "2026-99-99 00:00:00 UTC"])
def test_a_missing_or_unknown_expiry_form_gives_nothing(text: str | None) -> None:
    assert parse_expiry(text) is None


def test_the_expiry_is_reported_only_for_a_token_that_was_sent() -> None:
    fake, _ = fake_with()
    fake.latest_headers = {EXPIRY_HEADER: "2026-11-30 10:00:00 UTC"}
    assert client_for(fake, TOKEN).latest().token_expires_at == datetime(2026, 11, 30, 10, 0, tzinfo=UTC)
    assert client_for(fake).latest().token_expires_at is None  # no token sent: the header means nothing


def test_a_missing_expiry_header_gives_no_expiry_and_a_check_still_works() -> None:
    fake, _ = fake_with()
    result = client_for(fake, TOKEN).latest()
    assert result.outcome is Outcome.OK and result.token_expires_at is None


# ---- redirects and hosts (V45) ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("redirect", [True, False])
def test_an_asset_answers_200_or_302_and_both_work(redirect: bool) -> None:
    fake, _ = fake_with()
    fake.redirect = redirect
    release = client_for(fake).latest().release
    assert release is not None
    assert fetch_small(client_for(fake), release.assets["manifest.json"], 1_000_000).startswith(b"{")


@pytest.mark.parametrize(
    "url",
    [
        "http://api.github.com/x",
        "https://evil.example/x",
        "https://api.github.com.evil.example/x",
        "https://user:pw@api.github.com/x",
        "https://api.github.com:8443/x",
        "https://githubusercontent.com/x",
        "ftp://github.com/x",
        "https://raw.githubusercontent.com/x",
    ],
)
def test_only_https_to_the_three_hosts_is_allowed(url: str) -> None:
    with pytest.raises(DownloadRefused) as caught:
        check_url_allowed(httpx.URL(url))
    assert caught.value.code == "host_not_allowed"


@pytest.mark.parametrize(
    "url",
    [
        "https://api.github.com/x",
        "https://github.com/x",
        "https://release-assets.githubusercontent.com/x",
        "https://API.GitHub.com/x",
    ],
)
def test_the_three_hosts_pass(url: str) -> None:
    check_url_allowed(httpx.URL(url))


def asset_of(fake: FakeGitHub) -> ReleaseAsset:
    release = client_for(fake).latest().release
    assert release is not None
    return release.assets["manifest.json"]


def test_a_redirect_to_another_host_is_refused_and_the_log_names_the_host_only(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake, _ = fake_with()
    asset = asset_of(fake)
    fake.asset_override[asset.id] = lambda request: httpx.Response(
        302, headers={"location": "https://evil.example/steal?token=abc123secret"}
    )
    caplog.set_level(logging.DEBUG)
    with pytest.raises(DownloadRefused) as caught, client_for(fake, TOKEN).open_asset(asset):
        pass
    assert caught.value.code == "host_not_allowed"
    text = caplog.text
    assert "evil.example" in text
    assert "abc123secret" not in text and "token=" not in text and TOKEN not in text
    assert not any(host == "evil.example" for _, host, _, _ in fake.requests)  # never contacted


def test_a_redirect_to_http_is_refused() -> None:
    fake, _ = fake_with()
    asset = asset_of(fake)
    fake.asset_override[asset.id] = lambda r: httpx.Response(302, headers={"location": "http://github.com/x"})
    with pytest.raises(DownloadRefused), client_for(fake).open_asset(asset):
        pass


@pytest.mark.parametrize(
    "location",
    [
        "//evil.example/x",
        "https://github.com@evil.example/x",
        "https://github.com.evil.example/x",
        r"https://evil.example\@github.com/x",
    ],
)
def test_a_redirect_that_only_looks_like_an_allowed_host_is_refused(location: str) -> None:
    fake, _ = fake_with()
    asset = asset_of(fake)
    seen: list[str] = []

    def route(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.host)
        return httpx.Response(302, headers={"location": location})

    client = GitHubClient(lambda: TOKEN, transport=httpx.MockTransport(route))
    with pytest.raises(DownloadRefused) as caught, client.open_asset(asset):
        pass
    assert caught.value.code == "host_not_allowed" and seen == ["api.github.com"]  # the second host is never contacted


def test_a_relative_redirect_stays_on_the_same_host() -> None:
    fake, _ = fake_with()
    asset = asset_of(fake)
    seen: list[tuple[str, str]] = []

    def route(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.host, request.url.path))
        if request.url.path.endswith(f"/releases/assets/{asset.id}"):
            return httpx.Response(302, headers={"location": "/elsewhere"})
        return httpx.Response(200, content=b"ok")

    with GitHubClient(lambda: None, transport=httpx.MockTransport(route)).open_asset(asset) as response:
        assert response.status_code == 200
    assert seen[1] == ("api.github.com", "/elsewhere")


def test_more_than_three_redirects_are_refused() -> None:
    fake, _ = fake_with()
    asset = asset_of(fake)
    hops: list[str] = []

    def route(request: httpx.Request) -> httpx.Response:
        hops.append(request.url.host)
        return httpx.Response(302, headers={"location": "https://github.com/loop"})

    client = GitHubClient(lambda: None, transport=httpx.MockTransport(route))
    with pytest.raises(DownloadRefused) as caught, client.open_asset(asset):
        pass
    assert caught.value.code == "too_many_redirects"
    assert len(hops) == github.MAX_REDIRECTS + 1  # the first request and three redirects, then it stops


def test_exactly_three_redirects_are_followed() -> None:
    fake, _ = fake_with()
    asset = asset_of(fake)
    count = {"n": 0}

    def route(request: httpx.Request) -> httpx.Response:
        count["n"] += 1
        if count["n"] <= 3:
            return httpx.Response(302, headers={"location": "https://github.com/next"})
        return httpx.Response(200, content=b"end")

    with GitHubClient(lambda: None, transport=httpx.MockTransport(route)).open_asset(asset) as response:
        assert response.status_code == 200
        assert response.read() == b"end"


def test_a_non_200_asset_is_refused_and_a_redirect_without_location_too() -> None:
    fake, _ = fake_with()
    asset = asset_of(fake)
    fake.asset_override[asset.id] = lambda r: httpx.Response(404)
    with pytest.raises(DownloadRefused) as caught, client_for(fake).open_asset(asset):
        pass
    assert caught.value.code == "bad_status"
    fake.asset_override[asset.id] = lambda r: httpx.Response(302)
    with pytest.raises(DownloadRefused), client_for(fake).open_asset(asset):
        pass


def test_a_network_error_while_downloading_is_unreachable() -> None:
    fake, _ = fake_with()
    asset = asset_of(fake)
    fake.raise_error = httpx.ConnectError("down")
    with pytest.raises(DownloadRefused) as caught, client_for(fake).open_asset(asset):
        pass
    assert caught.value.code == "unreachable"


def test_nothing_secret_or_with_a_query_string_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    fake, _ = fake_with()
    caplog.set_level(logging.DEBUG)
    release = client_for(fake, TOKEN).latest().release
    assert release is not None
    with client_for(fake, TOKEN).open_asset(release.assets["manifest.json"]):
        pass
    assert TOKEN not in caplog.text and "Bearer" not in caplog.text and "sig=abc123" not in caplog.text


# ---- download.py --------------------------------------------------------------------------------------------------


def downloader(fake: FakeGitHub) -> tuple[GitHubClient, ReleaseAsset, object]:
    release = client_for(fake).latest().release
    assert release is not None
    asset = release.assets[zip_asset_name("0.0.2")]
    return client_for(fake), asset, next(iter(fake.releases.values())).manifest.assets[asset.name]


def test_the_zip_is_streamed_hashed_and_renamed_only_when_it_matches(tmp_path: Path) -> None:
    fake, _ = fake_with()
    client, asset, expected = downloader(fake)
    path = download_zip(client, asset, expected, tmp_path / "dl", tmp_path, lambda p: 10**12)  # type: ignore[arg-type]
    assert path.name == zip_asset_name("0.0.2") and path.is_file()
    assert [p.name for p in (tmp_path / "dl").iterdir()] == [path.name]  # no .part left


def test_a_zip_with_the_wrong_hash_is_refused_and_removed(tmp_path: Path) -> None:
    fake, _ = fake_with()
    client, asset, expected = downloader(fake)
    release = next(iter(fake.releases.values()))
    release.zip_bytes = release.zip_bytes[:-1] + bytes([release.zip_bytes[-1] ^ 1])  # same size, other bytes
    with pytest.raises(DownloadFailed) as caught:
        download_zip(client, asset, expected, tmp_path / "dl", tmp_path, lambda p: 10**12)  # type: ignore[arg-type]
    assert caught.value.code == "hash_mismatch"
    assert list((tmp_path / "dl").iterdir()) == []


def test_a_zip_longer_than_the_manifest_says_is_cut_off(tmp_path: Path) -> None:
    fake, _ = fake_with()
    client, asset, expected = downloader(fake)
    release = next(iter(fake.releases.values()))
    fake.redirect = False
    release.zip_bytes += b"x" * 5000
    with pytest.raises(DownloadFailed) as caught:
        download_zip(client, asset, expected, tmp_path / "dl", tmp_path, lambda p: 10**12)  # type: ignore[arg-type]
    assert caught.value.code == "size_mismatch"
    assert list((tmp_path / "dl").iterdir()) == []


def test_a_short_zip_is_refused(tmp_path: Path) -> None:
    fake, _ = fake_with()
    client, asset, expected = downloader(fake)
    next(iter(fake.releases.values())).zip_bytes = b"short"
    with pytest.raises(DownloadFailed) as caught:
        download_zip(client, asset, expected, tmp_path / "dl", tmp_path, lambda p: 10**12)  # type: ignore[arg-type]
    assert caught.value.code == "size_mismatch"


def test_a_manifest_size_over_the_cap_is_refused_before_any_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from shelfsync.update import download
    from shelfsync.update.manifest import FileEntry

    fake, _ = fake_with()
    client, asset, _expected = downloader(fake)
    fake.requests.clear()
    monkeypatch.setattr(download, "MAX_ZIP_BYTES", 100)
    with pytest.raises(DownloadFailed) as caught:
        download_zip(
            client, ReleaseAsset(asset.name, asset.id, 101), FileEntry(101, "0" * 64), tmp_path / "dl", tmp_path
        )
    assert caught.value.code == "too_large"
    assert fake.requests == []


def test_not_enough_free_space_is_refused_before_any_request(tmp_path: Path) -> None:
    fake, _ = fake_with()
    client, asset, expected = downloader(fake)
    fake.requests.clear()
    size = expected.size  # type: ignore[attr-defined]
    with pytest.raises(DownloadFailed) as caught:
        download_zip(client, asset, expected, tmp_path / "dl", tmp_path, lambda p: 3 * size - 1)  # type: ignore[arg-type]
    assert caught.value.code == "no_space"
    assert fake.requests == []
    download_zip(client, asset, expected, tmp_path / "dl", tmp_path, lambda p: 3 * size)  # type: ignore[arg-type]


def test_a_content_length_that_disagrees_is_refused(tmp_path: Path) -> None:
    fake, _ = fake_with()
    client, asset, expected = downloader(fake)
    fake.asset_override[asset.id] = lambda r: httpx.Response(200, content=b"x", headers={"content-length": "1"})
    with pytest.raises(DownloadFailed) as caught:
        download_zip(client, asset, expected, tmp_path / "dl", tmp_path, lambda p: 10**12)  # type: ignore[arg-type]
    assert caught.value.code == "size_mismatch"


def test_an_asset_name_that_is_a_path_is_refused(tmp_path: Path) -> None:
    fake, _ = fake_with()
    client, asset, expected = downloader(fake)
    for name in ("../evil.zip", "a/b.zip", "C:evil.zip", "CON"):
        with pytest.raises(DownloadFailed) as caught:
            download_zip(client, ReleaseAsset(name, asset.id, asset.size), expected, tmp_path / "dl", tmp_path)  # type: ignore[arg-type]
        assert caught.value.code == "bad_name"


def test_small_assets_are_capped(tmp_path: Path) -> None:
    fake, _ = fake_with()
    release = client_for(fake).latest().release
    assert release is not None
    with pytest.raises(DownloadFailed):
        fetch_small(client_for(fake), release.assets["manifest.json"], 10)
    fake.redirect = False
    asset = release.assets["manifest.json"]
    lying = ReleaseAsset(asset.name, asset.id, 5)  # the listing says small, the stream is bigger
    with pytest.raises(DownloadFailed):
        fetch_small(client_for(fake), lying, 10)


def test_the_downloads_folder_is_emptied_without_following_a_link(tmp_path: Path) -> None:
    folder = tmp_path / "dl"
    folder.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep", encoding="utf-8")
    (folder / "a.part").write_bytes(b"x")
    (folder / "sub").mkdir()
    (folder / "sub" / "b").write_bytes(b"y")
    from tests.update_support import make_dir_link

    make_dir_link(folder / "link", outside)
    clear_downloads(folder)
    assert list(folder.iterdir()) == []
    assert (outside / "keep.txt").read_text(encoding="utf-8") == "keep"
    clear_downloads(tmp_path / "missing")


def test_free_bytes_looks_at_the_nearest_existing_folder(tmp_path: Path) -> None:
    assert free_bytes(tmp_path / "not" / "yet" / "made") > 0
