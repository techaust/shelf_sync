"""Make the release signing key (06 section 6, SYS-06). Run by the owner, outside the Claude app.

    PYTHONPATH=backend uv run python tools/release/keygen.py <where to save the key>.pem

Writes the private key as an encrypted PKCS#8 PEM to the path you give, which must be OUTSIDE the repository (your
CREDENTIALS folder and an offline copy), and must not exist yet: it never overwrites a key. It asks for the passphrase
twice with hidden input (at least 16 characters), prints the public key as 64 hex characters for
`backend/shelfsync/update/release_key.py` (public, safe to paste), and prints the encryption algorithm it actually
wrote (cryptography's own docs say the default "may change over time", 04-A V46). It then loads the file it wrote and
checks the public key, so a key that can't be loaded is found now, not on release day.

Nothing here logs, stores or echoes the passphrase or the private key.
"""

import getpass
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from keyfile import MIN_PASSPHRASE_LENGTH, REPO_ROOT, describe_encryption, load_private_key, public_hex


class KeygenError(Exception):
    """Something the owner can fix. The message holds no secret."""


def generate(destination: Path, passphrase: str) -> tuple[str, str]:
    """Write a new encrypted key at `destination`; return (public key as hex, the encryption algorithm used)."""
    if len(passphrase) < MIN_PASSPHRASE_LENGTH:
        raise KeygenError(f"The passphrase must be at least {MIN_PASSPHRASE_LENGTH} characters.")
    resolved = destination.resolve()
    if resolved == REPO_ROOT or REPO_ROOT in resolved.parents:
        raise KeygenError("Choose a place outside the ShelfSync folder: a private key must never be in the repository.")
    if destination.exists():
        raise KeygenError("That file already exists. This tool never overwrites a key.")
    if not destination.parent.is_dir():
        raise KeygenError("The folder for the key doesn't exist.")
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(passphrase.encode("utf-8")),
    )
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(pem)
    if public_hex(load_private_key(destination, passphrase)) != public_hex(key):  # the file must load again
        destination.unlink()
        raise KeygenError("The key file could not be read back, so it was removed. Nothing was kept.")
    return public_hex(key), describe_encryption(pem)


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 1:
        sys.stderr.write("Usage: keygen.py <path for the encrypted key, outside the repository>\n")
        return 2
    destination = Path(arguments[0])
    first = getpass.getpass("Passphrase for the new key (at least 16 characters, nothing is shown): ")
    second = getpass.getpass("The same passphrase again: ")
    if first != second:
        sys.stderr.write("The two passphrases are not the same. Nothing was written.\n")
        return 1
    try:
        public, algorithm = generate(destination, first)
    except KeygenError as error:
        sys.stderr.write(f"{error}\n")
        return 1
    sys.stdout.write(f"Key saved: {destination}\n")
    sys.stdout.write(f"Encryption used: {algorithm}\n")
    sys.stdout.write(
        "Public key (paste into backend/shelfsync/update/release_key.py as PUBLIC_KEY = bytes.fromhex(...)):\n"
    )
    sys.stdout.write(f"{public}\n")
    sys.stdout.write(
        "Keep a second, offline copy of the key file. Without it and the passphrase no release can be signed.\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
