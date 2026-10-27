"""Downloading a release (SYS-06): the manifest and its signature first (small, in memory), then the zip, streamed to
`update\\downloads\\` and hashed while it arrives. The zip is capped at its manifest size and at 300 MB, the program
drive needs at least 3 times the zip's size free, and the file is renamed to its final name only after its size and
SHA-256 match the signed manifest.
"""

import hashlib
import logging
import shutil
from collections.abc import Callable
from pathlib import Path

from shelfsync.paths import remove_entry
from shelfsync.update.github import GitHubClient, ReleaseAsset
from shelfsync.update.manifest import SIGNATURE_BYTES, FileEntry, is_safe_relative_path

_log = logging.getLogger("shelfsync.update")

MAX_ZIP_BYTES = 300 * 1024 * 1024
FREE_SPACE_FACTOR = 3
_CHUNK = 256 * 1024


class DownloadFailed(Exception):
    """`code`: `bad_name`, `too_large`, `no_space`, `size_mismatch`, `hash_mismatch`, `disk_error`. (The GitHub
    client adds its own codes through DownloadRefused.)"""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def free_bytes(path: Path) -> int:
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return shutil.disk_usage(probe).free


def fetch_small(client: GitHubClient, asset: ReleaseAsset, limit: int) -> bytes:
    """A small asset (the manifest or its signature) read into memory, never more than `limit` bytes."""
    if asset.size > limit:
        raise DownloadFailed("too_large")
    data = bytearray()
    with client.open_asset(asset) as response:
        for chunk in response.iter_bytes():
            data += chunk
            if len(data) > limit:
                raise DownloadFailed("too_large")
    return bytes(data)


def fetch_signature(client: GitHubClient, asset: ReleaseAsset) -> bytes:
    return fetch_small(client, asset, SIGNATURE_BYTES * 2)  # a wrong length is refused later; this only bounds memory


def download_zip(
    client: GitHubClient,
    asset: ReleaseAsset,
    expected: FileEntry,
    downloads: Path,
    program_dir: Path,
    free: Callable[[Path], int] = free_bytes,
) -> Path:
    """Stream the zip into `downloads`, check it against `expected` (from the verified manifest) and return its path."""
    if "/" in asset.name or not is_safe_relative_path(asset.name):  # the name came from GitHub: never a path
        raise DownloadFailed("bad_name")
    cap = min(expected.size, MAX_ZIP_BYTES)
    if expected.size > MAX_ZIP_BYTES or asset.size != expected.size:
        raise DownloadFailed("too_large" if expected.size > MAX_ZIP_BYTES else "size_mismatch")
    if free(program_dir) < FREE_SPACE_FACTOR * expected.size:
        raise DownloadFailed("no_space")
    downloads.mkdir(parents=True, exist_ok=True)
    final = downloads / asset.name
    part = downloads / f"{asset.name}.part"
    for leftover in (part, final):
        if leftover.exists() or leftover.is_symlink():
            remove_entry(leftover)
    digest = hashlib.sha256()
    total = 0
    try:
        with client.open_asset(asset) as response, part.open("xb") as out:
            declared = response.headers.get("content-length")
            if declared is not None and declared.isascii() and declared.isdigit() and int(declared) != expected.size:
                raise DownloadFailed("size_mismatch")
            for chunk in response.iter_bytes(_CHUNK):
                total += len(chunk)
                if total > cap:
                    raise DownloadFailed("size_mismatch")
                digest.update(chunk)
                out.write(chunk)
        if total != expected.size:
            raise DownloadFailed("size_mismatch")
        if digest.hexdigest() != expected.sha256:
            raise DownloadFailed("hash_mismatch")
        part.replace(final)
    except OSError:
        part.unlink(missing_ok=True)
        raise DownloadFailed("disk_error") from None
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    return final


def clear_downloads(downloads: Path) -> None:
    """Empty the downloads folder (at start-up), never following a link."""
    if not downloads.is_dir():
        return
    for entry in downloads.iterdir():
        try:
            remove_entry(entry)
        except OSError as error:
            _log.warning("Couldn't remove %s from the downloads folder: %s", entry.name, error)
