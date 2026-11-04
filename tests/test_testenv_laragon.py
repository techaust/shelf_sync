"""`testenv/laragon.py`, the Laragon half of the test stack (m2.8): the site guard, the TLS context, `cert`, `keys`
and `check`. No Laragon and no network beyond loopback: `check` runs against a small fake WooCommerce over HTTPS on
127.0.0.1 with a certificate the harness made (`tests/tls_support.py`), through the harness's own transport.
Credential Manager is a `MemorySecretStore` here; the real one only under `-m windows`. `seed` is in
`test_testenv_seed.py`."""

import datetime
import getpass
import logging
import os
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
from testenv import laragon, moto_s3
from tests.laragon_support import (
    ALL_VALUES,
    RO_KEY,
    RO_SECRET,
    RW_KEY,
    RW_SECRET,
    SITE,
    basic,
    json_answer,
    site,
    store_with_keys,
    write_site_cert,
)
from tests.tls_support import RecordedRequest, RunningServer, make_certificate, tls_server

DEFAULT = site()
RO, RW = laragon.pairs_for(DEFAULT)
ENTRIES = (RO.key_entry, RO.secret_entry, RW.key_entry, RW.secret_entry)


# ---------- the site guard ----------


@pytest.mark.parametrize(
    ("value", "url", "port"),
    [
        ("https://shelfsync-test.test", "https://shelfsync-test.test", 443),
        ("https://shelfsync-test.test/", "https://shelfsync-test.test", 443),
        ("https://SHELFSYNC-TEST.TEST", "https://shelfsync-test.test", 443),
        ("https://shelfsync-test.test:443", "https://shelfsync-test.test", 443),
        ("https://shelfsync-test.test:8443", "https://shelfsync-test.test:8443", 8443),
        ("https://shelfsync-test.test:65535", "https://shelfsync-test.test:65535", 65535),
        ("https://shop.other-site.test", "https://shop.other-site.test", 443),
    ],
)
def test_a_test_site_is_accepted(value: str, url: str, port: int) -> None:
    parsed = laragon.parse_site(value)
    assert (parsed.url, parsed.port) == (url, port)


def test_the_default_site_and_its_laragon_project() -> None:
    assert (DEFAULT.host, DEFAULT.project) == (SITE, "shelfsync-test")


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
    "https://shelfsync-test.test:0",  # httpx lets port 0 through
    "https://shelfsync-test.test:65536",  # and ports past 65535
    "https://xn--bcher-kva.test",  # httpx decodes an IDNA name (bücher.test): refused
    "https://bücher.test",
    "",
]


@pytest.mark.parametrize("value", REFUSED_SITES)
def test_anything_but_https_on_a_test_name_is_refused(value: str) -> None:
    with pytest.raises(ValueError):
        laragon.parse_site(value)


@pytest.mark.parametrize("command", ["check", "keys", "seed", "cert"])
@pytest.mark.parametrize("value", ["https://store-a.example", "http://shelfsync-test.test", "https://127.0.0.1"])
def test_every_command_refuses_the_site_before_anything_else(
    command: str, value: str, capsys: pytest.CaptureFixture[str]
) -> None:
    def no_secrets() -> MemorySecretStore:
        raise AssertionError("the secrets were reached")

    with pytest.raises(SystemExit) as raised:
        laragon.main([command, "--site", value], secrets_factory=no_secrets)
    assert raised.value.code == 2
    assert "never talks to a real store" in capsys.readouterr().err


# ---------- the TLS context and the transport ----------


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


class Inner(httpx.BaseTransport):
    def __init__(self) -> None:
        self.seen: list[tuple[str, int | None, object]] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.seen.append((request.url.host, request.url.port, request.extensions.get("sni_hostname")))
        return httpx.Response(204)


def test_the_transport_sends_every_request_to_loopback() -> None:
    inner = Inner()
    transport = laragon.LoopbackOnlyTransport(inner, "anything-at-all.test")
    with httpx.Client(transport=transport) as client:
        request = client.build_request("GET", "https://anything-at-all.test:8443/x")
        transport.handle_request(request)
        assert request.headers["Host"] == "anything-at-all.test:8443"
    assert inner.seen == [("127.0.0.1", 8443, "anything-at-all.test")]


def test_a_transport_serves_one_site_only() -> None:
    """httpcore pools connections by 127.0.0.1 and the port and sets SNI only on a new one, so a shared transport
    could carry a second site's request over the first site's connection: it is refused instead."""
    inner = Inner()
    transport = laragon.LoopbackOnlyTransport(inner, SITE)
    with httpx.Client(transport=transport) as client, pytest.raises(laragon.HarnessError, match="needs its own"):
        client.get("https://other-site.test/x")
    assert inner.seen == []


def test_make_transport_gives_a_new_transport_each_time(site_cert: laragon.SiteCertificate, tmp_path: Path) -> None:
    context = laragon.tls_context(write_site_cert(tmp_path, site_cert))
    assert laragon.make_transport(context, SITE) is not laragon.make_transport(context, SITE)


# ---------- cert ----------


@dataclass
class Restrict:
    """A stand-in for `restrict_to_current_user`: records each path, whether it was a folder, and a file's size."""

    calls: list[tuple[Path, str]] = field(default_factory=list)
    fail_on_file: bool = False

    def __call__(self, path: Path) -> None:
        kind = "folder" if path.is_dir() else f"file of {path.stat().st_size} bytes"
        self.calls.append((path, kind))
        if self.fail_on_file and not path.is_dir():
            raise laragon.HarnessError("Couldn't limit it (test).")


@pytest.fixture
def fake_laragon(tmp_path: Path) -> Path:
    root = tmp_path / "laragon"
    (root / "etc" / "apache2" / "sites-enabled").mkdir(parents=True)
    (root / "www" / "shelfsync-test").mkdir(parents=True)
    return root


def run_cert(
    tmp_path: Path,
    laragon_root: Path,
    restrict: Restrict,
    *extra: str,
    private_folder: Callable[[Path], str | None] = lambda _: None,  # the real check is Windows-only (-m windows)
) -> int:
    argv = ["cert", "--dir", str(tmp_path / "tls"), "--laragon", str(laragon_root), *extra]
    return laragon.main(argv, restrict=restrict, private_folder=private_folder)


def sites_enabled(root: Path) -> Path:
    return root / "etc" / "apache2" / "sites-enabled"


def test_cert_writes_the_pair_and_the_apache_site(
    tmp_path: Path, fake_laragon: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    restrict = Restrict()
    assert run_cert(tmp_path, fake_laragon, restrict) == 0
    folder = tmp_path / "tls"
    crt, key = folder / f"{SITE}.crt", folder / f"{SITE}.key"
    vhost = sites_enabled(fake_laragon) / f"00-{SITE}.conf"
    # the folder is limited first, then the key while still empty (under its temporary name)
    assert restrict.calls == [(folder, "folder"), (folder / f"{SITE}.key.new", "file of 0 bytes")]
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
    assert sorted(path.name for path in folder.iterdir()) == [f"{SITE}.crt", f"{SITE}.key"]  # no .new left
    out = capsys.readouterr().out
    assert f"Made a certificate for {SITE}" in out and str(key) in out
    assert "PRIVATE KEY" not in out


def test_the_key_never_shows_in_a_repr(site_cert: laragon.SiteCertificate) -> None:
    assert "PRIVATE KEY" not in repr(site_cert)
    assert "BEGIN CERTIFICATE" in repr(site_cert)


def test_the_apache_file_is_read_before_laragons_own() -> None:
    files = laragon.cert_files(DEFAULT, Path("tls"), Path("laragon"))
    assert sorted([files.vhost.name, f"auto.{SITE}.conf", "00-default.conf"]) == [
        "00-default.conf",
        files.vhost.name,
        f"auto.{SITE}.conf",
    ]


def test_cert_uses_the_sites_own_port(tmp_path: Path, fake_laragon: Path) -> None:
    assert run_cert(tmp_path, fake_laragon, Restrict(), "--site", f"https://{SITE}:8443") == 0
    assert "<VirtualHost *:8443>" in (sites_enabled(fake_laragon) / f"00-{SITE}.conf").read_text(encoding="utf-8")


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


def test_a_failed_force_keeps_the_old_set(
    tmp_path: Path, fake_laragon: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """With --force the new files are written under temporary names and swapped in only when all three are there."""
    assert run_cert(tmp_path, fake_laragon, Restrict()) == 0
    folder = tmp_path / "tls"
    before = {path.name: path.read_bytes() for path in folder.iterdir()}
    vhost_before = (sites_enabled(fake_laragon) / f"00-{SITE}.conf").read_bytes()
    assert run_cert(tmp_path, fake_laragon, Restrict(fail_on_file=True), "--force") == 1
    assert {path.name: path.read_bytes() for path in folder.iterdir()} == before
    assert (sites_enabled(fake_laragon) / f"00-{SITE}.conf").read_bytes() == vhost_before
    assert "Couldn't limit it" in capsys.readouterr().err


def test_a_file_system_failure_is_reported_not_raised(
    tmp_path: Path, fake_laragon: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def no_replace(source: object, target: object) -> None:
        raise PermissionError(13, "Access is denied", str(target))

    monkeypatch.setattr(os, "replace", no_replace)
    assert run_cert(tmp_path, fake_laragon, Restrict()) == 1
    assert "Couldn't write the certificate files (Access is denied)" in capsys.readouterr().err
    assert list((tmp_path / "tls").iterdir()) == []  # the temporary files are gone
    assert list(sites_enabled(fake_laragon).iterdir()) == []


def test_cert_needs_laragons_folder_and_the_site(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run_cert(tmp_path, tmp_path / "nowhere", Restrict()) == 1
    assert "doesn't look like Laragon's folder" in capsys.readouterr().err
    root = tmp_path / "laragon"
    sites_enabled(root).mkdir(parents=True)
    assert run_cert(tmp_path, root, Restrict()) == 1
    assert "Make the site in Laragon first" in capsys.readouterr().err
    assert not (tmp_path / "tls").exists()


def test_cert_wont_limit_a_folder_holding_other_files(
    tmp_path: Path, fake_laragon: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "tls").mkdir()
    (tmp_path / "tls" / "notes.txt").write_text("mine", encoding="utf-8")
    restrict = Restrict()
    assert run_cert(tmp_path, fake_laragon, restrict) == 1
    assert "holds other files (notes.txt)" in capsys.readouterr().err
    assert restrict.calls == []


def test_a_key_that_cant_be_limited_is_never_left_behind(tmp_path: Path, fake_laragon: Path) -> None:
    assert run_cert(tmp_path, fake_laragon, Restrict(fail_on_file=True)) == 1
    assert list((tmp_path / "tls").iterdir()) == []
    assert list(sites_enabled(fake_laragon).iterdir()) == []


@pytest.mark.skipif(sys.platform == "win32", reason="the 0600 and 0700 modes are the non-Windows path")
def test_off_windows_the_key_and_folder_are_owner_only(tmp_path: Path) -> None:
    path = tmp_path / "k"
    path.write_bytes(b"")
    laragon.restrict_to_current_user(path)
    assert path.stat().st_mode & 0o777 == 0o600
    laragon.restrict_to_current_user(tmp_path)
    assert tmp_path.stat().st_mode & 0o777 == 0o700


# ---------- keys ----------


def prompts(*answers: str) -> tuple[list[str], Callable[[str], str]]:
    asked: list[str] = []
    queue = list(answers)

    def prompt(text: str) -> str:
        asked.append(text)
        return queue.pop(0)

    return asked, prompt


def run_keys(store: MemorySecretStore, *answers: str, remove: bool = False, host: str = SITE) -> int:
    _, prompt = prompts(*answers)
    argv = ["keys", "--site", f"https://{host}", *(["--remove"] if remove else [])]
    return laragon.main(argv, secrets_factory=lambda: store, prompt=prompt)


def test_keys_saves_both_pairs_under_the_sites_own_entries(capsys: pytest.CaptureFixture[str]) -> None:
    store = MemorySecretStore()
    assert run_keys(store, RO_KEY, RO_SECRET, RW_KEY, RW_SECRET) == 0
    assert ENTRIES == (
        "woo-shelfsync-test.test-ro-key",
        "woo-shelfsync-test.test-ro-secret",
        "woo-shelfsync-test.test-rw-key",
        "woo-shelfsync-test.test-rw-secret",
    )
    assert laragon.read_pair(store, RO) == (RO_KEY, RO_SECRET)
    assert laragon.read_pair(store, RW) == (RW_KEY, RW_SECRET)
    captured = capsys.readouterr()
    assert captured.out.splitlines() == [
        f"Saved read-only key pair for {SITE}.",
        f"Saved read/write key pair for {SITE}.",
    ]
    assert not any(value in captured.out + captured.err for value in ALL_VALUES)


def test_two_sites_keep_their_own_keys() -> None:
    store = MemorySecretStore()
    assert run_keys(store, RO_KEY, RO_SECRET, RW_KEY, RW_SECRET) == 0
    other_ro, other_rw = (
        ("ck_" + "0therR0key" * 3, "cs_" + "0therR0sec" * 3),
        ("ck_" + "0therRWkey" * 3, "cs_" + "0therRWsec" * 3),
    )
    assert run_keys(store, *other_ro, *other_rw, host="twin.test") == 0
    twin_ro, _ = laragon.pairs_for(site(host="twin.test"))
    assert laragon.read_pair(store, twin_ro) == other_ro
    assert laragon.read_pair(store, RO) == (RO_KEY, RO_SECRET)
    assert run_keys(store, remove=True, host="twin.test") == 0
    assert laragon.read_pair(store, twin_ro) is None
    assert laragon.read_pair(store, RO) == (RO_KEY, RO_SECRET)  # --remove deleted only that site's entries


def test_the_prompts_name_the_pair_and_the_site_and_say_nothing_is_shown() -> None:
    asked, prompt = prompts(RO_KEY, RO_SECRET, RW_KEY, RW_SECRET)
    laragon.save_keys(MemorySecretStore(), prompt, DEFAULT)
    assert [text.split(" (")[0] for text in asked] == [
        f"Read-only consumer key for {SITE}",
        f"Read-only consumer secret for {SITE}",
        f"Read/write consumer key for {SITE}",
        f"Read/write consumer secret for {SITE}",
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
    assert laragon.read_pair(store, RO) is None
    out = capsys.readouterr().out
    assert "Read-only key pair not saved: a consumer key starts with ck_" in out
    assert key not in out  # the typed value is never repeated back


def test_the_same_pair_twice_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    store = MemorySecretStore()
    assert run_keys(store, RO_KEY, RO_SECRET, RO_KEY, RW_SECRET) == 1
    assert laragon.read_pair(store, RW) is None
    assert "it's the same as the other pair" in capsys.readouterr().out


def test_nothing_typed_skips_a_pair_and_keeps_the_saved_one(capsys: pytest.CaptureFixture[str]) -> None:
    store = MemorySecretStore()
    store.set(RO.key_entry, RO_KEY)
    store.set(RO.secret_entry, RO_SECRET)
    assert run_keys(store, "", RW_KEY, RW_SECRET) == 0
    assert laragon.read_pair(store, RO) == (RO_KEY, RO_SECRET)
    assert capsys.readouterr().out.startswith("Read-only key pair skipped (nothing typed)")


class FailingSecondWrite(MemorySecretStore):
    def set(self, name: str, value: str) -> None:
        if name.endswith("-secret"):
            raise SecretStoreError("Credential Manager write failed (TestError)")
        super().set(name, value)


def test_a_half_written_pair_is_put_back(capsys: pytest.CaptureFixture[str]) -> None:
    store = FailingSecondWrite()
    MemorySecretStore.set(store, RO.key_entry, "ck_" + "old0ld0ld0" * 3)
    assert run_keys(store, RO_KEY, RO_SECRET, "") == 1
    assert store.get(RO.key_entry) == "ck_" + "old0ld0ld0" * 3
    out = capsys.readouterr().out
    assert "Read-only key pair not saved: Credential Manager write failed (TestError)." in out


def test_keys_remove_deletes_exactly_its_entries(capsys: pytest.CaptureFixture[str]) -> None:
    store = MemorySecretStore()
    for name in (*ENTRIES, "unrelated", "store-1-key", "woo-ro-key"):
        store.set(name, "value-" + name)
    assert run_keys(store, remove=True) == 0
    assert [name for name in ("unrelated", "store-1-key", "woo-ro-key") if store.get(name)] == [
        "unrelated",
        "store-1-key",
        "woo-ro-key",
    ]
    assert all(store.get(name) is None for name in ENTRIES)
    assert f"Removed the two key pairs of {SITE}" in capsys.readouterr().out


@pytest.mark.parametrize("host", [SITE, "store-1.test", "install-token.test", "s3.test", "a.b.test"])
def test_the_entries_are_never_shelfsyncs_own(host: str) -> None:
    assert laragon.SERVICE != platform_secrets.SERVICE_NAME
    names = {name for pair in laragon.pairs_for(site(host=host)) for name in (pair.key_entry, pair.secret_entry)}
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


@dataclass
class FakeWoo:
    """The two REST paths Test connection reads (WooCommerce REST v3 docs), with HTTP Basic for the read-only pair."""

    authorization: str = field(default_factory=lambda: basic(RO_KEY, RO_SECRET))
    redirect_to: str | None = None
    downloadable: int = 10  # what seed's samples give (runbook §3.5)

    def __call__(self, request: RecordedRequest) -> tuple[int, dict[str, str], bytes]:
        if self.redirect_to is not None:
            return 302, {"Location": self.redirect_to}, b""
        if request.headers.get("Authorization") != self.authorization:
            return json_answer(401, {"code": "woocommerce_rest_cannot_view", "message": "Sorry."})
        if request.method == "GET" and request.path == "/wp-json/wc/v3/system_status":
            return json_answer(200, {"environment": {"version": "9.4.1", "wp_version": "6.8.3"}})
        if request.method == "GET" and request.path == "/wp-json/wc/v3/products":
            return json_answer(200, [{"id": 7}], {"X-WP-Total": str(self.downloadable), "X-WP-TotalPages": "9"})
        return json_answer(404, {"code": "rest_no_route", "message": "No route."})


@pytest.fixture
def woo(site_cert: laragon.SiteCertificate, tmp_path: Path) -> Iterator[tuple[RunningServer, FakeWoo]]:
    app = FakeWoo()
    with tls_server((site_cert.cert_pem, site_cert.key_pem), tmp_path / "server", app) as server:
        yield server, app


def run_check(store: MemorySecretStore, port: int, cert: Path, host: str = SITE) -> int:
    return laragon.main(
        ["check", "--site", f"https://{host}:{port}", "--cert", str(cert)], secrets_factory=lambda: store
    )


def test_check_passes_and_words_it_as_settings_does(
    woo: tuple[RunningServer, FakeWoo],
    site_cert: laragon.SiteCertificate,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    server, _ = woo
    caplog.set_level(logging.DEBUG)
    assert run_check(store_with_keys(), server.port, write_site_cert(tmp_path / "trust", site_cert)) == 0
    out = capsys.readouterr()
    line = out.out.strip()
    assert line.startswith(f"https://{SITE}:{server.port}: Connected in ")
    assert line.endswith(" ms. WooCommerce 9.4.1, 10 downloadable products.")
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


def test_two_sites_on_one_port_each_get_their_own_connection(
    site_cert: laragon.SiteCertificate, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Like Laragon: two name-based sites on one port, the certificate chosen by SNI. Each check makes its own
    transport, so the second site gets a new connection with its own SNI and certificate."""
    twin = laragon.make_site_certificate("twin.test")
    store = store_with_keys()
    for pair, value in zip(
        laragon.pairs_for(site(host="twin.test")), ((RO_KEY, RO_SECRET), (RW_KEY, RW_SECRET)), strict=True
    ):
        store.set(pair.key_entry, value[0])
        store.set(pair.secret_entry, value[1])
    by_name = {"twin.test": (twin.cert_pem, twin.key_pem)}
    with tls_server((site_cert.cert_pem, site_cert.key_pem), tmp_path / "server", FakeWoo(), by_name) as server:
        assert run_check(store, server.port, write_site_cert(tmp_path / "a", site_cert)) == 0
        assert run_check(store, server.port, write_site_cert(tmp_path / "b", twin, "twin.test"), "twin.test") == 0
        # the fake server closes each connection (HTTP/1.0), so two connections per check, each with its own SNI
        assert server.record.sni_names == [SITE, SITE, "twin.test", "twin.test"]
        assert server.record.hosts == [f"{SITE}:{server.port}"] * 2 + [f"twin.test:{server.port}"] * 2
    assert capsys.readouterr().out.count("Connected in ") == 2


def test_check_with_refused_keys_says_so(
    woo: tuple[RunningServer, FakeWoo],
    site_cert: laragon.SiteCertificate,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    server, _ = woo
    store = store_with_keys(ro=(RW_KEY, RW_SECRET))
    assert run_check(store, server.port, write_site_cert(tmp_path / "trust", site_cert)) == 1
    assert capsys.readouterr().out.strip() == (
        f"https://{SITE}:{server.port}: HTTP 401: the Shop Manager key was refused."
    )


def test_check_never_follows_a_redirect(
    woo: tuple[RunningServer, FakeWoo],
    site_cert: laragon.SiteCertificate,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    server, app = woo
    app.redirect_to = "https://store-a.example/wp-json/wc/v3/system_status"
    assert run_check(store_with_keys(), server.port, write_site_cert(tmp_path / "trust", site_cert)) == 1
    assert len(server.record.requests) == 1  # the conftest guard would also have refused store-a.example
    assert capsys.readouterr().out.strip() == (
        f"https://{SITE}:{server.port}: The store sent the request to another address (store-a.example). "
        "Update the store's address."
    )


def test_check_words_a_redirect_to_an_unreadable_address(
    woo: tuple[RunningServer, FakeWoo],
    site_cert: laragon.SiteCertificate,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """httpx can't decode this `Location` and `WooClient` lets the error through; the harness words it instead."""
    server, app = woo
    app.redirect_to = "https://xn--a.test/"
    assert run_check(store_with_keys(), server.port, write_site_cert(tmp_path / "trust", site_cert)) == 1
    assert capsys.readouterr().out.strip() == (
        f"https://{SITE}:{server.port}: The store sent the request to another address. Update the store's address."
    )


def test_check_with_another_certificate_is_a_tls_error(
    woo: tuple[RunningServer, FakeWoo], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    server, _ = woo
    other = write_site_cert(tmp_path / "trust", laragon.make_site_certificate(SITE))  # same name, another key
    assert run_check(store_with_keys(), server.port, other) == 1
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


def test_check_without_the_certificate_file_says_so(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run_check(store_with_keys(), 443, tmp_path / "missing.crt") == 1
    assert "Run the cert command first" in capsys.readouterr().err


def test_check_defaults_to_the_certificate_cert_writes() -> None:
    files = laragon.cert_files(DEFAULT, laragon.DEFAULT_CERT_DIR, Path("x"))
    assert files.cert == laragon.default_cert(DEFAULT) == laragon.DEFAULT_CERT_DIR / f"{SITE}.crt"


def test_the_moto_defaults_match_the_moto_script() -> None:
    expected = f"http://{moto_s3.HOST}:{moto_s3.DEFAULT_PORT}"
    assert expected == laragon.DEFAULT_MOTO
    assert laragon.DEFAULT_BUCKET == moto_s3.DEFAULT_BUCKET
    assert laragon.DEFAULT_REGION == moto_s3.DEFAULT_REGION


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
        ("not_woocommerce", 404, "That address answers, but it isn't a WooCommerce store's REST API (HTTP 404)."),
        (
            "unreachable",
            502,
            "Couldn't reach the store (HTTP 502). Check the address and your internet connection.",
        ),
        (
            "blocked",
            403,
            "Something in front of the store (a firewall or a security check) blocked the request (HTTP 403).",
        ),
        ("bad_response", 200, "The store's answer wasn't what ShelfSync expected."),  # under 300: no status
        ("wc_too_old", 200, "The store's WooCommerce is too old. ShelfSync needs 5.8 or newer."),
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


def test_a_failed_second_swap_puts_the_old_set_back(
    tmp_path: Path, fake_laragon: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_cert(tmp_path, fake_laragon, Restrict()) == 0
    folder, vhost = tmp_path / "tls", sites_enabled(fake_laragon) / f"00-{SITE}.conf"
    before = {path.name: path.read_bytes() for path in folder.iterdir()} | {vhost.name: vhost.read_bytes()}
    real_replace = os.replace
    swaps: list[str] = []

    def second_swap_fails(source: str | Path, target: str | Path) -> None:
        if str(source).endswith(".new"):
            swaps.append(str(target))
            if len(swaps) == 2:
                raise PermissionError(13, "Access is denied", str(target))
        real_replace(source, target)

    monkeypatch.setattr(os, "replace", second_swap_fails)
    assert run_cert(tmp_path, fake_laragon, Restrict(), "--force") == 1
    after = {path.name: path.read_bytes() for path in folder.iterdir()} | {vhost.name: vhost.read_bytes()}
    assert after == before  # the key that was swapped in is undone, and every old file is back; no .new or .old
    assert sorted(path.name for path in sites_enabled(fake_laragon).iterdir()) == [vhost.name]
    assert "Nothing was changed." in capsys.readouterr().err


def test_a_swap_that_cant_be_undone_says_to_run_force_again(
    tmp_path: Path, fake_laragon: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_cert(tmp_path, fake_laragon, Restrict()) == 0
    real_replace = os.replace
    news: list[str] = []

    def second_swap_and_undo_fail(source: str | Path, target: str | Path) -> None:
        if str(source).endswith(".new"):
            news.append(str(target))
            if len(news) == 2:
                raise PermissionError(13, "Access is denied", str(target))
        if str(source).endswith(".old") and news:
            raise PermissionError(13, "Access is denied", str(target))
        real_replace(source, target)

    monkeypatch.setattr(os, "replace", second_swap_and_undo_fail)
    assert run_cert(tmp_path, fake_laragon, Restrict(), "--force") == 1
    assert "half replaced and couldn't be put back. Run cert --force again." in capsys.readouterr().err


def test_cert_refuses_an_existing_folder_others_may_open(
    tmp_path: Path, fake_laragon: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "tls").mkdir()
    restrict = Restrict()
    assert run_cert(tmp_path, fake_laragon, restrict, private_folder=lambda _: "other accounts may open it") == 1
    assert "already exists, but other accounts may open it" in capsys.readouterr().err
    assert restrict.calls == []


def test_cert_shows_the_expiry_in_local_time_with_the_zone(
    tmp_path: Path, fake_laragon: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_cert(tmp_path, fake_laragon, Restrict()) == 0
    cert = x509.load_pem_x509_certificate((tmp_path / "tls" / f"{SITE}.crt").read_bytes())
    local = cert.not_valid_after_utc.astimezone()
    line = capsys.readouterr().out.splitlines()[0]
    assert line == f"Made a certificate for {SITE}, valid until {local:%Y-%m-%d %H:%M} {local.tzname()}."
    assert "(UTC)" not in line


def test_the_certificate_is_valid_from_an_hour_ago_for_a_year() -> None:
    now = datetime.datetime(2026, 11, 5, 12, 0, tzinfo=datetime.UTC)
    made = laragon.make_site_certificate(SITE, now)
    cert = x509.load_pem_x509_certificate(made.cert_pem)
    assert cert.not_valid_before_utc == now - datetime.timedelta(hours=1)
    assert cert.not_valid_after_utc == now - datetime.timedelta(hours=1) + datetime.timedelta(days=365)


# ---------- Windows only (run on purpose with -m windows) ----------


def icacls_entries(path: Path) -> list[str]:
    listing = subprocess.run(["icacls", str(path)], check=True, capture_output=True, text=True).stdout
    return [line.strip() for line in listing.splitlines() if ":(" in line]


@pytest.mark.windows
@pytest.mark.skipif(sys.platform != "win32", reason="icacls is Windows only")
def test_windows_the_key_file_is_limited_to_this_account(tmp_path: Path) -> None:
    path = tmp_path / "site.key"
    path.write_bytes(b"")
    laragon.restrict_to_current_user(path)
    entries = icacls_entries(path)
    assert len(entries) == 1, entries
    assert entries[0].endswith(":(F)") and "(I)" not in entries[0]
    assert getpass.getuser().lower() in entries[0].lower()


@pytest.mark.windows
@pytest.mark.skipif(sys.platform != "win32", reason="Windows' security calls are Windows only")
def test_windows_only_a_folder_limited_to_this_account_is_accepted(tmp_path: Path) -> None:
    shared = tmp_path / "shared"
    shared.mkdir()  # inherits the parent's entries (SYSTEM, Administrators and this account, at least)
    assert laragon.folder_is_private(shared) == "other accounts may open it"
    mine = tmp_path / "mine"
    mine.mkdir()
    laragon.restrict_to_current_user(mine)
    assert laragon.folder_is_private(mine) is None
    owner, grantees = laragon.folder_access(mine)
    assert owner.startswith("S-1-") and len(grantees) == 1 and grantees[0].startswith("S-1-5-21-")


@pytest.mark.windows
@pytest.mark.skipif(sys.platform != "win32", reason="icacls is Windows only")
def test_windows_the_certificate_folder_is_limited_to_this_account(tmp_path: Path) -> None:
    folder = tmp_path / "tls"
    folder.mkdir()
    laragon.restrict_to_current_user(folder)
    entries = icacls_entries(folder)
    assert len(entries) == 1, entries
    assert entries[0].endswith(":(OI)(CI)(F)") and "(I)" not in entries[0].split(":", 1)[1].replace("(OI)(CI)", "")
    assert getpass.getuser().lower() in entries[0].lower()
    inside = folder / f"{SITE}.crt"
    inside.write_bytes(b"x")  # a file made in it inherits only this account
    inherited = icacls_entries(inside)
    assert len(inherited) == 1 and getpass.getuser().lower() in inherited[0].lower(), inherited


@pytest.mark.windows
@pytest.mark.skipif(sys.platform != "win32", reason="Credential Manager is Windows only")
def test_windows_keys_round_trip_in_a_throwaway_service(capsys: pytest.CaptureFixture[str]) -> None:
    store = platform_secrets.KeyringSecretStore(f"ShelfSync-TestStack-pytest-{uuid.uuid4().hex[:8]}")
    try:
        _, prompt = prompts(RO_KEY, RO_SECRET, RW_KEY, RW_SECRET)
        assert laragon.save_keys(store, prompt, DEFAULT) == 0
        assert laragon.read_pair(store, RO) == (RO_KEY, RO_SECRET)
        assert laragon.remove_keys(store, DEFAULT) == 0
        assert laragon.read_pair(store, RW) is None
    finally:
        for name in ENTRIES:
            store.delete(name)
    assert not any(value in capsys.readouterr().out for value in ALL_VALUES)
