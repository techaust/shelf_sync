"""The Laragon half of ShelfSync's test stack (m2.8; 04 section 10, 07 section 5, 04-A V57, runbook test-stack.md §3).

    UV_PYTHON_DOWNLOADS=never uv run python -m testenv.laragon <command> [options]

Commands:
- `cert`: makes the site's own certificate (self-signed, `CA:FALSE`, naming exactly the site, serverAuth) and its key,
  and the Apache site file that serves them for the site. Laragon's own certificate can't be used: its `*.test`
  wildcard never matches a name like `shelfsync-test.test` (V57), and Laragon rewrites that certificate itself.
- `keys`: saves one site's two WooCommerce REST key pairs (Read, and Read/Write) in Credential Manager under the
  service `ShelfSync-TestStack` (never ShelfSync's own), in entries named after the site; `keys --remove` deletes
  exactly that site's four entries.
- `check`: the store half of the M2 exit test: ShelfSync's own `WooClient` and `run_read_test` (Settings' Test
  connection) against the site with the read-only pair, worded as Settings words it (13).
- `seed`: writes the sample products (`testenv/samples.py`) with the read/write pair, and uploads their files to the
  moto S3 server; `seed --reset` deletes only the samples (`testenv/seed.py`).

Guards:
- **The site** must be `https` on a name ending in `.test` (RFC 6761: never a public name), no IP address, user, path
  or query, so a live store's address is refused before anything else runs.
- **Every connection goes to 127.0.0.1** (`LoopbackOnlyTransport`), whatever the name resolves to, so a key can never
  leave this PC; TLS still sends SNI for and checks the site's own name. So `check` doesn't test the name lookup
  (Laragon's hosts-file entry): a browser does. One transport serves one site only, and each command makes its own.
- **TLS trusts one file only**, the site's certificate, with Python's defaults otherwise (`VERIFY_X509_STRICT`, the
  hostname check, `CERT_REQUIRED`), which the harness checks and never changes.
- **Keys** are typed hidden (`getpass`; a console that can't hide them is refused), checked as Settings (Stores)
  checks them, and never printed, logged, written to a file or put in a URL (HTTP Basic in the header, `trust_env`
  off, no redirects followed: ShelfSync's `WooClient`).

Developer tooling for the test stack: never shipped with the app.
"""

import argparse
import contextlib
import datetime
import getpass
import os
import re
import ssl
import subprocess
import sys
import warnings
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from shelfsync.apply.woocommerce import ReadOutcome, WooClient, run_read_test
from shelfsync.platform.secrets import KeyringSecretStore, SecretStore, SecretStoreError
from shelfsync.secure.credentials import is_valid_pair

DEFAULT_SITE = "https://shelfsync-test.test"
DEFAULT_LARAGON = Path(r"C:\laragon")
# Outside Laragon's folder (Laragon rewrites its own certificate files, 2026-11-05) and outside %LOCALAPPDATA% and
# %APPDATA% (a process started from the Claude app writes those into a private copy Laragon's Apache can't see, 04-A
# V36). Not in the repository. A short path without spaces, as Apache's configuration prefers.
DEFAULT_CERT_DIR = Path(r"C:\ShelfSync-TestStack\tls")
SERVICE = "ShelfSync-TestStack"  # Credential Manager service: never ShelfSync's own ("ShelfSync"), see secrets.py
STORE_CODE = "TS"  # the only name `run_read_test`'s log line carries
SPACING_MS = 150  # Settings' default spacing between two requests to a store
CERT_DAYS = 365
LOOPBACK = "127.0.0.1"

_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_TEST_HOST = re.compile(rf"(?:{_LABEL}\.)+test")
_SID = re.compile(rb"S-1-[0-9]+(?:-[0-9]+)+")


class HarnessError(Exception):
    """Something the owner can fix; the message says what. It never holds a key."""


# ---------- the site ----------


@dataclass(frozen=True)
class Site:
    url: str  # https://<host>[:<port>], no trailing slash
    host: str
    port: int

    @property
    def project(self) -> str:
        """Laragon's project (folder) name: the host without `.test`."""
        return self.host.removesuffix(".test")


def parse_site(value: str) -> Site:
    """The site address, or ValueError. Only `https://<name>.test[:<port>]` passes."""
    try:
        url = httpx.URL(value)
    except httpx.InvalidURL:
        raise ValueError("not an address") from None
    host = url.host
    if (
        url.scheme != "https"
        or url.userinfo
        or url.query
        or url.fragment
        or url.path not in ("", "/")
        or len(host) > 253
        or _TEST_HOST.fullmatch(host) is None
    ):
        raise ValueError("not https on a .test name")
    # httpx gives no port for the default one; it lets 0 and numbers past 65535 through, so they are refused here.
    # An IDNA name (`xn--…`) comes back decoded (`bücher.test`), which the ASCII pattern above refuses.
    port = 443 if url.port is None else url.port
    if not 0 < port <= 65535:
        raise ValueError("not a port")
    return Site(f"https://{host}" + ("" if port == 443 else f":{port}"), host, port)


def _site_argument(value: str) -> Site:
    try:
        return parse_site(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"{value!r} isn't allowed: use https:// on a name ending in .test, for example {DEFAULT_SITE}. "
            "The test stack never talks to a real store."
        ) from None


# ---------- TLS ----------


def tls_context(cert: Path) -> ssl.SSLContext:
    """Python's default client context trusting `cert` and nothing else. The defaults are checked, never changed."""
    if not cert.is_file():
        raise HarnessError(f"The certificate file {cert} isn't there. Run the cert command first, or give --cert.")
    try:
        context = ssl.create_default_context(cafile=str(cert))
    except ssl.SSLError, OSError:
        raise HarnessError(f"{cert} isn't a certificate file Python can read.") from None
    if context.cert_store_stats()["x509"] != 1:
        raise HarnessError(f"{cert} must hold exactly one certificate.")
    strict = bool(context.verify_flags & ssl.VERIFY_X509_STRICT)
    if not (strict and context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED):
        raise HarnessError("This Python's default TLS checks aren't on, so the harness won't connect.")
    return context


class LoopbackOnlyTransport(httpx.BaseTransport):
    """Sends every request to 127.0.0.1, on its URL's port, whatever its name resolves to. SNI and the hostname check
    stay on the URL's own name: httpcore's documented `sni_hostname` request extension, which httpx 0.28.1 passes
    through unchanged and httpcore 1.0.9 uses as `server_hostname` (04-A V57). The `Host` header was set from the URL
    when the request was built, so Apache picks the site by it.

    It serves **one site only** (`host`): httpcore pools connections by where the socket goes (127.0.0.1 and the
    port) and sets SNI only when it opens one, so a transport shared by two sites on the same port could send the
    second site's request over a connection made for the first. A request for any other host is refused."""

    def __init__(self, inner: httpx.BaseTransport, host: str) -> None:
        self._inner = inner
        self._host = host

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        name = request.url.host
        if name != self._host:
            raise HarnessError(f"This connection is for {self._host} only; {name} needs its own.")
        request.url = request.url.copy_with(host=LOOPBACK)
        request.extensions = {**request.extensions, "sni_hostname": name}
        return self._inner.handle_request(request)

    def close(self) -> None:
        self._inner.close()


def make_transport(context: ssl.SSLContext, host: str) -> httpx.BaseTransport:
    """A new transport for one site: called once per client, never shared."""
    return LoopbackOnlyTransport(httpx.HTTPTransport(verify=context, trust_env=False), host)


# ---------- cert ----------


@dataclass(frozen=True)
class SiteCertificate:
    cert_pem: bytes
    key_pem: bytes = field(repr=False)  # never in a repr, a traceback's locals or a log line
    fingerprint: str  # SHA-256, colon-separated hex
    not_after: datetime.datetime


def make_site_certificate(host: str, now: datetime.datetime | None = None) -> SiteCertificate:
    """A self-signed certificate naming exactly `host`: RSA 2048, SHA-256, basicConstraints `CA:FALSE`, keyUsage
    digitalSignature + keyEncipherment, extendedKeyUsage serverAuth, a subject key identifier, valid from an hour ago
    for `CERT_DAYS`. The shape V57's tests accept under Python's strict defaults."""
    start = (now or datetime.datetime.now(datetime.UTC)) - datetime.timedelta(hours=1)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, host)])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(start)
        .not_valid_after(start + datetime.timedelta(days=CERT_DAYS))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
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
            critical=True,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(host)]), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    return SiteCertificate(
        certificate.public_bytes(serialization.Encoding.PEM),
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()),
        certificate.fingerprint(hashes.SHA256()).hex(":").upper(),
        certificate.not_valid_after_utc,
    )


@dataclass(frozen=True)
class CertFiles:
    cert: Path
    key: Path
    vhost: Path

    def all(self) -> tuple[Path, Path, Path]:
        return self.cert, self.key, self.vhost


def cert_files(site: Site, cert_dir: Path, laragon: Path) -> CertFiles:
    """Where `cert` writes. The Apache file's name starts `00-`, so Apache reads it before Laragon's own
    `auto.<site>.conf` (Apache includes `sites-enabled/*.conf` in alphabetical order and the first matching
    `ServerName` wins). Laragon's docs name only the `auto.` files as its own, but Laragon also rewrites some other
    files: at an SSL off-and-on on 2026-11-05 it rewrote its `00-default.conf` too. Whether it ever removes or
    rewrites this one isn't known; runbook §3.2 step 7 checks it, and `cert --force` puts it back."""
    return CertFiles(
        cert_dir / f"{site.host}.crt",
        cert_dir / f"{site.host}.key",
        laragon / "etc" / "apache2" / "sites-enabled" / f"00-{site.host}.conf",
    )


def _apache_path(path: Path) -> str:
    text = path.as_posix()
    if '"' in text or "\n" in text:
        raise HarnessError(f"{path} can't be used in Apache's configuration.")
    return text


def vhost_text(site: Site, files: CertFiles, docroot: Path) -> str:
    root = _apache_path(docroot)
    return (
        "# ShelfSync test stack (python -m testenv.laragon cert): the HTTPS site with its own certificate.\n"
        "# Apache reads this file before Laragon's auto.* file for the same site, so this one answers for it.\n"
        "# Remove this file to go back to Laragon's own settings.\n"
        f"<VirtualHost *:{site.port}>\n"
        f'    DocumentRoot "{root}"\n'
        f"    ServerName {site.host}\n"
        f'    <Directory "{root}">\n'
        "        AllowOverride All\n"
        "        Require all granted\n"
        "    </Directory>\n"
        "    SSLEngine on\n"
        f'    SSLCertificateFile "{_apache_path(files.cert)}"\n'
        f'    SSLCertificateKeyFile "{_apache_path(files.key)}"\n'
        "</VirtualHost>\n"
    )


def _whoami_sid(system32: Path) -> str:
    result = subprocess.run(
        [str(system32 / "whoami.exe"), "/user", "/fo", "csv", "/nh"], check=True, capture_output=True, timeout=30
    )
    match = _SID.search(result.stdout)
    if match is None:
        raise HarnessError("Couldn't read your Windows account's ID (whoami).")
    return match.group(0).decode("ascii")


def restrict_to_current_user(path: Path) -> None:
    """Only the current account may open `path`. Windows: `icacls` removes every inherited entry and grants this
    account (by its SID) full control and nothing else; on a folder, the grant is inherited by everything made in it
    (`(OI)(CI)`), so no other local account can read the key or swap the trusted certificate. Elsewhere: 0600 for a
    file, 0700 for a folder."""
    if sys.platform != "win32":
        path.chmod(0o700 if path.is_dir() else 0o600)
        return
    system32 = Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32"
    rights = "(OI)(CI)(F)" if path.is_dir() else "(F)"
    try:
        sid = _whoami_sid(system32)
        subprocess.run(
            [str(system32 / "icacls.exe"), str(path), "/inheritance:r", "/grant:r", f"*{sid}:{rights}"],
            check=True,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise HarnessError(f"Couldn't limit {path} to your account ({type(error).__name__}).") from None


def _write_private(path: Path, data: bytes, restrict: Callable[[Path], None]) -> None:
    """Create `path` empty (never over an existing file), limit it to this account, then write `data` into it."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
    os.close(descriptor)
    try:
        restrict(path)
        with path.open("r+b") as handle:  # opening the existing file keeps its permissions
            handle.write(data)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


# Only certificate pairs (and their in-progress copies) may sit in the certificate folder: it is limited to this
# account as a whole, which would be wrong for a folder holding anything else.
_OUR_FILE = re.compile(r"[a-z0-9.-]+\.test\.(?:crt|key)(?:\.new)?")


def _temporary(path: Path) -> Path:
    return path.with_name(path.name + ".new")


def write_certificate(
    site: Site,
    cert_dir: Path,
    laragon: Path,
    *,
    force: bool,
    restrict: Callable[[Path], None],
    now: datetime.datetime | None = None,
) -> tuple[CertFiles, SiteCertificate]:
    """Write the key, the certificate and the Apache file. Each is first written under a `.new` name and the three are
    swapped in only once all are written, so a failure never leaves a half-made set; the key is limited to this
    account while still empty. Any file-system failure is a `HarnessError`."""
    sites_enabled = laragon / "etc" / "apache2" / "sites-enabled"
    if not sites_enabled.is_dir():
        raise HarnessError(f"{laragon} doesn't look like Laragon's folder (no {sites_enabled}). Give --laragon.")
    docroot = laragon / "www" / site.project
    if not docroot.is_dir():
        raise HarnessError(f"Laragon has no site folder {docroot}. Make the site in Laragon first (runbook §3.1).")
    if cert_dir.exists():
        if not cert_dir.is_dir():
            raise HarnessError(f"{cert_dir} isn't a folder. Give another with --dir.")
        others = sorted(entry.name for entry in cert_dir.iterdir() if not _OUR_FILE.fullmatch(entry.name))
        if others:
            raise HarnessError(
                f"{cert_dir} holds other files ({', '.join(others[:3])}). Give a new or empty folder with --dir."
            )
    files = cert_files(site, cert_dir, laragon)
    existing = [path for path in files.all() if path.exists()]
    if existing and not force:
        names = ", ".join(str(path) for path in existing)
        raise HarnessError(f"Already there: {names}. Add --force to replace them with a new certificate and key.")
    made = make_site_certificate(site.host, now)
    temporaries = [_temporary(path) for path in files.all()]
    try:
        cert_dir.mkdir(parents=True, exist_ok=True)
        restrict(cert_dir)
        for temporary in temporaries:
            temporary.unlink(missing_ok=True)  # left by an earlier run that stopped half way
        _write_private(_temporary(files.key), made.key_pem, restrict)
        _temporary(files.cert).write_bytes(made.cert_pem)
        _temporary(files.vhost).write_text(vhost_text(site, files, docroot), encoding="utf-8", newline="\n")
        for path in (files.key, files.cert, files.vhost):
            os.replace(_temporary(path), path)
    except OSError as error:
        _remove(temporaries)
        where = f" {error.filename}" if error.filename else ""
        reason = error.strerror or type(error).__name__
        raise HarnessError(f"Couldn't write the certificate files ({reason}){where}.") from None
    except BaseException:
        _remove(temporaries)
        raise
    return files, made


def _remove(paths: Sequence[Path]) -> None:
    for path in paths:
        with contextlib.suppress(OSError):  # best effort; the caller reports the first failure
            path.unlink(missing_ok=True)


# ---------- keys ----------


@dataclass(frozen=True)
class PairSpec:
    name: str  # "read-only" or "read/write", as the output says it
    key_entry: str
    secret_entry: str


def pairs_for(site: Site) -> tuple[PairSpec, PairSpec]:
    """The site's (read-only, read/write) Credential Manager entries, named after the site, so two test sites never
    share keys. The `woo-` prefix keeps them apart from ShelfSync's own names (`store-<id>-key` and the fixed ones),
    though they also sit under another service."""
    base = f"woo-{site.host}"
    return (
        PairSpec("read-only", f"{base}-ro-key", f"{base}-ro-secret"),
        PairSpec("read/write", f"{base}-rw-key", f"{base}-rw-secret"),
    )


def hidden_prompt(text: str) -> str:
    """`getpass`, but a console that can't hide the typing is refused instead of echoing it."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        try:
            return getpass.getpass(text)
        except getpass.GetPassWarning:
            raise HarnessError(
                "keys needs a console window that can hide what you type. Run it in Windows PowerShell."
            ) from None


def read_pair(secrets: SecretStore, pair: PairSpec) -> tuple[str, str] | None:
    key, secret = secrets.get(pair.key_entry), secrets.get(pair.secret_entry)
    return None if key is None or secret is None else (key, secret)


def _put_back(secrets: SecretStore, name: str, value: str | None) -> None:
    try:
        if value is None:
            secrets.delete(name)
        else:
            secrets.set(name, value)
    except SecretStoreError:
        pass  # best effort; the caller reports the first failure


def _store_pair(secrets: SecretStore, pair: PairSpec, key: str, secret: str) -> None:
    """Both entries or neither: if the second write fails, the first is put back."""
    old_key, old_secret = secrets.get(pair.key_entry), secrets.get(pair.secret_entry)
    try:
        secrets.set(pair.key_entry, key)
        secrets.set(pair.secret_entry, secret)
    except SecretStoreError:
        _put_back(secrets, pair.key_entry, old_key)
        _put_back(secrets, pair.secret_entry, old_secret)
        raise


def save_keys(secrets: SecretStore, prompt: Callable[[str], str], site: Site) -> int:
    failed = False
    saved: dict[str, tuple[str, str]] = {}
    for pair in pairs_for(site):
        label = pair.name[0].upper() + pair.name[1:]
        key = prompt(f"{label} consumer key for {site.host} (starts ck_; nothing is shown as you type): ").strip()
        if not key:
            say(f"{label} key pair skipped (nothing typed); any one saved before is kept.")
            continue
        secret = prompt(f"{label} consumer secret for {site.host} (starts cs_; nothing is shown as you type): ").strip()
        if not is_valid_pair(key, secret):
            say(
                f"{label} key pair not saved: a consumer key starts with ck_ and a secret with cs_, "
                "each followed by 20 to 64 letters and digits."
            )
            failed = True
            continue
        if any(key == other_key or secret == other_secret for other_key, other_secret in saved.values()):
            say(f"{label} key pair not saved: it's the same as the other pair. Make one Read and one Read/Write key.")
            failed = True
            continue
        try:
            _store_pair(secrets, pair, key, secret)
        except SecretStoreError as error:
            say(f"{label} key pair not saved: {error}.")
            failed = True
            continue
        saved[pair.name] = (key, secret)
        say(f"Saved {pair.name} key pair for {site.host}.")
    return 1 if failed else 0


def remove_keys(secrets: SecretStore, site: Site) -> int:
    for pair in pairs_for(site):
        secrets.delete(pair.key_entry)
        secrets.delete(pair.secret_entry)
    say(f"Removed the two key pairs of {site.host} from Credential Manager (service {SERVICE}).")
    return 0


# ---------- check ----------

# The words of the Test connection in Settings (Stores) (13; frontend/src/lib/storesWording.ts).
_REASON_TEXT = {
    "unreachable": "Couldn't reach the store. Check the address and your internet connection.",
    "timeout": "The store took too long to answer.",
    "tls_error": "The store's security certificate wasn't accepted.",
    "blocked": "Something in front of the store (a firewall or a security check) blocked the request.",
    "not_woocommerce": "That address answers, but it isn't a WooCommerce store's REST API.",
    "rate_limited": "The store is limiting requests (HTTP 429). Try again in a few minutes.",
    "bad_response": "The store's answer wasn't what ShelfSync expected.",
    "keys_refused": "HTTP 401: the Shop Manager key was refused.",
    "forbidden": "HTTP 403: the key is valid but isn't allowed to read this. It needs the Shop Manager role.",
}
_NAMES_ITS_STATUS = frozenset({"rate_limited", "cloudflare_52x", "server_error", "keys_refused", "forbidden"})


def _products(count: int) -> str:
    return f"{count:,} downloadable {'product' if count == 1 else 'products'}"


def describe(outcome: ReadOutcome) -> str:
    if outcome.ok:
        if outcome.warning == "no_downloadable_products":
            return "Connected, but the store has no downloadable products yet."
        return f"Connected in {outcome.latency_ms:,} ms. WooCommerce {outcome.wc_version}, " + (
            f"{_products(outcome.downloadable_count or 0)}."
        )
    reason, status = outcome.reason or "", outcome.http_status
    if reason == "redirected":
        where = f" ({outcome.detail})" if outcome.detail else ""
        return f"The store sent the request to another address{where}. Update the store's address."
    if reason == "wc_too_old":
        return f"WooCommerce {outcome.wc_version} is too old. ShelfSync needs 5.8 or newer."
    if reason == "cloudflare_52x":
        text = "Cloudflare couldn't reach the store's server" + (f" (HTTP {status})." if status else ".")
    elif reason == "server_error":
        text = "The store had an error" + (f" (HTTP {status})." if status else ".")
    else:
        text = _REASON_TEXT.get(reason, "The test failed.")
    if status and reason not in _NAMES_ITS_STATUS:
        text += f" (HTTP {status})"
    return text


TransportFactory = Callable[[ssl.SSLContext, str], httpx.BaseTransport]


def run_check(
    site: Site, cert: Path, secrets: SecretStore, transport_factory: TransportFactory = make_transport
) -> int:
    pair = read_pair(secrets, pairs_for(site)[0])
    if pair is None:
        say(f"No read-only key pair is saved for {site.host}. Run the keys command first.")
        return 1
    context = tls_context(cert)
    with WooClient(site.url, pair[0], pair[1], transport=transport_factory(context, site.host)) as client:
        outcome = run_read_test(client, SPACING_MS, STORE_CODE)
    say(f"{site.url}: {describe(outcome)}")
    return 0 if outcome.ok else 1


# ---------- the command ----------

# The moto server's defaults (testenv/moto_s3.py; a test keeps them equal; not imported, so `check` and `keys` don't
# load moto).
DEFAULT_MOTO = "http://127.0.0.1:47630"
DEFAULT_BUCKET = "shelfsync-test-stack"
DEFAULT_REGION = "us-east-1"


def parse_moto(value: str) -> str:
    """The moto endpoint, or ValueError: `http` on 127.0.0.1 or localhost with a port, nothing else, so `seed` can
    never write to the real bucket."""
    try:
        url = httpx.URL(value)
    except httpx.InvalidURL:
        raise ValueError("not an address") from None
    if (
        url.scheme != "http"
        or url.host not in (LOOPBACK, "localhost")
        or url.port is None
        or not 0 < url.port <= 65535
        or url.userinfo
        or url.query
        or url.fragment
        or url.path not in ("", "/")
    ):
        raise ValueError("not the local moto server")
    return f"http://{url.host}:{url.port}"


def _moto_argument(value: str) -> str:
    try:
        return parse_moto(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"{value!r} isn't allowed: use the local S3 server, http://127.0.0.1:<port> (default {DEFAULT_MOTO})."
        ) from None


def say(text: str, stream: Any = None) -> None:
    out = stream if stream is not None else sys.stdout
    out.write(text + "\n")
    out.flush()


def default_cert(site: Site) -> Path:
    return DEFAULT_CERT_DIR / f"{site.host}.crt"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m testenv.laragon",
        description="The Laragon site of ShelfSync's test stack: its certificate, keys, check and sample products.",
    )
    site = argparse.ArgumentParser(add_help=False)
    site.add_argument(
        "--site",
        type=_site_argument,
        default=parse_site(DEFAULT_SITE),
        help=f"the site's address, https on a .test name (default {DEFAULT_SITE})",
    )
    trust = argparse.ArgumentParser(add_help=False)
    trust.add_argument(
        "--cert", type=Path, default=None, help=f"the certificate to trust (default in {DEFAULT_CERT_DIR})"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    cert = commands.add_parser("cert", parents=[site], help="make the site's certificate and its Apache site file")
    cert.add_argument("--dir", type=Path, default=DEFAULT_CERT_DIR, help=f"where (default {DEFAULT_CERT_DIR})")
    cert.add_argument("--laragon", type=Path, default=DEFAULT_LARAGON, help=f"Laragon's folder ({DEFAULT_LARAGON})")
    cert.add_argument("--force", action="store_true", help="replace a certificate made before")
    keys = commands.add_parser("keys", parents=[site], help="save (or --remove) the site's two WooCommerce key pairs")
    keys.add_argument("--remove", action="store_true", help="delete this site's saved pairs")
    commands.add_parser("check", parents=[site, trust], help="test the connection, as Settings does")
    seed = commands.add_parser("seed", parents=[site, trust], help="write (or --reset) the sample products")
    seed.add_argument("--moto", type=_moto_argument, default=DEFAULT_MOTO, help=f"the S3 server ({DEFAULT_MOTO})")
    seed.add_argument("--bucket", default=DEFAULT_BUCKET, help=f"its bucket (default {DEFAULT_BUCKET})")
    seed.add_argument("--reset", action="store_true", help="delete the sample products, and nothing else")
    return parser.parse_args(argv)


def main(
    argv: Sequence[str] | None = None,
    *,
    secrets_factory: Callable[[], SecretStore] = lambda: KeyringSecretStore(SERVICE),
    prompt: Callable[[str], str] = hidden_prompt,
    transport_factory: TransportFactory = make_transport,
    restrict: Callable[[Path], None] = restrict_to_current_user,
) -> int:
    args = parse_args(argv)
    try:
        if args.command == "cert":
            files, made = write_certificate(args.site, args.dir, args.laragon, force=args.force, restrict=restrict)
            say(f"Made a certificate for {args.site.host}, valid until {made.not_after:%Y-%m-%d} (UTC).")
            say(f"  SHA-256 fingerprint  {made.fingerprint}")
            say(f"  Certificate          {files.cert}")
            say(f"  Private key          {files.key} (only your account can open it)")
            say(f"  Apache site file     {files.vhost}")
            say(f'Next: reload Apache with Laragon\'s own command, "{args.laragon / "laragon.exe"}" reload apache')
            say("(or in Laragon: Stop, then Start All), then run the check command.")
            return 0
        secrets = secrets_factory()
        if args.command == "keys":
            return remove_keys(secrets, args.site) if args.remove else save_keys(secrets, prompt, args.site)
        cert = args.cert if args.cert is not None else default_cert(args.site)
        if args.command == "check":
            return run_check(args.site, cert, secrets, transport_factory)
        from testenv import seed  # here, not at the top: seed imports this module

        if args.reset:
            return seed.run_reset(args.site, cert, secrets, transport_factory)
        return seed.run_seed(args.site, cert, secrets, args.moto, args.bucket, DEFAULT_REGION, transport_factory)
    except HarnessError as error:
        say(str(error), sys.stderr)
        return 1
    except SecretStoreError as error:
        say(f"{error}. Nothing more was done.", sys.stderr)
        return 1
    except KeyboardInterrupt:
        say("Stopped. Nothing more was done.", sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
