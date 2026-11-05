"""04-A V57: does a certificate shaped like Laragon's work as httpx's `verify=` context for `https://shelfsync-test.test`
under Python 3.15's defaults? (m2.8, the Laragon half of the test stack.)

Every client context here is `ssl.create_default_context(cafile=<the one certificate file>)` and nothing else: the
defaults stay (`VERIFY_X509_STRICT` on, hostname check on, `CERT_REQUIRED`), and only that file is trusted. The socket
goes to 127.0.0.1 while SNI and the hostname check are on the `.test` name (`tests/tls_support.py`, httpcore's
`sni_hostname` extension); no name is looked up.

**What it showed (2026-11-05, Python 3.15.2, OpenSSL 3.5.9):** the certificate's chain is accepted (strict mode and a
self-signed `CA:FALSE` certificate as its own trust anchor are fine: `localhost` and `127.0.0.1`, its exact names,
pass), but its one-label wildcard `*.test` never matches `shelfsync-test.test`: "Hostname mismatch" (measured: a
wildcard matches only with at least two labels after the `*`). A certificate naming `shelfsync-test.test` exactly, or
a wildcard with two labels after the star, is accepted. So Laragon's certificate as it was read on 2026-11-05 can't
be used for the site.

**Chosen (owner, 2026-11-05, run file m2.8 §2 option 2):** the harness makes the site's own certificate
(`testenv.laragon.make_site_certificate`: self-signed, `CA:FALSE`, naming exactly the site, serverAuth). The last tests
here pin that shape through the harness's own `tls_context` and `make_transport` (every socket to 127.0.0.1).
"""

import ssl
from pathlib import Path

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.x509.oid import ExtendedKeyUsageOID

from testenv import laragon
from tests.tls_support import (
    LARAGON_DNS_NAMES,
    SITE_NAME,
    LoopbackTransport,
    TestCertificate,
    make_certificate,
    tls_server,
    verification_error,
)

HOSTNAME_MISMATCH = 62  # X509_V_ERR_HOSTNAME_MISMATCH
SELF_SIGNED_LEAF = 18  # X509_V_ERR_DEPTH_ZERO_SELF_SIGNED_CERT


@pytest.fixture(scope="module")
def laragon_like() -> TestCertificate:
    return make_certificate()


@pytest.fixture(scope="module")
def site_exact() -> TestCertificate:
    """The fix the probe points at: the same shape, naming the site exactly."""
    return make_certificate(dns_names=(SITE_NAME,), ip_addresses=())


def context_from(certificate: TestCertificate, folder: Path) -> ssl.SSLContext:
    """What `testenv/laragon.py` will build from the certificate file: Python's defaults plus that one file."""
    cert_path, _ = certificate.write(folder, "trusted")
    return ssl.create_default_context(cafile=str(cert_path))


def fetch(context: ssl.SSLContext | None, port: int, name: str) -> tuple[httpx.Response, LoopbackTransport]:
    inner = httpx.HTTPTransport(trust_env=False) if context is None else httpx.HTTPTransport(verify=context)
    transport = LoopbackTransport(inner, port)
    with httpx.Client(transport=transport, trust_env=False, follow_redirects=False) as client:
        return client.get(f"https://{name}/"), transport


def refusal(context: ssl.SSLContext | None, port: int, name: str) -> ssl.SSLCertVerificationError:
    with pytest.raises(httpx.ConnectError) as raised:
        fetch(context, port, name)
    error = verification_error(raised.value)
    assert error is not None, f"not a certificate verification error: {raised.value!r}"
    return error


def test_v57_the_lookalike_has_laragons_shape(laragon_like: TestCertificate) -> None:
    cert = x509.load_pem_x509_certificate(laragon_like.cert_pem)
    assert cert.subject == cert.issuer  # self-signed
    assert cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca is False
    usage = cert.extensions.get_extension_for_class(x509.KeyUsage).value
    assert usage.digital_signature and usage.key_encipherment and not usage.key_cert_sign
    assert cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value == x509.ExtendedKeyUsage(
        [ExtendedKeyUsageOID.SERVER_AUTH]
    )
    names = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert tuple(names.get_values_for_type(x509.DNSName)) == LARAGON_DNS_NAMES
    assert [str(ip) for ip in names.get_values_for_type(x509.IPAddress)] == ["127.0.0.1"]
    assert cert.extensions.get_extension_for_class(x509.SubjectKeyIdentifier)
    with pytest.raises(x509.ExtensionNotFound):
        cert.extensions.get_extension_for_class(x509.AuthorityKeyIdentifier)
    assert not any(extension.critical for extension in cert.extensions)


def test_v57_the_context_is_pythons_default_with_only_the_file(laragon_like: TestCertificate, tmp_path: Path) -> None:
    context = context_from(laragon_like, tmp_path)
    assert context.verify_flags & ssl.VERIFY_X509_STRICT
    assert context.check_hostname is True
    assert context.verify_mode == ssl.CERT_REQUIRED
    # the file and nothing else (no system or certifi store); `CA:FALSE`, so it isn't counted as a CA
    assert context.cert_store_stats() == {"x509": 1, "crl": 0, "x509_ca": 0}


def test_v57_recorded_laragons_wildcard_doesnt_match_the_site(laragon_like: TestCertificate, tmp_path: Path) -> None:
    """Recorded, the V57 result: `*.test` never matches `shelfsync-test.test`, with strict mode or without it being
    the cause (the next test). SNI did name the site, so this is the hostname check, not the routing."""
    context = context_from(laragon_like, tmp_path)
    with tls_server(laragon_like, tmp_path / "server") as server:
        error = refusal(context, server.port, SITE_NAME)
        assert server.record.sni_names == [SITE_NAME]
    assert error.verify_code == HOSTNAME_MISMATCH
    assert error.verify_message == f"Hostname mismatch, certificate is not valid for '{SITE_NAME}'."


@pytest.mark.parametrize("name", ["shelfsync-test.localhost", "deep.shelfsync-test.test"])
def test_v57_recorded_other_names_under_laragons_wildcards_are_refused(
    laragon_like: TestCertificate, tmp_path: Path, name: str
) -> None:
    with tls_server(laragon_like, tmp_path / "server") as server:
        error = refusal(context_from(laragon_like, tmp_path), server.port, name)
    assert error.verify_code == HOSTNAME_MISMATCH


@pytest.mark.parametrize("name", ["localhost", "127.0.0.1"])
def test_v57_laragons_chain_itself_passes_strict_verification(
    laragon_like: TestCertificate, tmp_path: Path, name: str
) -> None:
    """The same certificate is accepted for its exact names: strict mode, `CA:FALSE`, no AKID and being its own trust
    anchor are all fine. Only the wildcard fails."""
    with tls_server(laragon_like, tmp_path / "server") as server:
        response, _ = fetch(context_from(laragon_like, tmp_path), server.port, name)
        assert server.record.hosts == [name]
    assert response.status_code == 200


def test_v57_a_certificate_naming_the_site_is_accepted(site_exact: TestCertificate, tmp_path: Path) -> None:
    with tls_server(site_exact, tmp_path / "server") as server:
        response, transport = fetch(context_from(site_exact, tmp_path), server.port, SITE_NAME)
        assert server.record.sni_names == [SITE_NAME]  # SNI on the site's name, though the socket went to 127.0.0.1
        assert server.record.hosts == [SITE_NAME]
    assert response.status_code == 200
    assert transport.requests[0][1] == f"https://{SITE_NAME}/"


@pytest.mark.parametrize("name", ["other.test", f"deep.{SITE_NAME}", "shelfsync-test.example"])
def test_v57_a_name_outside_the_certificate_is_refused(site_exact: TestCertificate, tmp_path: Path, name: str) -> None:
    with tls_server(site_exact, tmp_path / "server") as server:
        error = refusal(context_from(site_exact, tmp_path), server.port, name)
    assert error.verify_code == HOSTNAME_MISMATCH


def test_v57_a_different_self_signed_certificate_is_refused(site_exact: TestCertificate, tmp_path: Path) -> None:
    """Same names, another key: the file trusts only its own certificate."""
    impostor = make_certificate(dns_names=(SITE_NAME,), ip_addresses=())
    with tls_server(impostor, tmp_path / "server") as server:
        error = refusal(context_from(site_exact, tmp_path), server.port, SITE_NAME)
        assert server.record.hosts == []  # no request was sent
    assert error.verify_code == SELF_SIGNED_LEAF


def test_v57_without_the_file_the_default_trust_refuses_it(site_exact: TestCertificate, tmp_path: Path) -> None:
    """httpx's own default (certifi, `verify=True`) doesn't know the certificate: trust comes from the file only."""
    with tls_server(site_exact, tmp_path / "server") as server:
        error = refusal(None, server.port, SITE_NAME)
    assert error.verify_code == SELF_SIGNED_LEAF


@pytest.mark.parametrize(
    ("pattern", "name", "accepted"),
    [
        ("*.test", "shelfsync-test.test", False),
        ("*.shelfsync.test", "site.shelfsync.test", True),
        ("*.shelfsync.test", "shelfsync.test", False),
    ],
)
def test_v57_recorded_openssl_wildcards_need_two_labels_after_the_star(
    tmp_path: Path, pattern: str, name: str, accepted: bool
) -> None:
    certificate = make_certificate(dns_names=(pattern,), ip_addresses=())
    with tls_server(certificate, tmp_path / "server") as server:
        if accepted:
            response, _ = fetch(context_from(certificate, tmp_path), server.port, name)
            assert response.status_code == 200
        else:
            assert refusal(context_from(certificate, tmp_path), server.port, name).verify_code == HOSTNAME_MISMATCH


# ---------- the chosen shape: the harness's own site certificate (owner, 2026-11-05) ----------


@pytest.fixture(scope="module")
def harness_made() -> laragon.SiteCertificate:
    return laragon.make_site_certificate(SITE_NAME)


def harness_fetch(cert_path: Path, port: int, name: str = SITE_NAME) -> httpx.Response:
    """Through the harness's own context and transport: the request names `name` and the socket goes to 127.0.0.1."""
    transport = laragon.make_transport(laragon.tls_context(cert_path), name)
    with httpx.Client(transport=transport, trust_env=False, follow_redirects=False) as client:
        return client.get(f"https://{name}:{port}/")


def test_v57_the_harness_certificate_names_only_the_site(harness_made: laragon.SiteCertificate) -> None:
    cert = x509.load_pem_x509_certificate(harness_made.cert_pem)
    assert cert.subject == cert.issuer
    constraints = cert.extensions.get_extension_for_class(x509.BasicConstraints)
    assert constraints.value.ca is False and constraints.critical
    usage = cert.extensions.get_extension_for_class(x509.KeyUsage).value
    assert usage.digital_signature and usage.key_encipherment and not usage.key_cert_sign
    assert cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value == x509.ExtendedKeyUsage(
        [ExtendedKeyUsageOID.SERVER_AUTH]
    )
    names = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert list(names) == [x509.DNSName(SITE_NAME)]  # no wildcard, no IP address, nothing else
    assert harness_made.not_after == cert.not_valid_after_utc
    assert harness_made.fingerprint == cert.fingerprint(hashes.SHA256()).hex(":").upper()


def test_v57_the_harness_certificate_is_accepted_for_the_site(
    harness_made: laragon.SiteCertificate, tmp_path: Path
) -> None:
    trusted = tmp_path / "site.crt"
    trusted.write_bytes(harness_made.cert_pem)
    with tls_server((harness_made.cert_pem, harness_made.key_pem), tmp_path / "server") as server:
        response = harness_fetch(trusted, server.port)
        assert server.record.sni_names == [SITE_NAME]
        assert server.record.hosts == [f"{SITE_NAME}:{server.port}"]
    assert response.status_code == 200


@pytest.mark.parametrize("name", ["other.test", f"deep.{SITE_NAME}"])
def test_v57_the_harness_certificate_is_refused_for_another_name(
    harness_made: laragon.SiteCertificate, tmp_path: Path, name: str
) -> None:
    trusted = tmp_path / "site.crt"
    trusted.write_bytes(harness_made.cert_pem)
    with (
        tls_server((harness_made.cert_pem, harness_made.key_pem), tmp_path / "server") as server,
        pytest.raises(httpx.ConnectError) as raised,
    ):
        harness_fetch(trusted, server.port, name)
    error = verification_error(raised.value)
    assert error is not None and error.verify_code == HOSTNAME_MISMATCH


def test_v57_another_harness_certificate_for_the_site_is_refused(
    harness_made: laragon.SiteCertificate, tmp_path: Path
) -> None:
    """A second `cert --force` makes a new key: the old file no longer trusts the site (check needs the new one)."""
    trusted = tmp_path / "site.crt"
    trusted.write_bytes(harness_made.cert_pem)
    newer = laragon.make_site_certificate(SITE_NAME)
    with tls_server((newer.cert_pem, newer.key_pem), tmp_path / "server") as server:
        with pytest.raises(httpx.ConnectError) as raised:
            harness_fetch(trusted, server.port)
        assert server.record.requests == []
    error = verification_error(raised.value)
    assert error is not None and error.verify_code == SELF_SIGNED_LEAF
