"""SYS-06, 06 section 4: unpacking a release (zip-slip, links, bombs, the manifest's exact file set) and checking a
version folder against its manifest."""

import io
import stat
import sys
import zipfile
from pathlib import Path

import pytest

from shelfsync.update import unpack
from shelfsync.update.layout import InstallLayout
from shelfsync.update.manifest import FileEntry, Manifest, parse_manifest
from shelfsync.update.unpack import UnpackError, remove_incoming_leftovers, unpack_release, verify_tree
from tests.update_support import build_release, entries, make_dir_link, make_keys, make_zip

KEYS = make_keys(1)


def prepare(tmp_path: Path, files: dict[str, bytes] | None = None) -> tuple[Manifest, bytes, InstallLayout]:
    release = build_release("0.0.2", KEYS, files)
    return parse_manifest(release.manifest_bytes), release.zip_bytes, InstallLayout(tmp_path / "root")


def write_zip(tmp_path: Path, data: bytes) -> Path:
    path = tmp_path / "release.zip"
    path.write_bytes(data)
    return path


def code_of(zip_path: Path, manifest: Manifest, layout: InstallLayout) -> str:
    with pytest.raises(UnpackError) as caught:
        unpack_release(zip_path, manifest, layout)
    assert not layout.incoming_dir(manifest.version).exists()  # nothing half-unpacked is left
    assert not layout.version_dir(manifest.version).exists()
    return caught.value.code


def test_a_good_release_unpacks_to_its_version_folder(tmp_path: Path) -> None:
    manifest, data, layout = prepare(tmp_path)
    folder = unpack_release(write_zip(tmp_path, data), manifest, layout)
    assert folder == layout.version_dir("0.0.2")
    assert (folder / "shelfsync" / "__init__.py").read_bytes().startswith(b"__version__")
    assert not layout.incoming_dir("0.0.2").exists()
    verify_tree(folder, manifest)  # the folder equals the manifest


def with_extra(files: dict[str, bytes], name: str, content: bytes = b"x") -> bytes:
    """A zip holding the manifest's files and one more entry."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for entry, data in files.items():
            archive.writestr(entry, data)
        archive.writestr(name, content)
    return buffer.getvalue()


@pytest.mark.parametrize(
    "name",
    [
        "../evil.txt",
        "a/../../evil.txt",
        "/abs.txt",
        "C:/win.txt",
        "c:evil.txt",
        "a\\b.txt",
        "CON",
        "nul.txt",
        "a/COM1.dll",
        "a/b.",
        "x:y",
    ],
)
def test_zip_slip_and_reserved_names_are_refused(tmp_path: Path, name: str) -> None:
    manifest, _, layout = prepare(tmp_path)
    data = with_extra(dict.fromkeys(manifest.files, b"x"), name)
    # On Windows zipfile itself reads a backslash as "/", so the entry becomes one more file the manifest doesn't list
    expected = "mismatch" if name == "a\\b.txt" and sys.platform == "win32" else "bad_entry"
    assert code_of(write_zip(tmp_path, data), manifest, layout) == expected
    assert not (tmp_path / "evil.txt").exists()


def test_a_file_outside_the_folder_is_never_written(tmp_path: Path) -> None:
    manifest, _, layout = prepare(tmp_path)
    data = with_extra(dict.fromkeys(manifest.files, b"x"), "../../escape.txt")
    code_of(write_zip(tmp_path, data), manifest, layout)
    assert not list(tmp_path.rglob("escape.txt"))


def test_a_symlink_or_special_entry_is_refused(tmp_path: Path) -> None:
    manifest, _, layout = prepare(tmp_path)
    files = {name: b"x" for name in manifest.files}
    for mode in (stat.S_IFLNK, stat.S_IFCHR, stat.S_IFIFO):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for name, content in files.items():
                archive.writestr(name, content)
            info = zipfile.ZipInfo("link")
            info.external_attr = (mode | 0o777) << 16
            archive.writestr(info, "target")
        assert code_of(write_zip(tmp_path, buffer.getvalue()), manifest, layout) == "bad_entry"


def test_a_reparse_point_attribute_is_refused(tmp_path: Path) -> None:
    manifest, _, layout = prepare(tmp_path)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name in manifest.files:
            archive.writestr(name, b"x")
        info = zipfile.ZipInfo("l")
        info.external_attr = 0x400
        archive.writestr(info, "x")
    assert code_of(write_zip(tmp_path, buffer.getvalue()), manifest, layout) == "bad_entry"


def test_an_encrypted_entry_is_refused(tmp_path: Path) -> None:
    manifest, data, layout = prepare(tmp_path)
    archive = bytearray(data)
    # set the "encrypted" bit in the first central directory entry's flags
    index = bytes(archive).index(b"PK\x01\x02")
    archive[index + 8] |= 0x01
    assert code_of(write_zip(tmp_path, bytes(archive)), manifest, layout) in ("bad_entry", "bad_zip")


def test_names_that_differ_only_in_case_are_refused(tmp_path: Path) -> None:
    manifest, _, layout = prepare(tmp_path)
    data = with_extra(dict.fromkeys(manifest.files, b"x"), "SHELFSYNC/__INIT__.PY")
    assert code_of(write_zip(tmp_path, data), manifest, layout) == "bad_entry"


def test_an_extra_file_is_refused(tmp_path: Path) -> None:
    release = build_release("0.0.2", KEYS)
    manifest = parse_manifest(release.manifest_bytes)
    layout = InstallLayout(tmp_path / "root")
    data = with_extra(release.files, "extra.dll")
    assert code_of(write_zip(tmp_path, data), manifest, layout) == "mismatch"


def test_a_missing_file_is_refused(tmp_path: Path) -> None:
    release = build_release("0.0.2", KEYS)
    manifest = parse_manifest(release.manifest_bytes)
    layout = InstallLayout(tmp_path / "root")
    data = make_zip({name: content for name, content in release.files.items() if name != "python.exe"})
    assert code_of(write_zip(tmp_path, data), manifest, layout) == "mismatch"


def test_a_file_with_the_wrong_hash_is_refused(tmp_path: Path) -> None:
    release = build_release("0.0.2", KEYS)
    manifest = parse_manifest(release.manifest_bytes)
    layout = InstallLayout(tmp_path / "root")
    changed = dict(release.files)
    changed["python.exe"] = b"X" * len(changed["python.exe"])  # same size, other bytes
    assert code_of(write_zip(tmp_path, make_zip(changed)), manifest, layout) == "mismatch"


def test_a_file_of_another_size_is_refused(tmp_path: Path) -> None:
    release = build_release("0.0.2", KEYS)
    manifest = parse_manifest(release.manifest_bytes)
    layout = InstallLayout(tmp_path / "root")
    changed = dict(release.files)
    changed["python.exe"] += b"more"
    assert code_of(write_zip(tmp_path, make_zip(changed)), manifest, layout) == "mismatch"


def test_not_a_zip_is_refused(tmp_path: Path) -> None:
    manifest, _, layout = prepare(tmp_path)
    assert code_of(write_zip(tmp_path, b"this is not a zip"), manifest, layout) == "bad_zip"


def test_a_missing_zip_is_a_disk_error(tmp_path: Path) -> None:
    manifest, _, layout = prepare(tmp_path)
    with pytest.raises(UnpackError) as caught:
        unpack_release(tmp_path / "nope.zip", manifest, layout)
    assert caught.value.code == "disk_error"


def test_the_size_caps_are_enforced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    release = build_release("0.0.2", KEYS)
    manifest = parse_manifest(release.manifest_bytes)
    layout = InstallLayout(tmp_path / "root")
    path = write_zip(tmp_path, release.zip_bytes)
    monkeypatch.setattr(unpack, "MAX_ENTRY_BYTES", 5)
    assert code_of(path, manifest, layout) == "too_big"
    monkeypatch.setattr(unpack, "MAX_ENTRY_BYTES", 10**9)
    monkeypatch.setattr(unpack, "MAX_TOTAL_BYTES", 20)
    assert code_of(path, manifest, layout) == "too_big"
    monkeypatch.setattr(unpack, "MAX_TOTAL_BYTES", 10**12)
    monkeypatch.setattr(unpack, "MAX_ENTRIES", 2)
    assert code_of(path, manifest, layout) == "bad_zip"


def test_a_compression_bomb_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    files = {"pythonw.exe": b"p", "bomb.bin": b"\x00" * (12 * 1024 * 1024)}
    release = build_release("0.0.2", KEYS, files)
    manifest = parse_manifest(release.manifest_bytes)
    layout = InstallLayout(tmp_path / "root")
    assert code_of(write_zip(tmp_path, release.zip_bytes), manifest, layout) == "ratio"


def test_a_header_that_lies_about_the_size_is_caught_while_extracting(tmp_path: Path) -> None:
    release = build_release("0.0.2", KEYS)
    manifest = parse_manifest(release.manifest_bytes)
    layout = InstallLayout(tmp_path / "root")
    data = bytearray(release.zip_bytes)
    # make the first entry's central-directory uncompressed size smaller than the real data
    index = bytes(data).index(b"PK\x01\x02")
    data[index + 24 : index + 28] = (1).to_bytes(4, "little")
    code = code_of(write_zip(tmp_path, bytes(data)), manifest, layout)
    assert code in ("mismatch", "too_big", "bad_zip")


def test_a_leftover_incoming_folder_is_replaced_and_its_links_are_not_followed(tmp_path: Path) -> None:
    manifest, data, layout = prepare(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "precious.txt").write_text("keep me", encoding="utf-8")
    leftover = layout.incoming_dir("0.0.2")
    leftover.mkdir(parents=True)
    (leftover / "junk.bin").write_bytes(b"old")
    make_dir_link(leftover / "planted", outside)
    other = layout.versions / ".incoming-9.9.9"
    other.mkdir()
    unpack_release(write_zip(tmp_path, data), manifest, layout)
    assert (outside / "precious.txt").read_text(encoding="utf-8") == "keep me"
    assert not layout.incoming_dir("0.0.2").exists() and not other.exists()
    assert layout.version_dir("0.0.2").is_dir()


def test_leftovers_are_removed_at_start_without_following_a_planted_link(tmp_path: Path) -> None:
    layout = InstallLayout(tmp_path / "root")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "precious.txt").write_text("keep me", encoding="utf-8")
    incoming = layout.versions / ".incoming-0.0.3"
    incoming.mkdir(parents=True)
    make_dir_link(incoming / "planted", outside)
    keep = layout.versions / "0.0.1"
    keep.mkdir()
    remove_incoming_leftovers(layout)
    assert not incoming.exists() and keep.is_dir()
    assert (outside / "precious.txt").read_text(encoding="utf-8") == "keep me"
    remove_incoming_leftovers(InstallLayout(tmp_path / "no-root"))  # nothing there: nothing to do


def test_an_earlier_download_of_the_same_version_is_replaced(tmp_path: Path) -> None:
    manifest, data, layout = prepare(tmp_path)
    old = layout.version_dir("0.0.2")
    old.mkdir(parents=True)
    (old / "stale.txt").write_text("old", encoding="utf-8")
    unpack_release(write_zip(tmp_path, data), manifest, layout)
    assert not (old / "stale.txt").exists()


# ---- verify_tree ---------------------------------------------------------------------------------------------------


def unpacked(tmp_path: Path) -> tuple[Manifest, Path]:
    manifest, data, layout = prepare(tmp_path)
    return manifest, unpack_release(write_zip(tmp_path, data), manifest, layout)


def test_a_changed_file_is_found(tmp_path: Path) -> None:
    manifest, folder = unpacked(tmp_path)
    (folder / "python.exe").write_bytes(b"x" * (folder / "python.exe").stat().st_size)
    with pytest.raises(UnpackError):
        verify_tree(folder, manifest)


def test_an_added_or_removed_file_is_found(tmp_path: Path) -> None:
    manifest, folder = unpacked(tmp_path)
    (folder / "shelfsync" / "extra.py").write_text("x", encoding="utf-8")
    with pytest.raises(UnpackError):
        verify_tree(folder, manifest)
    (folder / "shelfsync" / "extra.py").unlink()
    verify_tree(folder, manifest)
    (folder / "python.exe").unlink()
    with pytest.raises(UnpackError):
        verify_tree(folder, manifest)


def test_a_link_inside_the_folder_is_refused(tmp_path: Path) -> None:
    manifest, folder = unpacked(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    make_dir_link(folder / "planted", outside)
    with pytest.raises(UnpackError):
        verify_tree(folder, manifest)


def test_a_folder_that_is_a_link_or_missing_is_refused(tmp_path: Path) -> None:
    manifest, folder = unpacked(tmp_path)
    link = tmp_path / "link"
    make_dir_link(link, folder)
    with pytest.raises(UnpackError):
        verify_tree(link, manifest)
    with pytest.raises(UnpackError):
        verify_tree(tmp_path / "missing", manifest)


def test_empty_folders_are_not_files_and_do_not_matter(tmp_path: Path) -> None:
    manifest, folder = unpacked(tmp_path)
    (folder / "empty").mkdir()
    verify_tree(folder, manifest)


def test_the_file_entries_type_is_checked_by_the_manifest_helpers() -> None:
    assert entries({"a": b"x"})["a"] == FileEntry(1, entries({"a": b"x"})["a"].sha256)
