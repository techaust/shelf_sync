"""Check a downloaded Setup.exe before running it (06 section 6, "First install is different"). Run by the owner,
outside the Claude app, before the first install: nothing ShelfSync controls checks a hand-downloaded installer.

    PYTHONPATH=backend uv run python tools/release/verify_setup.py <manifest.json> <manifest.json.sig> <Setup.exe>

1. verifies the manifest's signature with the public key in THIS checkout's `release_key.py` (never a key fetched from
   GitHub or anywhere else), then reads the manifest;
2. compares the SHA-256 of the Setup.exe you downloaded with the one the signed manifest lists for it.

Exit code 0 only if both pass. The same result can be had from `Get-FileHash`; this tool just does the comparison.
"""

import hashlib
import sys
from pathlib import Path

from shelfsync.update.manifest import ManifestError, setup_asset_name, verify_and_parse

_MESSAGES = {
    "no_key": "release_key.py in this checkout has no public key yet, so nothing can be verified.",
    "bad_signature": (
        "The signature does not match this manifest and the key in release_key.py. Do NOT run the installer."
    ),
}


def verify(manifest_path: Path, signature_path: Path, setup_path: Path) -> str:
    """Return the version if everything checks out; raise ValueError with a plain message otherwise."""
    try:
        manifest = verify_and_parse(manifest_path.read_bytes(), signature_path.read_bytes())
    except ManifestError as error:
        raise ValueError(_MESSAGES.get(error.code, f"The manifest is not acceptable ({error.code}).")) from None
    except OSError:
        raise ValueError("A manifest or signature file could not be read.") from None
    entry = manifest.assets[setup_asset_name(manifest.version)]
    digest = hashlib.sha256()
    size = 0
    try:
        with setup_path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
    except OSError:
        raise ValueError("The installer file could not be read.") from None
    if size != entry.size or digest.hexdigest() != entry.sha256:
        raise ValueError("The installer does not match the signed manifest (size or SHA-256). Do NOT run it.")
    return manifest.version


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 3:
        sys.stderr.write("Usage: verify_setup.py <manifest.json> <manifest.json.sig> <ShelfSync-Setup-x.exe>\n")
        return 2
    try:
        version = verify(Path(arguments[0]), Path(arguments[1]), Path(arguments[2]))
    except ValueError as error:
        sys.stderr.write(f"FAILED: {error}\n")
        return 1
    sys.stdout.write(f"OK: the signature is valid and the installer is exactly ShelfSync {version}.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
