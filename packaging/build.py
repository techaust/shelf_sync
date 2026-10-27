"""Build the installable folder: `python -I packaging/build.py [--tag vX.Y.Z]` (04 section 8, SYS-01).

Writes `build/ShelfSync-<version>/` (what the installer puts in `versions\\<version>\\`) and
`build/shelfsync-<version>-win64.zip` (the same files, no top-level folder, for the updater) and
`build/files.txt` (one `path<TAB>size<TAB>sha256` line per file, sorted, for the release manifest). Steps:

1. the version comes from pyproject.toml and must equal `shelfsync.__version__` and, in CI, the tag;
2. the Python 3.14 embeddable package is downloaded (or taken from `--embed-zip`) and refused unless its SHA-256 is the
   pinned one; every `.exe`, `.dll` and `.pyd` in it must carry a valid signature from a known publisher (V12);
3. `python314._pth` is written from a template (the embeddable package's own is replaced);
4. the locked run-time wheels are installed into `Lib/site-packages` from `uv export --locked --no-dev` with hashes
   required, binary wheels only, for win_amd64 and CPython 3.14 (the wheels' own DLLs aren't signed by their projects,
   04 section 8's honest note);
5. `backend/shelfsync`, the built UI (`frontend/dist`, as `ui/`) and `brand/assets/app/shelfsync.ico` are copied in;
6. everything is precompiled with `--invalidation-mode checked-hash`, so a first start writes nothing into the folder
   (V47).

Nothing here reads a secret, and nothing is signed. Run it with `UV_PYTHON_DOWNLOADS=never` set.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess  # nosec B404 - runs uv, the embedded python and PowerShell with fixed argument lists
import sys
import tomllib
import urllib.request
import zipfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

REPO = Path(__file__).resolve().parents[1]

PYTHON_VERSION = "3.14.8"
PYTHON_TAG = "314"  # python314._pth, python314.zip
EMBED_NAME = f"python-{PYTHON_VERSION}-embed-amd64.zip"
EMBED_URL = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/{EMBED_NAME}"
EMBED_SHA256 = "a93abe456ab01bd96d7a085b3cdb6566b3063f4241360d114142fbdb07f0a310"  # 04 section 2.1

# Signers accepted on the files of the embeddable package: Python's own, and Microsoft's for the VC++ runtime DLLs.
TRUSTED_SIGNERS = ("Python Software Foundation", "Microsoft Corporation")
SIGNED_SUFFIXES = (".exe", ".dll", ".pyd")

PTH_TEMPLATE = "python{tag}.zip\n.\nLib\\site-packages\nimport site\n"

_VERSION = re.compile(r"^\d+\.\d+\.\d+$")


class BuildError(Exception):
    """A build step refused to go on. The message says what to fix."""


# ---- pure parts (tested) ------------------------------------------------------------------------------------------


def read_version(pyproject: Path) -> str:
    """The project version, strictly X.Y.Z."""
    with pyproject.open("rb") as handle:
        version = tomllib.load(handle)["project"]["version"]
    if not isinstance(version, str) or not _VERSION.fullmatch(version):
        raise BuildError(f"The version {version!r} in {pyproject.name} isn't X.Y.Z")
    return version


def read_package_version(init_file: Path) -> str:
    """`__version__` from the package's `__init__.py`, read as text (the package isn't imported)."""
    found = re.search(r'^__version__\s*=\s*"([^"]+)"', init_file.read_text(encoding="utf-8"), re.MULTILINE)
    if found is None:
        raise BuildError(f"No __version__ in {init_file}")
    return found.group(1)


def check_versions(project: str, package: str, tag: str | None) -> None:
    """pyproject.toml, `shelfsync.__version__` and (in CI) the tag `v<version>` must all agree."""
    if project != package:
        raise BuildError(f"pyproject.toml says {project} but shelfsync.__version__ says {package}")
    if tag is not None and tag != f"v{project}":
        raise BuildError(f"The tag {tag} doesn't match the version {project} (expected v{project})")


def pth_text(tag: str = PYTHON_TAG) -> str:
    """`python314._pth`: the stdlib zip, the folder itself (where `shelfsync` sits), the wheels, and `site`."""
    return PTH_TEMPLATE.format(tag=tag)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_sha256(path: Path, expected: str) -> None:
    """Refuse a file whose SHA-256 isn't the pinned one."""
    actual = sha256_of(path)
    if actual != expected:
        raise BuildError(f"{path.name} has SHA-256 {actual}, not the pinned {expected}; it was not used")


@dataclass(frozen=True)
class FileEntry:
    path: str  # relative, forward slashes
    size: int
    sha256: str


def file_listing(root: Path) -> list[FileEntry]:
    """Every file under `root`, sorted by path. A link of any kind is an error: the tree must be plain files."""
    entries: list[FileEntry] = []
    for folder, directories, names in os.walk(root, followlinks=False):
        for name in [*directories, *names]:
            candidate = Path(folder, name)
            if candidate.is_symlink() or os.path.isjunction(candidate):
                raise BuildError(f"{candidate} is a link; the build folder must hold plain files only")
        for name in names:
            file = Path(folder, name)
            entries.append(FileEntry(file.relative_to(root).as_posix(), file.stat().st_size, sha256_of(file)))
    return sorted(entries, key=lambda entry: entry.path)


def format_files_txt(entries: Iterable[FileEntry]) -> str:
    """One `path<TAB>size<TAB>sha256` line per file, LF line ends, sorted by path."""
    return "".join(f"{entry.path}\t{entry.size}\t{entry.sha256}\n" for entry in sorted(entries, key=lambda e: e.path))


def parse_files_txt(text: str) -> list[FileEntry]:
    entries = []
    for line in text.splitlines():
        path, size, digest = line.split("\t")
        entries.append(FileEntry(path, int(size), digest))
    return entries


def check_signatures(records: Sequence[dict[str, str | None]], expected_files: Iterable[str]) -> None:
    """`records` is what PowerShell's Get-AuthenticodeSignature reported: Path, Status and the signer's Subject. Every
    file in `expected_files` must be Valid and signed by a trusted publisher."""
    seen = {str(record["Path"]).replace("\\", "/").lower(): record for record in records}
    for relative in expected_files:
        found = next((r for key, r in seen.items() if key.endswith("/" + relative.lower())), None)
        if found is None:
            raise BuildError(f"No signature check result for {relative}")
        if found.get("Status") != "Valid":
            raise BuildError(f"{relative}: signature is {found.get('Status')}, not Valid")
        subject = found.get("Subject") or ""
        if not any(f"O={signer}" in subject or f"CN={signer}" in subject for signer in TRUSTED_SIGNERS):
            raise BuildError(f"{relative}: signed by an unexpected publisher ({subject})")


def safe_extract(archive: zipfile.ZipFile, destination: Path) -> None:
    """Extract, refusing any entry that would land outside `destination` or isn't a plain relative path."""
    root = destination.resolve()
    for info in archive.infolist():
        name = PurePosixPath(info.filename.replace("\\", "/"))
        if name.is_absolute() or ".." in name.parts or (name.parts and ":" in name.parts[0]):
            raise BuildError(f"The archive has an unsafe entry: {info.filename}")
        target = (root / Path(*name.parts)).resolve()
        if root != target and root not in target.parents:
            raise BuildError(f"The archive has an unsafe entry: {info.filename}")
    archive.extractall(root)  # every entry was checked above


def write_zip(folder: Path, entries: Iterable[FileEntry], destination: Path) -> None:
    """Zip the listed files (no top-level folder), sorted, so the same tree gives the same entry order."""
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for entry in sorted(entries, key=lambda e: e.path):
            archive.write(folder / entry.path, entry.path)


# ---- steps that touch the PC (exercised by the local build and release.yml) ---------------------------------------


def download_embed_zip(cache: Path) -> Path:
    """The embeddable zip in `cache`, downloaded from python.org if it isn't there; always hash-checked."""
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / EMBED_NAME
    if not target.is_file():
        if not EMBED_URL.startswith("https://www.python.org/"):  # defence in depth: the URL is a constant
            raise BuildError("Refusing a download from anywhere but python.org")
        partial = target.with_suffix(".part")
        with urllib.request.urlopen(EMBED_URL, timeout=120) as response, partial.open("wb") as out:  # nosec B310
            shutil.copyfileobj(response, out)
        partial.replace(target)
    try:
        verify_sha256(target, EMBED_SHA256)
    except BuildError:
        target.unlink(missing_ok=True)  # never keep a file that isn't the pinned one
        raise
    return target


def powershell_signatures(folder: Path) -> list[dict[str, str | None]]:
    """Get-AuthenticodeSignature for every .exe, .dll and .pyd under `folder` (Windows only)."""
    script = (
        "$ErrorActionPreference='Stop'; "
        "Get-ChildItem -LiteralPath $env:SHELFSYNC_BUILD_FOLDER -Recurse -File "
        "| Where-Object { $_.Extension -in '.exe','.dll','.pyd' } "
        "| Get-AuthenticodeSignature | ForEach-Object { [pscustomobject]@{ Path=$_.Path; Status=[string]$_.Status; "
        "Subject=$_.SignerCertificate.Subject } } | ConvertTo-Json -Compress"
    )
    done = subprocess.run(  # nosec B603 B607
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        check=True,
        timeout=600,
        env={**os.environ, "SHELFSYNC_BUILD_FOLDER": str(folder)},
    )
    data = json.loads(done.stdout or "[]")
    return [data] if isinstance(data, dict) else data


def check_embedded_signatures(folder: Path) -> None:
    expected = [
        file.relative_to(folder).as_posix()
        for file in folder.rglob("*")
        if file.is_file() and file.suffix.lower() in SIGNED_SUFFIXES
    ]
    if sys.platform != "win32":
        print(f"Signature check skipped: not Windows ({len(expected)} files not checked)")  # noqa: T201
        return
    check_signatures(powershell_signatures(folder), expected)
    print(f"Signatures valid on {len(expected)} files of the embeddable package")  # noqa: T201


def install_wheels(site_packages: Path, work: Path) -> None:
    """The locked run-time packages, with hashes required, binary wheels only, for Windows and CPython 3.14."""
    requirements = work / "requirements.txt"
    run(["uv", "export", "--locked", "--no-dev", "--no-emit-project", "--format", "requirements-txt",
         "--output-file", str(requirements)])  # fmt: skip
    run(["uv", "pip", "install", "--target", str(site_packages), "--require-hashes", "--only-binary", ":all:",
         "--no-deps", "--python-platform", "windows", "--python-version", "3.14", "--no-compile-bytecode",
         "--no-installer-metadata", "-r", str(requirements)])  # fmt: skip


def run(command: list[str], cwd: Path = REPO) -> None:
    print("+", " ".join(command))  # noqa: T201
    subprocess.run(command, cwd=cwd, check=True)  # nosec B603 B607 - fixed argument lists, no shell


def precompile(folder: Path) -> None:
    """Precompile with the embedded python, checked-hash pycs: a first start then writes nothing here (V47)."""
    python = folder / "python.exe"
    run([str(python), "-m", "compileall", "-q", "-f", "--invalidation-mode", "checked-hash", "shelfsync",
         "Lib/site-packages"], cwd=folder)  # fmt: skip


def copy_tree(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def build(out: Path, tag: str | None, embed_zip: Path | None) -> Path:
    version = read_version(REPO / "pyproject.toml")
    check_versions(version, read_package_version(REPO / "backend" / "shelfsync" / "__init__.py"), tag)
    ui = REPO / "frontend" / "dist"
    if not (ui / "index.html").is_file():
        raise BuildError("frontend/dist/index.html is missing: run `npm ci` and `npm run build` in frontend/ first")
    icon = REPO / "brand" / "assets" / "app" / "shelfsync.ico"
    if not icon.is_file():
        raise BuildError(f"{icon} is missing")

    folder = out / f"ShelfSync-{version}"
    if out.exists():
        if out.name != "build" and any(out.iterdir()):
            raise BuildError(f"{out} isn't named 'build' and isn't empty; it was not cleared")
        shutil.rmtree(out)  # a rebuild starts clean
    folder.mkdir(parents=True)
    work = out / "work"
    work.mkdir()

    if embed_zip is not None:
        verify_sha256(embed_zip, EMBED_SHA256)
        archive_path = embed_zip
    else:
        archive_path = download_embed_zip(REPO / "build-cache")
    with zipfile.ZipFile(archive_path) as archive:
        safe_extract(archive, folder)
    check_embedded_signatures(folder)

    (folder / f"python{PYTHON_TAG}._pth").write_text(pth_text(), encoding="ascii", newline="\n")
    site_packages = folder / "Lib" / "site-packages"
    site_packages.mkdir(parents=True)
    install_wheels(site_packages, work)

    copy_tree(REPO / "backend" / "shelfsync", folder / "shelfsync")
    copy_tree(ui, folder / "ui")
    shutil.copy2(icon, folder / "shelfsync.ico")

    precompile(folder)
    shutil.rmtree(work)

    entries = file_listing(folder)
    (out / "files.txt").write_text(format_files_txt(entries), encoding="utf-8", newline="\n")
    write_zip(folder, entries, out / f"shelfsync-{version}-win64.zip")
    print(f"Built {folder} ({len(entries)} files)")  # noqa: T201
    return folder


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the ShelfSync folder, zip and files.txt")
    parser.add_argument("--out", type=Path, default=REPO / "build", help="output folder (default: build/)")
    parser.add_argument("--tag", help="the release tag; must equal v<version> (CI passes it)")
    parser.add_argument("--embed-zip", type=Path, help="a local copy of the embeddable zip (still hash-checked)")
    arguments = parser.parse_args(argv)
    try:
        build(arguments.out.resolve(), arguments.tag, arguments.embed_zip)
    except (BuildError, subprocess.CalledProcessError, OSError) as error:
        print(f"Build failed: {error}", file=sys.stderr)  # noqa: T201
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
