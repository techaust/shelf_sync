"""Shared helpers of the release tools (keygen.py, sign.py, verify_setup.py). Run by the owner, outside the Claude app.

Nothing here logs, stores or echoes a passphrase or a private key.

`describe_encryption` reads the algorithm out of an encrypted PKCS#8 file (RFC 5958 / PKCS#5 v2.0): cryptography's docs
say `BestAvailableEncryption`'s algorithm "may change over time" (04-A V46), so `keygen.py` prints what it actually
wrote, and `sign.py` loads any file `keygen.py` made whatever the algorithm was.
"""

import base64
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

REPO_ROOT = Path(__file__).resolve().parents[2]
MIN_PASSPHRASE_LENGTH = 16

_OIDS = {
    "1.2.840.113549.1.5.13": "PBES2",
    "1.2.840.113549.1.5.12": "PBKDF2",
    "1.3.6.1.4.1.11591.4.11": "scrypt",
    "1.2.840.113549.2.7": "HMAC-SHA1",
    "1.2.840.113549.2.9": "HMAC-SHA256",
    "1.2.840.113549.2.10": "HMAC-SHA384",
    "1.2.840.113549.2.11": "HMAC-SHA512",
    "2.16.840.1.101.3.4.1.2": "AES-128-CBC",
    "2.16.840.1.101.3.4.1.22": "AES-192-CBC",
    "2.16.840.1.101.3.4.1.42": "AES-256-CBC",
    "1.2.840.113549.3.7": "3DES-CBC",
}


def _read(data: bytes, offset: int) -> tuple[int, bytes, int]:
    """One DER element at `offset`: (tag, content, offset after it)."""
    tag = data[offset]
    length = data[offset + 1]
    start = offset + 2
    if length & 0x80:
        count = length & 0x7F
        length = int.from_bytes(data[start : start + count], "big")
        start += count
    return tag, data[start : start + length], start + length


def _children(content: bytes) -> list[tuple[int, bytes]]:
    found: list[tuple[int, bytes]] = []
    offset = 0
    while offset < len(content):
        tag, body, offset = _read(content, offset)
        found.append((tag, body))
    return found


def _oid(body: bytes) -> str:
    parts = [body[0] // 40, body[0] % 40]
    value = 0
    for byte in body[1:]:
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            parts.append(value)
            value = 0
    return ".".join(str(part) for part in parts)


def _name(oid: str) -> str:
    return _OIDS.get(oid, f"OID {oid}")


def describe_encryption(pem: bytes) -> str:
    """A short description of how an encrypted PKCS#8 PEM is protected, e.g. `PBES2, PBKDF2 (HMAC-SHA256, 2048
    iterations), AES-256-CBC`. Anything it can't read is reported as such, never guessed."""
    try:
        lines = [line for line in pem.decode("ascii").splitlines() if line and not line.startswith("-----")]
        der = base64.b64decode("".join(lines))
        _, outer, _ = _read(der, 0)  # EncryptedPrivateKeyInfo
        algorithm = _children(outer)[0][1]
        algorithm_parts = _children(algorithm)
        scheme = _name(_oid(algorithm_parts[0][1]))
        if scheme != "PBES2":
            return scheme
        kdf_part, cipher_part = _children(algorithm_parts[1][1])
        kdf_parts = _children(kdf_part[1])
        kdf = _name(_oid(kdf_parts[0][1]))
        details: list[str] = []
        parameters = _children(kdf_parts[1][1])
        if kdf == "PBKDF2":
            iterations = int.from_bytes(parameters[1][1], "big")
            prf = "HMAC-SHA1"  # PBKDF2's default when none is named
            for tag, body in parameters[2:]:
                if tag == 0x30:
                    prf = _name(_oid(_children(body)[0][1]))
            details = [prf, f"{iterations} iterations"]
        elif kdf == "scrypt":
            n, r, p = (int.from_bytes(parameters[index][1], "big") for index in (1, 2, 3))
            details = [f"N={n}", f"r={r}", f"p={p}"]
        cipher = _name(_oid(_children(cipher_part[1])[0][1]))
        suffix = f" ({', '.join(details)})" if details else ""
        return f"{scheme}, {kdf}{suffix}, {cipher}"
    except ValueError, IndexError, TypeError:
        return "unreadable (not an encrypted PKCS#8 file this tool recognises)"


def load_private_key(path: Path, passphrase: str) -> Ed25519PrivateKey:
    """The Ed25519 key in an encrypted PEM written by keygen.py. ValueError for a wrong passphrase, a damaged file or
    any other kind of key; the message never holds the passphrase or key material."""
    try:
        key = serialization.load_pem_private_key(path.read_bytes(), password=passphrase.encode("utf-8"))
    except (ValueError, TypeError) as error:
        raise ValueError("The passphrase is wrong or the file is not an encrypted key") from error
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("The file holds a key that is not Ed25519")
    return key


def public_hex(key: Ed25519PrivateKey) -> str:
    raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return raw.hex()
