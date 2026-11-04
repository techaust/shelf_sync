"""TLS helpers for the Laragon half of the test stack (m2.8, 04-A V57): look-alike certificates made with
`cryptography`, a small HTTPS server on 127.0.0.1, and an httpx transport that sends a request for a `.test` name to
that server while TLS still checks the `.test` name.

How the name and the socket are kept apart: `LoopbackTransport` rewrites only where the socket goes (the URL's host and
port become 127.0.0.1 and the server's port) and sets httpcore's documented `sni_hostname` request extension to the
original name. httpcore 1.0.9 (`_sync/connection.py`, `_connect`) passes `sni_hostname` as `server_hostname` to
`start_tls`, so the SNI sent *and* the hostname check are on the `.test` name; httpx 0.28.1 passes a request's
`extensions` to httpcore unchanged (`_transports/default.py`), and the `Host` header was fixed from the original URL
when the request was built. No name is ever looked up (the conftest guard would refuse one), and nothing in the TLS
context is changed: the context under test is used as it is.
"""

import datetime
import ipaddress
import ssl
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

# The names of Laragon 8.8.0's own certificate (read 2026-11-05 from C:\laragon\etc\ssl\laragon.crt, public fields
# only): DNS localhost, *.localhost, *.test and IP 127.0.0.1 (it also names one LAN address, left out here).
LARAGON_DNS_NAMES = ("localhost", "*.localhost", "*.test")
LARAGON_IP_ADDRESSES = ("127.0.0.1",)
SITE_NAME = "shelfsync-test.test"


@dataclass(frozen=True)
class TestCertificate:
    """A self-signed certificate and its key, both PEM."""

    __test__ = False  # not a pytest test class

    cert_pem: bytes
    key_pem: bytes

    def write(self, folder: Path, stem: str) -> tuple[Path, Path]:
        folder.mkdir(parents=True, exist_ok=True)
        cert_path, key_path = folder / f"{stem}.crt", folder / f"{stem}.key"
        cert_path.write_bytes(self.cert_pem)
        key_path.write_bytes(self.key_pem)
        return cert_path, key_path


def make_certificate(
    dns_names: Sequence[str] = LARAGON_DNS_NAMES,
    ip_addresses: Sequence[str] = LARAGON_IP_ADDRESSES,
    common_name: str = "laragon",
) -> TestCertificate:
    """A self-signed certificate shaped like Laragon's: RSA 2048, SHA-256, subject = issuer, basicConstraints
    `CA:FALSE`, keyUsage digitalSignature + keyEncipherment, extendedKeyUsage serverAuth, the given SANs, a subject key
    identifier and no authority key identifier (Laragon's has none), none of them critical; valid from yesterday for a
    year."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.datetime.now(datetime.UTC)
    sans: list[x509.GeneralName] = [x509.DNSName(n) for n in dns_names]
    sans += [x509.IPAddress(ipaddress.ip_address(ip)) for ip in ip_addresses]
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=False)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=False,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectAlternativeName(sans), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    return TestCertificate(
        certificate.public_bytes(serialization.Encoding.PEM),
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()),
    )


@dataclass
class ServerRecord:
    """What the HTTPS server saw: the SNI names offered, the Host headers of the requests, and handshake failures."""

    sni_names: list[str | None] = field(default_factory=list)
    hosts: list[str | None] = field(default_factory=list)
    handshake_errors: list[str] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)


class _Handler(BaseHTTPRequestHandler):
    server: _TlsServer

    def do_GET(self) -> None:
        with self.server.record.lock:
            self.server.record.hosts.append(self.headers.get("Host"))
        body = b'{"ok": true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:  # quiet: pytest shows stderr on a failure only
        pass


class _TlsServer(ThreadingHTTPServer):
    """An HTTP server on 127.0.0.1 whose connections are wrapped in TLS in each request's own thread, so a failed
    handshake is recorded and never stops the accept loop."""

    daemon_threads = True

    def __init__(self, context: ssl.SSLContext, record: ServerRecord) -> None:
        self.tls = context
        self.record = record
        super().__init__(("127.0.0.1", 0), _Handler)

    def finish_request(self, request: Any, client_address: Any) -> None:
        try:
            wrapped = self.tls.wrap_socket(request, server_side=True)
        except (ssl.SSLError, OSError) as error:
            with self.record.lock:
                self.record.handshake_errors.append(str(error))
            return
        super().finish_request(wrapped, client_address)


@dataclass
class RunningServer:
    port: int
    record: ServerRecord


@contextmanager
def tls_server(certificate: TestCertificate, folder: Path) -> Iterator[RunningServer]:
    """Serve `GET` (200, a small JSON body) over TLS with `certificate` on 127.0.0.1, any free port."""
    cert_path, key_path = certificate.write(folder, "server")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_path, key_path)
    record = ServerRecord()

    def remember_sni(_: Any, name: str | None, __: Any) -> None:
        with record.lock:
            record.sni_names.append(name)

    context.sni_callback = remember_sni
    server = _TlsServer(context, record)
    thread = threading.Thread(target=server.serve_forever, name="tls-test-server", daemon=True)
    thread.start()
    try:
        yield RunningServer(int(server.server_address[1]), record)
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


class LoopbackTransport(httpx.BaseTransport):
    """Sends every request to 127.0.0.1:`port`, with SNI and the hostname check still on the request's own host
    (httpcore's `sni_hostname` extension). Records the URLs and headers as the caller built them."""

    def __init__(self, inner: httpx.BaseTransport, port: int) -> None:
        self._inner = inner
        self._port = port
        self.requests: list[tuple[str, str, httpx.Headers]] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append((request.method, str(request.url), httpx.Headers(request.headers)))
        name = request.url.host
        request.url = request.url.copy_with(host="127.0.0.1", port=self._port)
        request.extensions = {**request.extensions, "sni_hostname": name}
        return self._inner.handle_request(request)

    def close(self) -> None:
        self._inner.close()


def verification_error(error: BaseException) -> ssl.SSLCertVerificationError | None:
    """The certificate verification error behind an httpx error, if there is one."""
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        if isinstance(current, ssl.SSLCertVerificationError):
            return current
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return None
