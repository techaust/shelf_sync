"""The `.ssbak` export file: sealing and opening, with no I/O (SET-05, 06 section 7, 04-A V21).

A file is UTF-8 JSON, format version 1:

    {"format": "shelfsync-export", "version": 1, "created_at": <UTC ISO>, "app_version": <text>, "schema": <int>,
     "encryption": null | {"cipher": "AES-256-GCM", "kdf": "scrypt", "n": 131072, "r": 8, "p": 1,
                           "salt": <base64, 16 bytes>, "nonce": <base64, 12 bytes>},
     ... then "payload" and "sha256" (no encryption) or "ciphertext" (encryption)}

- **Key:** the standard library's `hashlib.scrypt` (N = 2**17, r = 8, p = 1, `maxmem` 256 MiB, 32 bytes) over the
  passphrase in NFC and UTF-8, with a fresh 16-byte random salt per file. Not cryptography's Scrypt (04-A V21).
- **Cipher:** AES-256-GCM (`cryptography`'s `AESGCM`), a fresh 12-byte random nonce per file. `encrypt` returns the
  ciphertext with the 16-byte tag appended and `decrypt` takes it the same way (Context7, pyca/cryptography,
  2026-10-28).
- **AAD:** the canonical JSON (`sort_keys`, `separators=(",", ":")`, `ensure_ascii`) of every header field except
  `ciphertext`, so a changed date, version text, schema, salt, nonce or parameter fails the tag.
- **Costs are never taken from the file.** A file is opened only when its `n`, `r` and `p` equal this module's
  constants, and that is checked **before any derivation**: a file that asks for a bigger cost is refused outright.
- A file without a passphrase holds `payload` (the JSON object) and `sha256` of its canonical form: a corruption
  check only, not proof of who wrote it.
- Duplicate keys, `NaN` and `Infinity`, unknown fields and a wrong shape anywhere in the header are refused.

Nothing here logs, and no message holds the passphrase, a key or a payload value.
"""

import base64
import binascii
import hashlib
import json
import os
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, TypeIs

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

FORMAT = "shelfsync-export"
VERSION = 1
CIPHER = "AES-256-GCM"
KDF_NAME = "scrypt"
# The only costs version 1 accepts. They are module constants (not parameters, not read from a file); the tests lower
# `SCRYPT_N` for speed, which moves the writer and the reader together, and no production code does.
SCRYPT_N = 2**17
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_MAXMEM = 256 * 1024 * 1024  # about 128 MiB are used; the default limit (32 MiB) would refuse (V21)
KEY_BYTES = 32
SALT_BYTES = 16
NONCE_BYTES = 12
TAG_BYTES = 16
PASSPHRASE_MIN = 12
PASSPHRASE_MAX = 1024
MAX_FILE_CHARS = 32 * 1024 * 1024  # the longest file text an import reads

_CREATED_AT = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_HEADER_FIELDS = frozenset({"format", "version", "created_at", "app_version", "schema", "encryption"})
_ENCRYPTION_FIELDS = frozenset({"cipher", "kdf", "n", "r", "p", "salt", "nonce"})
_APP_VERSION_MAX = 64


class ExportError(Exception):
    """Base of the refusals below. The message never holds a value from the file or the passphrase."""


class ExportInvalid(ExportError):
    """Not a ShelfSync export file, or one that was changed or damaged."""


class ExportTooNew(ExportError):
    """A newer format version or database schema than this ShelfSync knows."""


class PassphraseRequired(ExportError):
    """The file is encrypted and no passphrase was given."""


class WrongPassphrase(ExportError):
    """The tag didn't verify: a wrong passphrase, or a file changed since it was written (the two can't be told
    apart, by design)."""


class PassphraseInvalid(ValueError):
    """A passphrase outside 12 to 1024 characters (counted after NFC)."""


def passphrase_bytes(passphrase: str) -> bytes:
    """The passphrase in NFC and UTF-8. `PassphraseInvalid` when it isn't 12 to 1024 characters long after NFC."""
    text = unicodedata.normalize("NFC", passphrase)
    if not PASSPHRASE_MIN <= len(text) <= PASSPHRASE_MAX:
        raise PassphraseInvalid("A passphrase has 12 to 1024 characters.")
    try:
        return text.encode("utf-8")
    except UnicodeEncodeError:  # a lone surrogate
        raise PassphraseInvalid("A passphrase must be valid text.") from None


def check_passphrase(passphrase: str) -> str:
    """The passphrase as given, if it is acceptable (for a request model); `PassphraseInvalid` otherwise."""
    passphrase_bytes(passphrase)
    return passphrase


def derive_key(passphrase: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        passphrase_bytes(passphrase),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        maxmem=SCRYPT_MAXMEM,
        dklen=KEY_BYTES,
    )


def canonical(value: Any) -> bytes:
    """The one byte form of a JSON value that the checksum and the AAD are taken over."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    found: dict[str, Any] = {}
    for key, value in pairs:
        if key in found:
            raise ValueError("a repeated key")
        found[key] = value
    return found


def _no_constants(name: str) -> Any:
    raise ValueError("not a JSON value")  # NaN, Infinity


def strict_loads(text: str | bytes) -> Any:
    """`json.loads` that refuses repeated keys (at any depth) and `NaN`/`Infinity`. ValueError or RecursionError."""
    return json.loads(text, object_pairs_hook=_no_duplicates, parse_constant=_no_constants)


def parse_envelope(text: str) -> dict[str, Any]:
    """The file text as a JSON object. `ExportInvalid` for anything else, a repeated key included."""
    if not isinstance(text, str) or not text or len(text) > MAX_FILE_CHARS:
        raise ExportInvalid("The file is empty or too long.")
    try:
        value = strict_loads(text)
    except ValueError, RecursionError:
        raise ExportInvalid("The file isn't valid JSON.") from None
    if not isinstance(value, dict):
        raise ExportInvalid("The file isn't a JSON object.")
    return value


def dumps(envelope: Mapping[str, Any]) -> str:
    """The file text: compact, keys in order, ASCII only (so the file is the same in any encoding)."""
    return json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _unb64(text: object) -> bytes:
    """Standard base64 in its one canonical form (padding included), or `ExportInvalid`."""
    if not isinstance(text, str) or not text.isascii():
        raise ExportInvalid("A field isn't base64.")
    try:
        raw = base64.b64decode(text, validate=True)
    except binascii.Error, ValueError:
        raise ExportInvalid("A field isn't base64.") from None
    if _b64(raw) != text:
        raise ExportInvalid("A field isn't base64.")
    return raw


@dataclass(frozen=True)
class _Checked:
    schema: int
    encrypted: bool
    salt: bytes = b""
    nonce: bytes = b""
    ciphertext: bytes = b""
    payload: Mapping[str, Any] | None = None
    sha256: str = ""


def _is_int(value: object) -> TypeIs[int]:
    return type(value) is int  # not a bool


def _check(envelope: object) -> _Checked:
    """Every rule about the shape of the file and of its header; no derivation, no decryption."""
    if not isinstance(envelope, dict) or envelope.get("format") != FORMAT:
        raise ExportInvalid("Not a ShelfSync export file.")
    version = envelope.get("version")
    if not _is_int(version):
        raise ExportInvalid("Not a ShelfSync export file.")
    if version > VERSION:
        raise ExportTooNew("A newer export format.")
    if version != VERSION:
        raise ExportInvalid("Not a ShelfSync export file.")
    if "encryption" not in envelope:
        raise ExportInvalid("The header is incomplete.")
    encryption = envelope["encryption"]
    encrypted = encryption is not None
    if set(envelope) != _HEADER_FIELDS | ({"ciphertext"} if encrypted else {"payload", "sha256"}):
        raise ExportInvalid("The file has missing or unknown fields.")
    created_at = envelope["created_at"]
    app_version = envelope["app_version"]
    schema = envelope["schema"]
    if (
        not isinstance(created_at, str)
        or _CREATED_AT.fullmatch(created_at) is None
        or not isinstance(app_version, str)
        or not 1 <= len(app_version) <= _APP_VERSION_MAX
        or not app_version.isprintable()
        or not _is_int(schema)
        or not 1 <= schema <= 1_000_000
    ):
        raise ExportInvalid("The header is wrong.")
    if not encrypted:
        payload = envelope["payload"]
        digest = envelope["sha256"]
        if not isinstance(payload, dict) or not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
            raise ExportInvalid("The payload is wrong.")
        return _Checked(schema, False, payload=payload, sha256=digest)
    if not isinstance(encryption, dict) or set(encryption) != _ENCRYPTION_FIELDS:
        raise ExportInvalid("The encryption header is wrong.")
    # The costs are compared with this module's constants, and a file asking for more (or less) is refused here, before
    # a salt is read and long before scrypt could run.
    if (
        encryption["cipher"] != CIPHER
        or encryption["kdf"] != KDF_NAME
        or not _is_int(encryption["n"])
        or not _is_int(encryption["r"])
        or not _is_int(encryption["p"])
        or (encryption["n"], encryption["r"], encryption["p"]) != (SCRYPT_N, SCRYPT_R, SCRYPT_P)
    ):
        raise ExportInvalid("The encryption settings aren't the ones this version accepts.")
    salt = _unb64(encryption["salt"])
    nonce = _unb64(encryption["nonce"])
    ciphertext = _unb64(envelope["ciphertext"])
    if len(salt) != SALT_BYTES or len(nonce) != NONCE_BYTES or len(ciphertext) < TAG_BYTES:
        raise ExportInvalid("The encryption header is wrong.")
    return _Checked(schema, True, salt=salt, nonce=nonce, ciphertext=ciphertext)


def check_header(envelope: object, *, max_schema: int) -> None:
    """The header checks an import makes before it derives a key: shape, version, exact KDF costs, and a database
    schema no newer than `max_schema`. `ExportInvalid` or `ExportTooNew`."""
    checked = _check(envelope)
    if checked.schema > max_schema:
        raise ExportTooNew("A newer database schema.")


def seal(payload: bytes, passphrase: str | None, *, created_at: str, app_version: str, schema: int) -> dict[str, Any]:
    """The envelope for `payload` (the JSON bytes of the payload object). With a passphrase it is encrypted, with a new
    salt and nonce every time; without one it is plain, with the SHA-256 of the payload's canonical form."""
    header: dict[str, Any] = {
        "format": FORMAT,
        "version": VERSION,
        "created_at": created_at,
        "app_version": app_version,
        "schema": schema,
    }
    if passphrase is None:
        document = strict_loads(payload)
        envelope = {
            **header,
            "encryption": None,
            "payload": document,
            "sha256": hashlib.sha256(canonical(document)).hexdigest(),
        }
    else:
        salt = os.urandom(SALT_BYTES)
        nonce = os.urandom(NONCE_BYTES)
        header["encryption"] = {
            "cipher": CIPHER,
            "kdf": KDF_NAME,
            "n": SCRYPT_N,
            "r": SCRYPT_R,
            "p": SCRYPT_P,
            "salt": _b64(salt),
            "nonce": _b64(nonce),
        }
        sealed = AESGCM(derive_key(passphrase, salt)).encrypt(nonce, payload, canonical(header))
        envelope = {**header, "ciphertext": _b64(sealed)}
    _check(envelope)  # what this module writes, it also accepts
    return envelope


def open_envelope(envelope: object, passphrase: str | None) -> bytes:
    """The payload's bytes (canonical JSON). The header is checked first (`ExportInvalid`, `ExportTooNew`); then a
    plain file's SHA-256, or an encrypted file's tag: `PassphraseRequired` without a passphrase, `WrongPassphrase`
    when the tag fails. A passphrase given for a plain file is ignored."""
    checked = _check(envelope)
    if not isinstance(envelope, dict):  # `_check` has refused anything else; this narrows the type
        raise ExportInvalid("Not a ShelfSync export file.")
    if not checked.encrypted:
        body = canonical(checked.payload)
        if hashlib.sha256(body).hexdigest() != checked.sha256:
            raise ExportInvalid("The file is damaged: its checksum doesn't match.")
        return body
    if passphrase is None:
        raise PassphraseRequired("The file is encrypted.")
    key = derive_key(passphrase, checked.salt)
    aad = canonical({name: value for name, value in envelope.items() if name != "ciphertext"})
    try:
        return AESGCM(key).decrypt(checked.nonce, checked.ciphertext, aad)
    except InvalidTag:
        raise WrongPassphrase("The passphrase doesn't match, or the file was changed.") from None
