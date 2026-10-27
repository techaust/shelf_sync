"""The versions kept on disk and their signed manifests (`manifests\\<v>.json` and `.json.sig`, outside the version
folders). A kept folder is re-checked, signature and every file, before anything switches to it (roll back, or an
update downloaded earlier): the check is run again because the folder has sat on disk since it was verified.
"""

import os
from pathlib import Path

from shelfsync.paths import is_plain_file
from shelfsync.update.layout import InstallLayout
from shelfsync.update.manifest import (
    MAX_MANIFEST_BYTES,
    SIGNATURE_BYTES,
    Manifest,
    ManifestError,
    verify_and_parse,
)
from shelfsync.update.unpack import UnpackError, verify_tree


class KeptVersionError(Exception):
    """`code`: `manifest_missing`, `no_key` (this build has no release key, so nothing is trusted), `manifest_invalid`
    (signature or content), `files_changed` (the folder isn't what the manifest lists)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _read_limited(path: Path, limit: int) -> bytes | None:
    if not is_plain_file(path):
        return None
    try:
        with path.open("rb") as handle:
            data = handle.read(limit + 1)
    except OSError:
        return None
    return data if len(data) <= limit else None


def write_manifest(layout: InstallLayout, version: str, manifest_bytes: bytes, signature: bytes) -> None:
    """Keep a verified manifest and its signature for `version` (atomic replace; the caller verified them)."""
    layout.manifests.mkdir(parents=True, exist_ok=True)
    for path, data in ((layout.manifest_path(version), manifest_bytes), (layout.signature_path(version), signature)):
        temporary = path.with_name(f"{path.name}.tmp")
        temporary.write_bytes(data)
        os.replace(temporary, path)


def load_manifest(layout: InstallLayout, version: str) -> Manifest:
    """The kept manifest for `version`, its signature checked again against the build's release key."""
    manifest_bytes = _read_limited(layout.manifest_path(version), MAX_MANIFEST_BYTES)
    signature = _read_limited(layout.signature_path(version), SIGNATURE_BYTES)
    if manifest_bytes is None or signature is None:
        raise KeptVersionError("manifest_missing")
    try:
        manifest = verify_and_parse(manifest_bytes, signature)
    except ManifestError as error:
        raise KeptVersionError("no_key" if error.code == "no_key" else "manifest_invalid") from None
    if manifest.version != version:
        raise KeptVersionError("manifest_invalid")
    return manifest


def verify_kept_version(layout: InstallLayout, version: str) -> Manifest:
    """The manifest, verified, and the version folder checked against it, file by file."""
    manifest = load_manifest(layout, version)
    try:
        verify_tree(layout.version_dir(version), manifest)
    except UnpackError:
        raise KeptVersionError("files_changed") from None
    return manifest
