"""The signed release manifest (SYS-06, 06 section 6).

`manifest.json` is UTF-8 JSON written canonically (sorted keys, no spaces, no trailing newline). `manifest.json.sig` is
exactly the 64 bytes of an Ed25519 signature over the exact bytes of `manifest.json`: nothing else is accepted. The
signature is checked **before** the JSON is parsed, so a hostile file is never handed to the parser unless the
owner's key signed it.

Fields (all required, none unknown): `format` (1), `app` ("shelfsync"), `version`, `tag` ("v" + version),
`source_commit` (40 lowercase hex), `built_at` (UTC, ISO 8601, ends in Z), `schema_version` (the highest migration
number), `assets` (the two release files, each `{size, sha256}`) and `files` (every file of the version folder, a
relative path with `/`, each `{size, sha256}`).
"""

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from shelfsync.update import release_key
from shelfsync.update.versions import VersionError, is_newer, parse_version, tag_for

MANIFEST_FORMAT = 1
APP_NAME = "shelfsync"
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
SIGNATURE_BYTES = 64
MAX_FILES = 20_000
MAX_PATH_LENGTH = 240
MAX_FILE_BYTES = 2**40

MANIFEST_NAME = "manifest.json"
SIGNATURE_NAME = "manifest.json.sig"


def setup_asset_name(version: str) -> str:
    return f"ShelfSync-Setup-{version}.exe"


def zip_asset_name(version: str) -> str:
    return f"shelfsync-{version}-win64.zip"


class ManifestError(Exception):
    """A manifest or signature was refused. `code` is one of the fixed codes below; the message never holds anything
    from the file."""

    CODES = (
        "too_large",
        "no_key",
        "bad_signature",
        "bad_format",
        "bad_path",
        "not_newer",
        "tag_mismatch",
        "wrong_version",
    )

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class FileEntry:
    size: int
    sha256: str


@dataclass(frozen=True)
class Manifest:
    version: str
    tag: str
    source_commit: str
    built_at: str
    schema_version: int
    assets: dict[str, FileEntry]
    files: dict[str, FileEntry]


# ---- paths ---------------------------------------------------------------------------------------------------------

_RESERVED = frozenset({"con", "prn", "aux", "nul", *(f"com{i}" for i in range(10)), *(f"lpt{i}" for i in range(10))})
_SUPERSCRIPT_DIGITS = "¹²³"  # COM1, COM2, COM3 written with superscripts are reserved too
_FORBIDDEN_CHARACTERS = frozenset('<>:"|?*\\')


def is_safe_relative_path(path: object) -> bool:
    """A relative path with `/` that can't leave the folder it is unpacked into on Windows: no `..`, drive letter or
    stream (`:`), leading slash, backslash, empty or dot component, trailing dot or space, reserved device name,
    control character or character Windows forbids in a name."""
    if not isinstance(path, str) or not path or len(path) > MAX_PATH_LENGTH or path.startswith("/"):
        return False
    for component in path.split("/"):
        if component in ("", ".", "..") or component != component.rstrip(" ."):
            return False
        if any(ord(ch) < 32 or ord(ch) == 127 or ch in _FORBIDDEN_CHARACTERS for ch in component):
            return False
        stem = component.split(".", 1)[0].rstrip(" ").casefold()
        if stem in _RESERVED or (stem[:3] in ("com", "lpt") and stem[3:] and stem[3:] in _SUPERSCRIPT_DIGITS):
            return False
    return True


def fold_path(path: str) -> str:
    """The form in which two names count as the same file on Windows (case-insensitive, normalised)."""
    return unicodedata.normalize("NFC", path).casefold()


# ---- parsing -------------------------------------------------------------------------------------------------------

_SHA256 = re.compile(r"[0-9a-f]{64}")
_COMMIT = re.compile(r"[0-9a-f]{40}")
_BUILT_AT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?Z")
_TOP_LEVEL = frozenset(
    {"format", "app", "version", "tag", "source_commit", "built_at", "schema_version", "assets", "files"}
)


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ManifestError("bad_format")
        result[key] = value
    return result


def _refuse_constant(_name: str) -> Any:
    raise ManifestError("bad_format")  # NaN and Infinity aren't JSON


def _is_int(value: object) -> bool:
    return type(value) is int  # not a bool


def _entry(value: object) -> FileEntry:
    if not isinstance(value, dict) or set(value) != {"size", "sha256"}:
        raise ManifestError("bad_format")
    size, digest = value["size"], value["sha256"]
    if (
        not _is_int(size)
        or not 0 <= size <= MAX_FILE_BYTES
        or not isinstance(digest, str)
        or not _SHA256.fullmatch(digest)
    ):
        raise ManifestError("bad_format")
    return FileEntry(size, digest)


def _entries(value: object, *, check_paths: bool) -> dict[str, FileEntry]:
    if not isinstance(value, dict):
        raise ManifestError("bad_format")
    if len(value) > MAX_FILES:
        raise ManifestError("bad_format")
    seen: set[str] = set()
    result: dict[str, FileEntry] = {}
    for name, entry in value.items():
        if check_paths:
            if not is_safe_relative_path(name):
                raise ManifestError("bad_path")
            folded = fold_path(name)
            if folded in seen:
                raise ManifestError("bad_path")  # two names for one file on Windows
            seen.add(folded)
        result[name] = _entry(entry)
    return result


def parse_manifest(data: bytes) -> Manifest:
    """Parse and validate manifest bytes. This does NOT check a signature: call `verify_and_parse` for anything that
    came from outside. Raises ManifestError."""
    if len(data) > MAX_MANIFEST_BYTES:
        raise ManifestError("too_large")
    try:
        loaded = json.loads(data.decode("utf-8"), object_pairs_hook=_no_duplicates, parse_constant=_refuse_constant)
    except UnicodeDecodeError, ValueError, RecursionError:  # a ManifestError from the hooks passes through
        raise ManifestError("bad_format") from None
    if not isinstance(loaded, dict) or set(loaded) != _TOP_LEVEL:
        raise ManifestError("bad_format")
    if not _is_int(loaded["format"]) or loaded["format"] != MANIFEST_FORMAT or loaded["app"] != APP_NAME:
        raise ManifestError("bad_format")
    version = loaded["version"]
    try:
        parse_version(version)
        expected_tag = tag_for(version)
    except VersionError:
        raise ManifestError("bad_format") from None
    if loaded["tag"] != expected_tag:
        raise ManifestError("tag_mismatch")
    commit, built_at, schema = loaded["source_commit"], loaded["built_at"], loaded["schema_version"]
    if not isinstance(commit, str) or not _COMMIT.fullmatch(commit):
        raise ManifestError("bad_format")
    if not isinstance(built_at, str) or not _BUILT_AT.fullmatch(built_at):
        raise ManifestError("bad_format")
    try:
        datetime.fromisoformat(built_at)
    except ValueError:
        raise ManifestError("bad_format") from None
    if not _is_int(schema) or not 1 <= schema <= 100_000:
        raise ManifestError("bad_format")
    assets = _entries(loaded["assets"], check_paths=False)
    if set(assets) != {setup_asset_name(version), zip_asset_name(version)}:
        raise ManifestError("bad_format")
    files = _entries(loaded["files"], check_paths=True)
    if not files:
        raise ManifestError("bad_format")
    return Manifest(version, expected_tag, commit, built_at, schema, assets, files)


def verify_signature(manifest_bytes: bytes, signature: bytes) -> None:
    """Check `signature` (exactly 64 raw bytes) over the exact bytes against the key in `release_key.PUBLIC_KEY`.
    Raises ManifestError: `no_key` (no key in this build: nothing can be installed), `bad_signature`."""
    if len(manifest_bytes) > MAX_MANIFEST_BYTES:
        raise ManifestError("too_large")
    key_bytes = release_key.PUBLIC_KEY  # read at the moment of use; nothing else can supply a key
    if key_bytes is None:
        raise ManifestError("no_key")
    if not isinstance(signature, bytes) or len(signature) != SIGNATURE_BYTES:
        raise ManifestError("bad_signature")
    try:
        Ed25519PublicKey.from_public_bytes(key_bytes).verify(signature, manifest_bytes)
    except InvalidSignature, ValueError:  # ValueError: a key that isn't 32 bytes (a build mistake): refuse
        raise ManifestError("bad_signature") from None


def verify_and_parse(manifest_bytes: bytes, signature: bytes) -> Manifest:
    """The only way a downloaded manifest becomes a `Manifest`: signature first, then the parse."""
    verify_signature(manifest_bytes, signature)
    return parse_manifest(manifest_bytes)


# ---- what the updater accepts ---------------------------------------------------------------------------------------


def check_acceptable(manifest: Manifest, *, installed: str, release_tag: str | None) -> None:
    """An update is accepted only if its version is strictly higher than the installed one (never a downgrade by
    update, never the same version) and, when it came from a release, the tag matches that release."""
    if release_tag is not None and manifest.tag != release_tag:
        raise ManifestError("tag_mismatch")
    if not is_newer(manifest.version, installed):
        raise ManifestError("not_newer")


def check_is_version(manifest: Manifest, *, version: str, release_tag: str) -> None:
    """For the running version's own manifest (first check after a fresh install): it must be exactly that version
    and come from that tag."""
    if manifest.tag != release_tag:
        raise ManifestError("tag_mismatch")
    if manifest.version != version:
        raise ManifestError("wrong_version")


# ---- writing (CI and the release tools) -----------------------------------------------------------------------------


def canonical_bytes(document: dict[str, Any]) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def parse_files_txt(text: str) -> dict[str, FileEntry]:
    """The build's `files.txt`: one file per line, `path<TAB>size<TAB>sha256`."""
    files: dict[str, FileEntry] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != 3 or not parts[1].isascii() or not parts[1].isdigit():
            raise ManifestError("bad_format")
        if parts[0] in files:
            raise ManifestError("bad_path")
        files[parts[0]] = FileEntry(int(parts[1]), parts[2])
    return files


def make_manifest(
    *,
    version: str,
    source_commit: str,
    built_at: str,
    schema_version: int,
    assets: dict[str, FileEntry],
    files: dict[str, FileEntry],
) -> bytes:
    """The unsigned manifest for CI. It is parsed again before it is returned, so a manifest this updater would
    refuse is never written."""
    document: dict[str, Any] = {
        "format": MANIFEST_FORMAT,
        "app": APP_NAME,
        "version": version,
        "tag": tag_for(version),
        "source_commit": source_commit,
        "built_at": built_at,
        "schema_version": schema_version,
        "assets": {name: {"size": entry.size, "sha256": entry.sha256} for name, entry in assets.items()},
        "files": {name: {"size": entry.size, "sha256": entry.sha256} for name, entry in files.items()},
    }
    data = canonical_bytes(document)
    parse_manifest(data)
    return data


def hash_file(path: Path) -> FileEntry:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return FileEntry(size, digest.hexdigest())


def main(argv: Sequence[str] | None = None) -> int:
    """`python -m shelfsync.update.manifest`: write the unsigned manifest in CI from `build\\files.txt`."""
    from shelfsync.db.migrate import discover  # local: the CLI is the only user

    parser = argparse.ArgumentParser(description="Write the unsigned manifest.json for a release.")
    parser.add_argument("--version", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--built-at", required=True)
    parser.add_argument("--files-txt", type=Path, required=True)
    parser.add_argument("--setup", type=Path, required=True, help="the ShelfSync-Setup-<v>.exe")
    parser.add_argument("--zip", type=Path, required=True, help="the shelfsync-<v>-win64.zip")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    schema = max(migration.version for migration in discover())
    data = make_manifest(
        version=args.version,
        source_commit=args.source_commit,
        built_at=args.built_at,
        schema_version=schema,
        assets={
            setup_asset_name(args.version): hash_file(args.setup),
            zip_asset_name(args.version): hash_file(args.zip),
        },
        files=parse_files_txt(args.files_txt.read_text(encoding="utf-8")),
    )
    args.out.write_bytes(data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
