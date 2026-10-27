"""SYS-01: the pure parts of packaging/build.py: the `_pth` text, files.txt, the version check, the pinned hash, the
signature check and the safe extraction. (The download, uv and compileall steps run in the local build and in
release.yml.) The script is loaded by path: a folder named `packaging` would clash with PyPI's `packaging`."""

import hashlib
import importlib.util
import io
import zipfile
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[1]


def load_build() -> ModuleType:
    spec = importlib.util.spec_from_file_location("shelfsync_packaging_build", REPO / "packaging" / "build.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build = load_build()


def test_the_pth_names_the_stdlib_zip_the_folder_the_wheels_and_site() -> None:
    """SYS-01, V11: `.` is the folder holding `shelfsync`; no `#` lines, no PYTHONPATH."""
    assert build.pth_text() == "python314.zip\n.\nLib\\site-packages\nimport site\n"


def test_the_pinned_embed_hash_is_the_one_in_04() -> None:
    """SYS-01: 04 section 2.1 and this script must agree."""
    text = (REPO / "docs" / "04-architecture.md").read_text(encoding="utf-8")
    assert build.EMBED_SHA256 in text
    assert build.EMBED_URL.endswith("python-3.14.8-embed-amd64.zip")
    assert (REPO / ".python-version").read_text(encoding="utf-8").strip() == build.PYTHON_VERSION


def test_the_version_comes_from_pyproject_and_matches_the_package() -> None:
    """SYS-01."""
    project = build.read_version(REPO / "pyproject.toml")
    package = build.read_package_version(REPO / "backend" / "shelfsync" / "__init__.py")
    assert project == package
    build.check_versions(project, package, f"v{project}")
    build.check_versions(project, package, None)


@pytest.mark.parametrize("tag", ["v9.9.9", "0.1.0", "v0.1.0-rc1", ""])
def test_a_tag_that_isnt_v_plus_the_version_is_refused(tag: str) -> None:
    """SYS-01: the version must equal the tag in CI."""
    with pytest.raises(build.BuildError):
        build.check_versions("0.1.0", "0.1.0", tag)


def test_a_package_version_that_differs_from_pyproject_is_refused() -> None:
    """SYS-01."""
    with pytest.raises(build.BuildError):
        build.check_versions("0.1.1", "0.1.0", None)


@pytest.mark.parametrize("bad", ["1.2", "1.2.3.4", "v1.2.3", "1.2.3rc1", "01.x.3"])
def test_a_version_that_isnt_strict_x_y_z_is_refused(tmp_path: Path, bad: str) -> None:
    """SYS-01: the same strictness the updater uses."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(f'[project]\nname = "x"\nversion = "{bad}"\n', encoding="utf-8")
    with pytest.raises(build.BuildError):
        build.read_version(pyproject)


def test_a_wrong_hash_is_refused_and_the_right_one_accepted(tmp_path: Path) -> None:
    """SYS-01: nothing else is ever used."""
    file = tmp_path / "embed.zip"
    file.write_bytes(b"not python")
    with pytest.raises(build.BuildError, match="not the pinned"):
        build.verify_sha256(file, build.EMBED_SHA256)
    build.verify_sha256(file, hashlib.sha256(b"not python").hexdigest())


def test_a_downloaded_file_with_a_wrong_hash_is_deleted(tmp_path: Path) -> None:
    """SYS-01: a cached file that isn't the pinned one is never kept for next time."""
    (tmp_path / build.EMBED_NAME).write_bytes(b"tampered")
    with pytest.raises(build.BuildError):
        build.download_embed_zip(tmp_path)
    assert not (tmp_path / build.EMBED_NAME).exists()


def make_tree(root: Path) -> None:
    (root / "shelfsync").mkdir(parents=True)
    (root / "shelfsync" / "b.py").write_bytes(b"print(1)\n")
    (root / "shelfsync" / "a.py").write_bytes(b"")
    (root / "python.exe").write_bytes(b"MZ")


def test_files_txt_lists_every_file_sorted_with_size_and_sha256(tmp_path: Path) -> None:
    """SYS-06 (for the manifest): `path<TAB>size<TAB>sha256`, forward slashes, LF, no `build/` prefix."""
    make_tree(tmp_path)
    entries = build.file_listing(tmp_path)
    text = build.format_files_txt(entries)
    assert [e.path for e in entries] == ["python.exe", "shelfsync/a.py", "shelfsync/b.py"]
    lines = text.splitlines()
    assert lines[1] == f"shelfsync/a.py\t0\t{hashlib.sha256(b'').hexdigest()}"
    assert lines[2] == f"shelfsync/b.py\t9\t{hashlib.sha256(b'print(1)\n').hexdigest()}"
    assert "\r" not in text and text.endswith("\n")
    assert build.parse_files_txt(text) == entries


def test_a_link_in_the_build_folder_is_refused(tmp_path: Path) -> None:
    """SYS-01: the tree must be plain files (the updater refuses links too)."""
    make_tree(tmp_path)
    try:
        (tmp_path / "link").symlink_to(tmp_path / "shelfsync", target_is_directory=True)
    except OSError:
        pytest.skip("this account can't make symlinks")
    with pytest.raises(build.BuildError, match="link"):
        build.file_listing(tmp_path)


def test_the_zip_holds_exactly_the_listed_files_with_no_top_folder(tmp_path: Path) -> None:
    """SYS-06: the zip's entries are the manifest's paths."""
    tree = tmp_path / "tree"
    make_tree(tree)
    entries = build.file_listing(tree)
    build.write_zip(tree, entries, tmp_path / "out.zip")
    with zipfile.ZipFile(tmp_path / "out.zip") as archive:
        assert archive.namelist() == [e.path for e in entries]


MICROSOFT = "CN=Microsoft Corporation, O=Microsoft Corporation"


def record(
    path: str,
    status: str = "Valid",
    subject: str | None = "CN=Python Software Foundation, O=Python Software Foundation",
) -> dict[str, str | None]:
    return {"Path": path, "Status": status, "Subject": subject}


def test_valid_signatures_from_a_trusted_publisher_pass() -> None:
    """SYS-01, V12."""
    build.check_signatures(
        [
            record(r"D:\b\ShelfSync-0.1.0\python.exe"),
            record(r"D:\b\ShelfSync-0.1.0\vcruntime140.dll", subject=MICROSOFT),
        ],
        ["python.exe", "vcruntime140.dll"],
    )


@pytest.mark.parametrize(
    "bad",
    [
        record(r"D:\b\python.exe", status="NotSigned", subject=None),
        record(r"D:\b\python.exe", status="HashMismatch"),
        record(r"D:\b\python.exe", subject="CN=Somebody Else"),
        record(r"D:\b\python.exe", subject="CN=Evil, O=Not Python Software Foundation Inc"),
        record(r"D:\b\python.exe", subject="CN=Python Software Foundation Fake, O=Evil"),
        record(r"D:\b\python.exe", subject="CN=Python Software Foundation; O=Python Software Foundation"),
    ],
)
def test_an_unsigned_altered_or_foreign_file_fails_the_check(bad: dict[str, str | None]) -> None:
    """SYS-01, V12."""
    with pytest.raises(build.BuildError):
        build.check_signatures([bad], ["python.exe"])


def test_a_file_with_no_result_fails_the_check() -> None:
    """SYS-01."""
    with pytest.raises(build.BuildError, match="No signature check result"):
        build.check_signatures([], ["python.exe"])


def zip_with(names: list[str]) -> zipfile.ZipFile:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name in names:
            archive.writestr(name, "x")
    return zipfile.ZipFile(buffer)


@pytest.mark.parametrize("name", ["../evil.txt", "a/../../evil.txt", "/abs.txt", "C:/evil.txt", "..\\evil.txt"])
def test_an_archive_entry_outside_the_folder_is_refused(tmp_path: Path, name: str) -> None:
    """SYS-01, 06 section 4: no zip-slip from the embeddable zip."""
    destination = tmp_path / "out"
    destination.mkdir()
    with pytest.raises(build.BuildError, match="unsafe"):
        build.safe_extract(zip_with(["ok.txt", name]), destination)
    assert not (tmp_path / "evil.txt").exists()


def test_a_plain_archive_is_extracted(tmp_path: Path) -> None:
    """SYS-01."""
    build.safe_extract(zip_with(["python.exe", "Lib/x.py"]), tmp_path)
    assert (tmp_path / "python.exe").exists() and (tmp_path / "Lib" / "x.py").exists()


def test_a_build_without_the_ui_stops_with_a_clear_message(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SYS-01: no half-built folder; run the UI build first."""
    monkeypatch.setattr(build, "REPO", tmp_path)
    (tmp_path / "backend" / "shelfsync").mkdir(parents=True)
    (tmp_path / "backend" / "shelfsync" / "__init__.py").write_text('__version__ = "0.1.0"\n', encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "0.1.0"\n', encoding="utf-8")
    with pytest.raises(build.BuildError, match=r"frontend/dist/index\.html"):
        build.build(tmp_path / "build", None, None)


def test_a_non_build_folder_that_has_files_is_never_cleared(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SYS-01: `--out` pointing at a folder with other things in it is refused, not emptied."""
    monkeypatch.setattr(build, "REPO", tmp_path)
    (tmp_path / "backend" / "shelfsync").mkdir(parents=True)
    (tmp_path / "backend" / "shelfsync" / "__init__.py").write_text('__version__ = "0.1.0"\n', encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "0.1.0"\n', encoding="utf-8")
    (tmp_path / "frontend" / "dist").mkdir(parents=True)
    (tmp_path / "frontend" / "dist" / "index.html").write_text("x", encoding="utf-8")
    (tmp_path / "brand" / "assets" / "app").mkdir(parents=True)
    (tmp_path / "brand" / "assets" / "app" / "shelfsync.ico").write_bytes(b"ico")
    (tmp_path / "brand" / "assets" / "tray").mkdir(parents=True)
    for name in build.TRAY_ICON_NAMES:
        (tmp_path / "brand" / "assets" / "tray" / name).write_bytes(b"ico")
    precious = tmp_path / "documents"
    precious.mkdir()
    (precious / "keep.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(build.BuildError, match="was not cleared"):
        build.build(precious, None, None)
    assert (precious / "keep.txt").exists()


def test_a_subject_is_read_attribute_by_attribute_not_as_text() -> None:
    """SYS-01: exact values; a quoted value with a comma is one value."""
    fields = build.subject_fields('CN="Python Software Foundation, Inc.", O=Python Software Foundation, L=Beaverton')
    assert fields == {"CN": "Python Software Foundation, Inc.", "O": "Python Software Foundation", "L": "Beaverton"}


@pytest.mark.parametrize(
    "subject",
    [
        "CN=Python Software Foundation, garbage",
        'CN="Python Software Foundation, O=x',
        "O=Python Software Foundation,, CN=x",
        "=Python Software Foundation",
    ],
)
def test_a_subject_that_doesnt_parse_completely_is_refused(subject: str) -> None:
    """SYS-01: no half-read subject is ever matched against the trusted signers."""
    with pytest.raises(build.BuildError):
        build.subject_fields(subject)
    with pytest.raises(build.BuildError):
        build.check_signatures([record(r"D:\python.exe", subject=subject)], ["python.exe"])


def test_real_looking_subjects_parse_fully() -> None:
    """SYS-01: the usual shapes, with extra attributes and an OID attribute."""
    psf = "CN=Python Software Foundation, O=Python Software Foundation, L=Beaverton, S=Oregon, C=US"
    assert build.subject_fields(psf)["O"] == "Python Software Foundation"
    ms = "CN=Microsoft Corporation, O=Microsoft Corporation, L=Redmond, OID.1.3.6.1.4.1.311.60.2.1.3=US, C=US"
    assert build.subject_fields(ms)["CN"] == "Microsoft Corporation"
    assert build.subject_fields("") == {}


def test_the_signature_check_drops_psmodulepath_and_reports_powershells_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SYS-01: on GitHub's `shell: pwsh` steps Windows PowerShell inherits PowerShell 7's PSModulePath (release.yml's
    first run failed there with no message); the child gets no PSModulePath, and a failure names PowerShell's error."""
    import subprocess

    seen: dict[str, dict[str, str]] = {}

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        env = kwargs["env"]
        assert isinstance(env, dict)
        seen["env"] = env
        return subprocess.CompletedProcess(args, 1, "", "Get-AuthenticodeSignature: the module could not be loaded")

    monkeypatch.setenv("PSModulePath", r"C:\Program Files\PowerShell\7\Modules")
    monkeypatch.setattr(build.subprocess, "run", fake_run)
    with pytest.raises(build.BuildError, match="module could not be loaded"):
        build.powershell_signatures(tmp_path)
    assert not any(key.upper() == "PSMODULEPATH" for key in seen["env"])
    assert seen["env"]["SHELFSYNC_BUILD_FOLDER"] == str(tmp_path)
