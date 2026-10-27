"""Sign a release manifest (06 section 6, SYS-06). Run by the owner, outside the Claude app, after CI built the release.

    PYTHONPATH=backend uv run python tools/release/sign.py <manifest.json> <the encrypted key>.pem

It reads the unsigned `manifest.json` that CI made, SHOWS what is being signed (version, tag, source commit, build
time, and the SHA-256 of both assets) so you can compare the commit with the one you expect, asks y/N, asks for the
passphrase with hidden input, and writes `manifest.json.sig` next to it: exactly the 64 bytes of Ed25519 over the exact
bytes of the manifest. It refuses to overwrite a signature, and refuses a key that isn't the one in
`backend/shelfsync/update/release_key.py` (once that has a key), because an app that ships one key can't verify a
signature made with another. Before it writes anything it verifies the new signature with the public key.

Nothing here logs, stores or echoes the passphrase or the private key.
"""

import getpass
import sys
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from keyfile import load_private_key, public_hex

from shelfsync.update import release_key
from shelfsync.update.manifest import MAX_MANIFEST_BYTES, SIGNATURE_NAME, ManifestError, parse_manifest


class SignError(Exception):
    """Something the owner can fix. The message holds no secret."""


def describe(data: bytes) -> str:
    """What the owner is asked to approve, as text."""
    try:
        manifest = parse_manifest(data)
    except ManifestError as error:
        raise SignError(f"This is not a manifest the app would accept ({error.code}). Nothing was signed.") from None
    lines = [
        f"Version:        {manifest.version}",
        f"Tag:            {manifest.tag}",
        f"Source commit:  {manifest.source_commit}",
        f"Built at (UTC): {manifest.built_at}",
        f"Schema version: {manifest.schema_version}",
        f"Files listed:   {len(manifest.files)}",
    ]
    for name, entry in sorted(manifest.assets.items()):
        lines.append(f"Asset {name}")
        lines.append(f"    size {entry.size}   sha256 {entry.sha256}")
    return "\n".join(lines)


def sign(manifest_path: Path, key_path: Path, passphrase: str, data: bytes | None = None) -> Path:
    """Write the signature next to the manifest and return its path. `data` are the manifest's bytes the owner was shown
    (`main` reads the file once and passes the same bytes to `describe` and here, so a file changed in between is not
    what gets signed); without it the file is read now."""
    if data is None:
        data = manifest_path.read_bytes()
    if len(data) > MAX_MANIFEST_BYTES:
        raise SignError("The manifest is far larger than any real one. Nothing was signed.")
    signature_path = manifest_path.with_name(SIGNATURE_NAME)
    if signature_path.exists():
        raise SignError(f"{SIGNATURE_NAME} already exists. This tool never overwrites a signature.")
    try:
        key = load_private_key(key_path, passphrase)
    except (ValueError, OSError) as error:
        raise SignError(str(error) if isinstance(error, ValueError) else "The key file could not be read.") from None
    built_in = release_key.PUBLIC_KEY
    if built_in is not None and built_in.hex() != public_hex(key):
        raise SignError("This key is not the one in release_key.py, so installed apps would refuse the signature.")
    signature = key.sign(data)
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_hex(key))).verify(signature, data)
    except InvalidSignature:
        raise SignError("The new signature did not verify. Nothing was written.") from None
    with signature_path.open("xb") as handle:  # "x": never overwrite
        handle.write(signature)
    return signature_path


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 2:
        sys.stderr.write("Usage: sign.py <manifest.json> <encrypted key .pem>\n")
        return 2
    manifest_path, key_path = Path(arguments[0]), Path(arguments[1])
    try:
        data = manifest_path.read_bytes()  # read once: what is shown is what is signed
        text = describe(data)
    except OSError:
        sys.stderr.write("The manifest could not be read.\n")
        return 1
    except SignError as error:
        sys.stderr.write(f"{error}\n")
        return 1
    sys.stdout.write("You are about to sign this release manifest:\n\n" + text + "\n\n")
    if release_key.PUBLIC_KEY is None:
        sys.stdout.write("Note: release_key.py has no key yet, so no installed app can verify this signature.\n\n")
    if input("Sign it? [y/N] ").strip().lower() != "y":
        sys.stdout.write("Not signed.\n")
        return 1
    passphrase = getpass.getpass("Passphrase for the key (nothing is shown): ")
    try:
        written = sign(manifest_path, key_path, passphrase, data)
    except SignError as error:
        sys.stderr.write(f"{error}\n")
        return 1
    sys.stdout.write(f"Signed. Wrote {written}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
