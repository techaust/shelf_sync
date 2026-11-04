"""`testenv/laragon.py`, the Laragon half of the test stack (m2.8): the site guard, the TLS context, `cert`, `keys`
and `check`. No Laragon and no network beyond loopback: `check` runs against a small fake WooCommerce over HTTPS on
127.0.0.1 with a certificate the harness made (`tests/tls_support.py`), through the harness's own transport.
Credential Manager is a `MemorySecretStore` here; the real one only under `-m windows`."""

import base64
import datetime
import getpass
import json
import logging
import ssl
import subprocess
import sys
import uuid
import warnings
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization

from shelfsync.apply.woocommerce import ReadOutcome
from shelfsync.platform import secrets as platform_secrets
from shelfsync.platform.secrets import MemorySecretStore, SecretStoreError
from testenv import laragon
from tests.tls_support import RecordedRequest, RunningServer, make_certificate, tls_server

SITE = "shelfsync-test.test"
RO_KEY = "ck_" + "r0Read0nly" * 3
RO_SECRET = "cs_" + "r0S3cretRO" * 3
RW_KEY = "ck_" + "rWr1teKey0" * 3
RW_SECRET = "cs_" + "rWS3cretRW" * 3
ALL_VALUES = (RO_KEY, RO_SECRET, RW_KEY, RW_SECRET)


# ---------- the site guard ----------


@pytest.mark.parametrize(
    ("value", "url", "port"),
    [
        ("https://shelfsync-test.test", "https://shelfsync-test.test", 443),
        ("https://shelfsync-test.test/", "https://shelfsync-test.test", 443),
        ("https://SHELFSYNC-TEST.TEST", "https://shelfsync-test.test", 443),
        ("https://shelfsync-test.test:443", "https://shelfsync-test.test", 443),
        ("https://shelfsync-test.test:8443", "https://shelfsync-test.test:8443", 8443),
        ("https://shop.other-site.test", "https://shop.other-site.test", 443),
    ],
)
def test_a_test_site_is_accepted(value: str, url: str, port: int) -> None:
    site = laragon.parse_site(value)
    assert (site.url, site.port) == (url, port)


def test_the_default_site_and_its_laragon_project() -> None:
    site = laragon.parse_site(laragon.DEFAULT_SITE)
    assert (site.host, site.project) == (SITE, "shelfsync-test")


REFUSED_SITES = [
    "http://shelfsync-test.test",
    "ftp://shelfsync-test.test",
    "shelfsync-test.test",
    "https://store-a.example",
    "https://shelfsync-test.test.example",
    "https://shelfsync-test.testing",
    "https://shelfsync-test.test.",
    "https://test",
    "https://.test",
    "https://-bad.test",
    "https://bad-.test",
    "https://shelfsync_test.test",
    "https://127.0.0.1",
    "https://[::1]",
    "https://localhost",
    "https://user:password@shelfsync-test.test",
    "https://shelfsync-test.test/shop",
    "https://shelfsync-test.test/?a=1",
    "https://shelfsync-test.test/#top",
    "https://shelfsync-test.test@store-a.example",
    "",
]


@pytest.mark.parametrize("value", REFUSED_SITES)
def test_anything_but_https_on_a_test_name_is_refused(value: str) -> None:
    with pytest.raises(ValueError):
        laragon.parse_site(value)


@pytest.mark.parametrize("value", ["https://store-a.example", "http://shelfsync-test.test", "https://127.0.0.1"])
def test_check_refuses_the_site_before_anything_else(
    value: str, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    def no_secrets() -> MemorySecretStore:
        raise AssertionError("the secrets were reached")

    with pytest.raises(SystemExit) as raised:
        laragon.main(["check", "--site", value, "--cert", str(tmp_path / "x.crt")], secrets_factory=no_secrets)
    assert raised.value.code == 2
    assert "never talks to a real store" in capsys.readouterr().err


# ---------- the TLS context ----------


def write_site_cert(folder: Path, made: laragon.SiteCertificate) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{SITE}.crt"
    path.write_bytes(made.cert_pem)
    return path


@pytest.fixture(scope="module")
def site_cert() -> laragon.SiteCertificate:
    return laragon.make_site_certificate(SITE)


def test_the_context_keeps_pythons_defaults_and_trusts_the_file_only(
    site_cert: laragon.SiteCertificate, tmp_path: Path
) -> None:
    context = laragon.tls_context(write_site_cert(tmp_path, site_cert))
    assert context.verify_flags & ssl.VERIFY_X509_STRICT
    assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
    assert context.cert_store_stats()["x509"] == 1


def test_a_missing_certificate_file_is_reported(tmp_path: Path) -> None:
    with pytest.raises(laragon.HarnessError, match="Run the cert command first"):
        laragon.tls_context(tmp_path / "none.crt")


def test_a_file_without_a_certificate_is_refused(site_cert: laragon.SiteCertificate, tmp_path: Path) -> None:
    key_only = tmp_path / "key.pem"
    key_only.write_bytes(site_cert.key_pem)  # the key given as --cert by mistake
    with pytest.raises(laragon.HarnessError, match="isn't a certificate file"):
        laragon.tls_context(key_only)


def test_a_file_with_two_certificates_is_refused(site_cert: laragon.SiteCertificate, tmp_path: Path) -> None:
    two = tmp_path / "two.crt"
    two.write_bytes(site_cert.cert_pem + make_certificate().cert_pem)
    with pytest.raises(laragon.HarnessError, match="exactly one certificate"):
        laragon.tls_context(two)


def test_a_python_whose_defaults_arent_strict_is_refused(
    site_cert: laragon.SiteCertificate, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = ssl.create_default_context

    def lax(*args: object, **kwargs: object) -> ssl.SSLContext:
        context = real(*args, **kwargs)  # type: ignore[arg-type]
        context.verify_flags &= ~ssl.VERIFY_X509_STRICT
        return context

    monkeypatch.setattr(ssl, "create_default_context", lax)
    with pytest.raises(laragon.HarnessError, match="aren't on"):
        laragon.tls_context(write_site_cert(tmp_path, site_cert))


# ---------- cert ----------


@dataclass
class Restrict:
    """A stand-in for `restrict_to_current_user` that records what it was given, and the file's size at the time."""

    calls: list[tuple[Path, int]] = field(default_factory=list)
    fail: bool = False

    def __call__(self, path: Path) -> None:
        self.calls.append((path, path.stat().st_size))
        if self.fail:
            raise laragon.HarnessError("Couldn't limit it (test).")


@pytest.fixture
def fake_laragon(tmp_path: Path) -> Path:
    root = tmp_path / "laragon"
    (root / "etc" / "apache2" / "sites-enabled").mkdir(parents=True)
    (root / "www" / "shelfsync-test").mkdir(parents=True)
    return root


def run_cert(tmp_path: Path, laragon_root: Path, restrict: Restrict, *extra: str) -> int:
    return laragon.main(
        ["cert", "--dir", str(tmp_path / "tls"), "--laragon", str(laragon_root), *extra], restrict=restrict
    )


def test_cert_writes_the_pair_and_the_apache_site(
    tmp_path: Path, fake_laragon: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    restrict = Restrict()
    assert run_cert(tmp_path, fake_laragon, restrict) == 0
    crt, key = tmp_path / "tls" / f"{SITE}.crt", tmp_path / "tls" / f"{SITE}.key"
    vhost = fake_laragon / "etc" / "apache2" / "sites-enabled" / f"00-{SITE}.conf"
    assert restrict.calls == [(key, 0)]  # limited while still empty, before the key was written
    cert = x509.load_pem_x509_certificate(crt.read_bytes())
    private = serialization.load_pem_private_key(key.read_bytes(), password=None)
    assert cert.public_key() == private.public_key()
    names = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert list(names) == [x509.DNSName(SITE)]
    text = vhost.read_text(encoding="utf-8")
    root = (fake_laragon / "www" / "shelfsync-test").as_posix()
    assert "<VirtualHost *:443>" in text
    assert f"ServerName {SITE}\n" in text
    assert f'DocumentRoot "{root}"' in text
    assert f'SSLCertificateFile "{crt.as_posix()}"' in text
    assert f'SSLCertificateKeyFile "{key.as_posix()}"' in text
    assert "ServerAlias" not in text
    out = capsys.readouterr().out
    assert f"Made a certificate for {SITE}" in out and str(key) in out
    assert "PRIVATE KEY" not in out


def test_the_apache_file_is_read_before_laragons_own() -> None:
    files = laragon.cert_files(laragon.parse_site(laragon.DEFAULT_SITE), Path("tls"), Path("laragon"))
    assert sorted([files.vhost.name, f"auto.{SITE}.conf", "00-default.conf"]) == [
        "00-default.conf",
        files.vhost.name,
        f"auto.{SITE}.conf",
    ]


def test_cert_uses_the_sites_own_port(tmp_path: Path, fake_laragon: Path) -> None:
    assert run_cert(tmp_path, fake_laragon, Restrict(), "--site", f"https://{SITE}:8443") == 0
    vhost = fake_laragon / "etc" / "apache2" / "sites-enabled" / f"00-{SITE}.conf"
    assert "<VirtualHost *:8443>" in vhost.read_text(encoding="utf-8")


def test_cert_never_replaces_without_force(
    tmp_path: Path, fake_laragon: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_cert(tmp_path, fake_laragon, Restrict()) == 0
    first = (tmp_path / "tls" / f"{SITE}.crt").read_bytes()
    assert run_cert(tmp_path, fake_laragon, Restrict()) == 1
    assert "Already there" in capsys.readouterr().err
    assert (tmp_path / "tls" / f"{SITE}.crt").read_bytes() == first
    assert run_cert(tmp_path, fake_laragon, Restrict(), "--force") == 0
    assert (tmp_path / "tls" / f"{SITE}.crt").read_bytes() != first


def test_cert_needs_laragons_folder_and_the_site(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run_cert(tmp_path, tmp_path / "nowhere", Restrict()) == 1
    assert "doesn't look like Laragon's folder" in capsys.readouterr().err
    root = tmp_path / "laragon"
    (root / "etc" / "apache2" / "sites-enabled").mkdir(parents=True)
    assert run_cert(tmp_path, root, Restrict()) == 1
    assert "Make the site in Laragon first" in capsys.readouterr().err
    assert not (tmp_path / "tls").exists()


def test_a_key_that_cant_be_limited_is_never_left_behind(tmp_path: Path, fake_laragon: Path) -> None:
    assert run_cert(tmp_path, fake_laragon, Restrict(fail=True)) == 1
    assert list((tmp_path / "tls").iterdir()) == []
    assert list((fake_laragon / "etc" / "apache2" / "sites-enabled").iterdir()) == []


@pytest.mark.skipif(sys.platform == "win32", reason="the 0600 mode is the non-Windows path")
def test_off_windows_the_key_is_mode_0600(tmp_path: Path) -> None:
    path = tmp_path / "k"
    path.write_bytes(b"")
    laragon.restrict_to_current_user(path)
    assert path.stat().st_mode & 0o777 == 0o600


# ---------- keys ----------


def prompts(*answers: str) -> tuple[list[str], Callable[[str], str]]:
    asked: list[str] = []
    queue = list(answers)

    def prompt(text: str) -> str:
        asked.append(text)
        return queue.pop(0)

    return asked, prompt


def run_keys(store: MemorySecretStore, *answers: str, remove: bool = False) -> int:
    _, prompt = prompts(*answers)
    return laragon.main(["keys", *(["--remove"] if remove else [])], secrets_factory=lambda: store, prompt=prompt)


def test_keys_saves_both_pairs_under_their_own_entries(capsys: pytest.CaptureFixture[str]) -> None:
    store = MemorySecretStore()
    assert run_keys(store, RO_KEY, RO_SECRET, RW_KEY, RW_SECRET) == 0
    assert laragon.read_pair(store, laragon.READ_ONLY) == (RO_KEY, RO_SECRET)
    assert laragon.read_pair(store, laragon.READ_WRITE) == (RW_KEY, RW_SECRET)
    captured = capsys.readouterr()
    assert captured.out.splitlines() == ["Saved read-only key pair.", "Saved read/write key pair."]
    assert not any(value in captured.out + captured.err for value in ALL_VALUES)


def test_the_prompts_name_the_pair_and_say_nothing_is_shown() -> None:
    asked, prompt = prompts(RO_KEY, RO_SECRET, RW_KEY, RW_SECRET)
    laragon.save_keys(MemorySecretStore(), prompt)
    assert [text.split(" (")[0] for text in asked] == [
        "Read-only consumer key",
        "Read-only consumer secret",
        "Read/write consumer key",
        "Read/write consumer secret",
    ]
    assert all("nothing is shown" in text for text in asked)


@pytest.mark.parametrize(
    ("key", "secret"),
    [
        ("cs_" + "a1" * 12, RO_SECRET),  # prefixes swapped
        (RO_KEY, "ck_" + "a1" * 12),
        ("ck_short", RO_SECRET),
        (RO_KEY, ""),
        ("ck_" + "a1" * 10 + "!", RO_SECRET),
    ],
)
def test_a_pair_of_the_wrong_shape_isnt_saved(key: str, secret: str, capsys: pytest.CaptureFixture[str]) -> None:
    store = MemorySecretStore()
    assert run_keys(store, key, secret, "") == 1
    assert laragon.read_pair(store, laragon.READ_ONLY) is None
    out = capsys.readouterr().out
    assert "Read-only key pair not saved: a consumer key starts with ck_" in out
    assert key not in out or not key  # the typed value is never repeated back


def test_the_same_pair_twice_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    store = MemorySecretStore()
    assert run_keys(store, RO_KEY, RO_SECRET, RO_KEY, RW_SECRET) == 1
    assert laragon.read_pair(store, laragon.READ_WRITE) is None
    assert "it's the same as the other pair" in capsys.readouterr().out


def test_nothing_typed_skips_a_pair_and_keeps_the_saved_one(capsys: pytest.CaptureFixture[str]) -> None:
    store = MemorySecretStore()
    store.set("woo-ro-key", RO_KEY)
    store.set("woo-ro-secret", RO_SECRET)
    assert run_keys(store, "", RW_KEY, RW_SECRET) == 0
    assert laragon.read_pair(store, laragon.READ_ONLY) == (RO_KEY, RO_SECRET)
    assert capsys.readouterr().out.startswith("Read-only key pair skipped (nothing typed)")


class FailingSecondWrite(MemorySecretStore):
    def set(self, name: str, value: str) -> None:
        if name.endswith("-secret"):
            raise SecretStoreError("Credential Manager write failed (TestError)")
        super().set(name, value)


def test_a_half_written_pair_is_put_back(capsys: pytest.CaptureFixture[str]) -> None:
    store = FailingSecondWrite()
    MemorySecretStore.set(store, "woo-ro-key", "ck_" + "old0ld0ld0" * 3)
    assert run_keys(store, RO_KEY, RO_SECRET, "") == 1
    assert store.get("woo-ro-key") == "ck_" + "old0ld0ld0" * 3
    out = capsys.readouterr().out
    assert "Read-only key pair not saved: Credential Manager write failed (TestError)." in out


def test_keys_remove_deletes_exactly_its_entries(capsys: pytest.CaptureFixture[str]) -> None:
    store = MemorySecretStore()
    for name in ("woo-ro-key", "woo-ro-secret", "woo-rw-key", "woo-rw-secret", "unrelated", "store-1-key"):
        store.set(name, "value-" + name)
    assert run_keys(store, remove=True) == 0
    assert [name for name in ("unrelated", "store-1-key") if store.get(name)] == ["unrelated", "store-1-key"]
    assert all(store.get(name) is None for name in ("woo-ro-key", "woo-ro-secret", "woo-rw-key", "woo-rw-secret"))
    assert "Removed the test stack's two key pairs" in capsys.readouterr().out


def test_the_entries_are_never_shelfsyncs_own() -> None:
    assert laragon.SERVICE != platform_secrets.SERVICE_NAME
    names = {name for pair in laragon.PAIRS for name in (pair.key_entry, pair.secret_entry)}
    assert len(names) == 4
    assert not names & set(platform_secrets.OWNED_SECRET_NAMES)
    assert not any(name.startswith("store-") for name in names)


def test_the_default_store_is_credential_manager_under_the_test_stack_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services: list[str] = []

    def keyring_store(service: str) -> MemorySecretStore:
        services.append(service)
        return MemorySecretStore()

    monkeypatch.setattr(laragon, "KeyringSecretStore", keyring_store)
    _, prompt = prompts("", "")
    assert laragon.main(["keys"], prompt=prompt) == 0
    assert services == ["ShelfSync-TestStack"]


def test_no_credential_manager_is_reported(capsys: pytest.CaptureFixture[str]) -> None:
    def unavailable() -> MemorySecretStore:
        raise SecretStoreError("Credential Manager is available on Windows only")

    assert laragon.main(["keys"], secrets_factory=unavailable) == 1
    assert "Credential Manager is available on Windows only" in capsys.readouterr().err


def test_a_console_that_would_show_the_typing_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    def echoing(prompt: str = "") -> str:
        warnings.warn("Can not control echo on the terminal.", getpass.GetPassWarning, stacklevel=2)
        return "would have been shown"

    monkeypatch.setattr(getpass, "getpass", echoing)
    with pytest.raises(laragon.HarnessError, match="hide what you type"):
        laragon.hidden_prompt("Read-only consumer key: ")


# ---------- check, against a fake HTTPS WooCommerce ----------


def basic(key: str, secret: str) -> str:
    return "Basic " + base64.b64encode(f"{key}:{secret}".encode()).decode()


@dataclass
class FakeWoo:
    """The two REST paths Test connection reads (WooCommerce REST v3 docs), with HTTP Basic for the read-only pair."""

    authorization: str = field(default_factory=lambda: basic(RO_KEY, RO_SECRET))
    redirect_to: str | None = None
    downloadable: int = 9

    def __call__(self, request: RecordedRequest) -> tuple[int, dict[str, str], bytes]:
        json_type = {"Content-Type": "application/json"}
        if self.redirect_to is not None:
            return 302, {"Location": self.redirect_to}, b""
        if request.headers.get("Authorization") != self.authorization:
            body = {"code": "woocommerce_rest_cannot_view", "message": "Sorry.", "data": {"status": 401}}
            return 401, json_type, json.dumps(body).encode()
        if request.method == "GET" and request.path == "/wp-json/wc/v3/system_status":
            body = {"environment": {"version": "9.4.1", "wp_version": "6.8.3"}}
            return 200, json_type, json.dumps(body).encode()
        if request.method == "GET" and request.path == "/wp-json/wc/v3/products":
            headers = {**json_type, "X-WP-Total": str(self.downloadable), "X-WP-TotalPages": "9"}
            return 200, headers, json.dumps([{"id": 7}]).encode()
        body = {"code": "rest_no_route", "message": "No route.", "data": {"status": 404}}
        return 404, json_type, json.dumps(body).encode()


@pytest.fixture
def saved_keys() -> MemorySecretStore:
    store = MemorySecretStore()
    store.set("woo-ro-key", RO_KEY)
    store.set("woo-ro-secret", RO_SECRET)
    store.set("woo-rw-key", RW_KEY)
    store.set("woo-rw-secret", RW_SECRET)
    return store


@pytest.fixture
def woo(site_cert: laragon.SiteCertificate, tmp_path: Path) -> Iterator[tuple[RunningServer, FakeWoo]]:
    app = FakeWoo()
    with tls_server((site_cert.cert_pem, site_cert.key_pem), tmp_path / "server", app) as server:
        yield server, app


def run_check(store: MemorySecretStore, port: int, cert: Path) -> int:
    return laragon.main(
        ["check", "--site", f"https://{SITE}:{port}", "--cert", str(cert)], secrets_factory=lambda: store
    )


def test_check_passes_and_words_it_as_settings_does(
    woo: tuple[RunningServer, FakeWoo],
    saved_keys: MemorySecretStore,
    site_cert: laragon.SiteCertificate,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    server, _ = woo
    caplog.set_level(logging.DEBUG)
    assert run_check(saved_keys, server.port, write_site_cert(tmp_path / "trust", site_cert)) == 0
    out = capsys.readouterr()
    line = out.out.strip()
    assert line.startswith(f"https://{SITE}:{server.port}: Connected in ")
    assert line.endswith(" ms. WooCommerce 9.4.1, 9 downloadable products.")
    # the two GETs, SNI and Host on the site's name, the keys in the Authorization header only
    assert [(r.method, r.path) for r in server.record.requests] == [
        ("GET", "/wp-json/wc/v3/system_status"),
        ("GET", "/wp-json/wc/v3/products"),
    ]
    assert set(server.record.sni_names) == {SITE}
    assert set(server.record.hosts) == {f"{SITE}:{server.port}"}
    for request in server.record.requests:
        assert request.headers["Authorization"] == basic(RO_KEY, RO_SECRET)
        assert not any(value in request.target for value in ALL_VALUES)
    seen = out.out + out.err + caplog.text
    assert not any(value in seen for value in ALL_VALUES)
    assert "Store TS read test: ok" in caplog.text


def test_check_with_refused_keys_says_so(
    woo: tuple[RunningServer, FakeWoo],
    site_cert: laragon.SiteCertificate,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    server, _ = woo
    store = MemorySecretStore()
    store.set("woo-ro-key", RW_KEY)
    store.set("woo-ro-secret", RW_SECRET)
    assert run_check(store, server.port, write_site_cert(tmp_path / "trust", site_cert)) == 1
    assert capsys.readouterr().out.strip() == (
        f"https://{SITE}:{server.port}: HTTP 401: the Shop Manager key was refused."
    )


def test_check_never_follows_a_redirect(
    woo: tuple[RunningServer, FakeWoo],
    saved_keys: MemorySecretStore,
    site_cert: laragon.SiteCertificate,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    server, app = woo
    app.redirect_to = "https://store-a.example/wp-json/wc/v3/system_status"
    assert run_check(saved_keys, server.port, write_site_cert(tmp_path / "trust", site_cert)) == 1
    assert len(server.record.requests) == 1  # the conftest guard would also have refused store-a.example
    assert capsys.readouterr().out.strip() == (
        f"https://{SITE}:{server.port}: The store sent the request to another address (store-a.example). "
        "Update the store's address."
    )


def test_check_with_another_certificate_is_a_tls_error(
    woo: tuple[RunningServer, FakeWoo],
    saved_keys: MemorySecretStore,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    server, _ = woo
    other = write_site_cert(tmp_path / "trust", laragon.make_site_certificate(SITE))  # same name, another key
    assert run_check(saved_keys, server.port, other) == 1
    assert server.record.requests == []
    assert capsys.readouterr().out.strip() == (
        f"https://{SITE}:{server.port}: The store's security certificate wasn't accepted."
    )


def test_check_needs_the_read_only_pair(
    woo: tuple[RunningServer, FakeWoo],
    site_cert: laragon.SiteCertificate,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    server, _ = woo
    assert run_check(MemorySecretStore(), server.port, write_site_cert(tmp_path / "trust", site_cert)) == 1
    assert "Run the keys command first" in capsys.readouterr().out
    assert server.record.sni_names == []  # nothing was sent


def test_check_without_the_certificate_file_says_so(
    saved_keys: MemorySecretStore, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_check(saved_keys, 443, tmp_path / "missing.crt") == 1
    assert "Run the cert command first" in capsys.readouterr().err


def test_check_defaults_to_the_certificate_cert_writes() -> None:
    files = laragon.cert_files(laragon.parse_site(laragon.DEFAULT_SITE), laragon.DEFAULT_CERT_DIR, Path("x"))
    assert files.cert == laragon.DEFAULT_CERT_DIR / f"{SITE}.crt"


def test_the_transport_sends_every_request_to_loopback() -> None:
    seen: list[tuple[str, int | None, object]] = []

    class Inner(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            seen.append((request.url.host, request.url.port, request.extensions.get("sni_hostname")))
            return httpx.Response(204)

    transport = laragon.LoopbackOnlyTransport(Inner())
    with httpx.Client(transport=transport) as client:
        request = client.build_request("GET", "https://anything-at-all.test:8443/x")
        transport.handle_request(request)
        assert request.headers["Host"] == "anything-at-all.test:8443"
    assert seen == [("127.0.0.1", 8443, "anything-at-all.test")]


@pytest.mark.parametrize(
    ("reason", "status", "text"),
    [
        ("unreachable", None, "Couldn't reach the store. Check the address and your internet connection."),
        ("server_error", 500, "The store had an error (HTTP 500)."),
        ("cloudflare_52x", 522, "Cloudflare couldn't reach the store's server (HTTP 522)."),
        (
            "forbidden",
            403,
            "HTTP 403: the key is valid but isn't allowed to read this. It needs the Shop Manager role.",
        ),
        ("not_woocommerce", 404, "That address answers, but it isn't a WooCommerce store's REST API. (HTTP 404)"),
        ("some_new_reason", None, "The test failed."),
    ],
)
def test_failures_are_worded_as_settings_words_them(reason: str, status: int | None, text: str) -> None:
    assert laragon.describe(ReadOutcome(reason, status)) == text


def test_the_outcomes_without_a_failure() -> None:
    connected = ReadOutcome(None, 200, 1234, "9.4.1", "6.8.3", 1)
    assert laragon.describe(connected) == "Connected in 1,234 ms. WooCommerce 9.4.1, 1 downloadable product."
    empty = ReadOutcome(None, 200, 5, "9.4.1", "6.8.3", 0, warning="no_downloadable_products")
    assert laragon.describe(empty) == "Connected, but the store has no downloadable products yet."
    old = ReadOutcome("wc_too_old", 200, None, "5.7.0", "6.0")
    assert laragon.describe(old) == "WooCommerce 5.7.0 is too old. ShelfSync needs 5.8 or newer."


# ---------- Windows only (run on purpose with -m windows) ----------


@pytest.mark.windows
@pytest.mark.skipif(sys.platform != "win32", reason="icacls is Windows only")
def test_windows_the_key_file_is_limited_to_this_account(tmp_path: Path) -> None:
    path = tmp_path / "site.key"
    path.write_bytes(b"")
    laragon.restrict_to_current_user(path)
    listing = subprocess.run(["icacls", str(path)], check=True, capture_output=True, text=True).stdout
    entries = [line.strip() for line in listing.splitlines() if ":(" in line]
    assert len(entries) == 1, listing
    assert entries[0].endswith(":(F)") and "(I)" not in entries[0]
    assert getpass.getuser().lower() in entries[0].lower()


@pytest.mark.windows
@pytest.mark.skipif(sys.platform != "win32", reason="Credential Manager is Windows only")
def test_windows_keys_round_trip_in_a_throwaway_service(capsys: pytest.CaptureFixture[str]) -> None:
    store = platform_secrets.KeyringSecretStore(f"ShelfSync-TestStack-pytest-{uuid.uuid4().hex[:8]}")
    try:
        _, prompt = prompts(RO_KEY, RO_SECRET, RW_KEY, RW_SECRET)
        assert laragon.save_keys(store, prompt) == 0
        assert laragon.read_pair(store, laragon.READ_ONLY) == (RO_KEY, RO_SECRET)
        assert laragon.remove_keys(store) == 0
        assert laragon.read_pair(store, laragon.READ_WRITE) is None
    finally:
        for pair in laragon.PAIRS:
            store.delete(pair.key_entry)
            store.delete(pair.secret_entry)
    assert not any(value in capsys.readouterr().out for value in ALL_VALUES)


def test_the_certificate_is_valid_from_an_hour_ago_for_a_year() -> None:
    now = datetime.datetime(2026, 11, 5, 12, 0, tzinfo=datetime.UTC)
    made = laragon.make_site_certificate(SITE, now)
    cert = x509.load_pem_x509_certificate(made.cert_pem)
    assert cert.not_valid_before_utc == now - datetime.timedelta(hours=1)
    assert cert.not_valid_after_utc == now - datetime.timedelta(hours=1) + datetime.timedelta(days=365)
