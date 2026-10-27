"""Unpacking a release zip (SYS-06, 06 section 4) and checking a version folder against its manifest.

The zip is untrusted until every entry has passed. Refused: zip-slip names (`..`, a drive letter, a leading slash or
backslash, reserved Windows names, and the rest of `manifest.is_safe_relative_path`), names that differ only in case,
encrypted entries, links and special entries, more than 500 MB for one entry, 1 GB in all, and a compression ratio above
100:1 for an entry over 10 MB. Then the set of files must equal `manifest.files` exactly (none extra, none missing,
every size and SHA-256 right). Files go into `versions\\.incoming-<v>` and the folder is renamed to `versions\\<v>` only
at the end; any failure removes the incoming folder (without following a link in it).
"""

import hashlib
import logging
import os
import stat
import zipfile
from pathlib import Path

from shelfsync.paths import is_plain_file, remove_entry
from shelfsync.update.layout import InstallLayout
from shelfsync.update.manifest import Manifest, fold_path, hash_file, is_safe_relative_path

_log = logging.getLogger("shelfsync.update")

MAX_ENTRY_BYTES = 500 * 1024 * 1024
MAX_TOTAL_BYTES = 1024 * 1024 * 1024
RATIO_FLOOR_BYTES = 10 * 1024 * 1024
MAX_RATIO = 100
MAX_ENTRIES = 25_000
_CHUNK = 256 * 1024
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400


class UnpackError(Exception):
    """`code`: `bad_zip`, `bad_entry`, `too_big`, `ratio`, `mismatch` (not the manifest's files), `disk_error`."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def remove_incoming_leftovers(layout: InstallLayout) -> None:
    """Remove every `.incoming-*` folder a crashed unpack left, without following links."""
    if not layout.versions.is_dir():
        return
    for entry in layout.versions.iterdir():
        if entry.name.startswith(".incoming-"):
            try:
                remove_entry(entry)
            except OSError as error:
                _log.warning("Couldn't remove %s: %s", entry.name, error)


def _check_entries(infos: list[zipfile.ZipInfo], manifest: Manifest) -> dict[str, zipfile.ZipInfo]:
    """Check every entry; return the files by name. Directory entries are checked and left out."""
    if len(infos) > MAX_ENTRIES:
        raise UnpackError("bad_zip")
    files: dict[str, zipfile.ZipInfo] = {}
    folded: set[str] = set()
    total = 0
    for info in infos:
        name = info.filename
        is_directory = name.endswith("/")
        bare = name[:-1] if is_directory else name
        if not is_safe_relative_path(bare) or info.flag_bits & 0x1:
            raise UnpackError("bad_entry")
        if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            raise UnpackError("bad_entry")
        # The Unix file type, if the zip records one (a zip made on Windows or by Python's zipfile may record none):
        # only a plain file, or a folder for a folder entry, passes; a symlink, device or pipe is refused.
        kind = stat.S_IFMT((info.external_attr >> 16) & 0xFFFF)
        allowed = (stat.S_IFDIR,) if is_directory else (stat.S_IFREG,)
        if info.external_attr & _FILE_ATTRIBUTE_REPARSE_POINT or (kind and kind not in allowed):
            raise UnpackError("bad_entry")  # a link or a special entry
        key = fold_path(bare)
        if key in folded:
            raise UnpackError("bad_entry")
        folded.add(key)
        if is_directory:
            continue
        if info.file_size > MAX_ENTRY_BYTES:
            raise UnpackError("too_big")
        total += info.file_size
        if total > MAX_TOTAL_BYTES:
            raise UnpackError("too_big")
        if info.file_size > RATIO_FLOOR_BYTES and info.file_size > MAX_RATIO * max(info.compress_size, 1):
            raise UnpackError("ratio")
        files[name] = info
    if set(files) != set(manifest.files):
        raise UnpackError("mismatch")
    for name, info in files.items():
        if info.file_size != manifest.files[name].size:
            raise UnpackError("mismatch")
    return files


def _extract(archive: zipfile.ZipFile, files: dict[str, zipfile.ZipInfo], manifest: Manifest, incoming: Path) -> None:
    base = os.path.normcase(os.path.abspath(incoming)) + os.sep
    for name, info in files.items():
        target = incoming.joinpath(*name.split("/"))
        if not (os.path.normcase(os.path.abspath(target)) + os.sep).startswith(base):
            raise UnpackError("bad_entry")  # not reachable after the name check; kept as a second line of defence
        target.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        written = 0
        with archive.open(info) as source, target.open("xb") as out:
            while chunk := source.read(_CHUNK):
                written += len(chunk)
                if written > info.file_size:
                    raise UnpackError("too_big")  # the header lied about the size
                digest.update(chunk)
                out.write(chunk)
        expected = manifest.files[name]
        if written != expected.size or digest.hexdigest() != expected.sha256:
            raise UnpackError("mismatch")


def unpack_release(zip_path: Path, manifest: Manifest, layout: InstallLayout) -> Path:
    """Unpack into `versions\\.incoming-<v>`, then rename to `versions\\<v>`. Returns the final folder."""
    incoming = layout.incoming_dir(manifest.version)
    final = layout.version_dir(manifest.version)
    try:
        layout.versions.mkdir(parents=True, exist_ok=True)
        remove_incoming_leftovers(layout)
        with zipfile.ZipFile(zip_path) as archive:
            files = _check_entries(archive.infolist(), manifest)
            incoming.mkdir()
            _extract(archive, files, manifest, incoming)
        if os.path.lexists(final):
            remove_entry(final)  # an earlier download of this same version
        incoming.rename(final)
    except zipfile.BadZipFile, EOFError, NotImplementedError, RuntimeError:
        _discard(incoming)
        raise UnpackError("bad_zip") from None
    except OSError:
        _discard(incoming)
        raise UnpackError("disk_error") from None
    except BaseException:
        _discard(incoming)
        raise
    return final


def _discard(folder: Path) -> None:
    try:
        if os.path.lexists(folder):
            remove_entry(folder)
    except OSError as error:
        _log.warning("Couldn't remove %s: %s", folder.name, error)


def verify_tree(folder: Path, manifest: Manifest) -> None:
    """Check a version folder against its manifest: every file present with the right size and SHA-256, nothing else
    in it (empty folders aside), and no link of any kind. Raises UnpackError("mismatch")."""
    found: dict[str, Path] = {}
    pending = [(folder, "")]
    if not folder.is_dir() or folder.is_symlink() or os.path.isjunction(folder):
        raise UnpackError("mismatch")
    while pending:
        directory, prefix = pending.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError:
            raise UnpackError("mismatch") from None
        for entry in entries:
            relative = f"{prefix}{entry.name}"
            path = Path(entry.path)
            if entry.is_symlink() or os.path.isjunction(path):
                raise UnpackError("mismatch")
            if entry.is_dir(follow_symlinks=False):
                pending.append((path, f"{relative}/"))
            elif is_plain_file(path):
                found[relative] = path
            else:
                raise UnpackError("mismatch")
    if set(found) != set(manifest.files):
        raise UnpackError("mismatch")
    for name, path in found.items():
        try:
            actual = hash_file(path)
        except OSError:
            raise UnpackError("mismatch") from None
        expected = manifest.files[name]
        if actual.size != expected.size or actual.sha256 != expected.sha256:
            raise UnpackError("mismatch")
