"""Helpers for the updater tests: throwaway keys made in the test, signed releases built in memory, a fake GitHub
(`httpx.MockTransport`), and fakes for links, processes, the lock and the health check. Nothing here touches the real
registry, Credential Manager, a real junction, GitHub or the network."""

import hashlib
import io
import json
import os
import sys
import zipfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from shelfsync.paths import DataPaths
from shelfsync.platform.junction import LinkError, WindowsJunctions
from shelfsync.update import release_key
from shelfsync.update.github import REPO
from shelfsync.update.layout import InstallLayout
from shelfsync.update.manifest import (
    FileEntry,
    Manifest,
    make_manifest,
    parse_manifest,
    setup_asset_name,
    zip_asset_name,
)

COMMIT = "a" * 40
BUILT_AT = "2026-10-27T10:00:00Z"


@dataclass(frozen=True)
class Keys:
    private: Ed25519PrivateKey

    @property
    def public(self) -> bytes:
        return self.private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)

    def sign(self, data: bytes) -> bytes:
        return self.private.sign(data)


def make_keys(seed: int = 1) -> Keys:
    return Keys(Ed25519PrivateKey.from_private_bytes(bytes([seed]) * 32))


def use_key(monkeypatch: pytest.MonkeyPatch, keys: Keys | None) -> None:
    """Patch the module constant: the one place verification reads (06 section 6)."""
    monkeypatch.setattr(release_key, "PUBLIC_KEY", keys.public if keys is not None else None)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def entries(files: Mapping[str, bytes]) -> dict[str, FileEntry]:
    return {name: FileEntry(len(data), sha(data)) for name, data in files.items()}


@dataclass
class Release:
    version: str
    files: dict[str, bytes]
    manifest_bytes: bytes
    signature: bytes
    zip_bytes: bytes
    setup_bytes: bytes
    manifest: Manifest

    @property
    def tag(self) -> str:
        return f"v{self.version}"


def make_zip(files: Mapping[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def default_files(version: str) -> dict[str, bytes]:
    return {
        "pythonw.exe": b"pythonw " + version.encode(),
        "python.exe": b"python " + version.encode(),
        "shelfsync/__init__.py": f'__version__ = "{version}"\n'.encode(),
        "ui/index.html": b"<!doctype html>",
    }


def build_release(
    version: str, keys: Keys, files: dict[str, bytes] | None = None, schema: int = 1, sign: bool = True
) -> Release:
    content = files if files is not None else default_files(version)
    archive = make_zip(content)
    setup = b"setup " + version.encode()
    manifest_bytes = make_manifest(
        version=version,
        source_commit=COMMIT,
        built_at=BUILT_AT,
        schema_version=schema,
        assets={
            setup_asset_name(version): FileEntry(len(setup), sha(setup)),
            zip_asset_name(version): FileEntry(len(archive), sha(archive)),
        },
        files=entries(content),
    )
    signature = keys.sign(manifest_bytes) if sign else b"\x00" * 64
    return Release(version, content, manifest_bytes, signature, archive, setup, parse_manifest(manifest_bytes))


# ---- a fake GitHub ---------------------------------------------------------------------------------------------------


@dataclass
class FakeGitHub:
    """Serves `releases/latest`, `releases/tags/<tag>`, the repository, and assets (through a 302 to the asset host,
    like GitHub). `requests` records (method, host, path, has_authorization) for every request."""

    releases: dict[str, Release] = field(default_factory=dict)
    latest_tag: str | None = None
    latest_status: int | None = None
    latest_headers: dict[str, str] = field(default_factory=dict)
    repo_status: int = 200
    repo_headers: dict[str, str] = field(default_factory=dict)
    redirect: bool = True
    asset_override: dict[int, Callable[[httpx.Request], httpx.Response]] = field(default_factory=dict)
    requests: list[tuple[str, str, str, bool]] = field(default_factory=list)
    raise_error: Exception | None = None

    def _assets(self) -> dict[int, tuple[str, bytes]]:
        table: dict[int, tuple[str, bytes]] = {}
        for index, release in enumerate(self.releases.values()):
            base = (index + 1) * 10
            table[base] = ("manifest.json", release.manifest_bytes)
            table[base + 1] = ("manifest.json.sig", release.signature)
            table[base + 2] = (zip_asset_name(release.version), release.zip_bytes)
            table[base + 3] = (setup_asset_name(release.version), release.setup_bytes)
        return table

    def asset_id(self, version: str, name: str) -> int:
        for asset_id, (asset_name, _) in self._assets().items():
            owner = list(self.releases.values())[asset_id // 10 - 1]
            if owner.version == version and asset_name == name:
                return asset_id
        raise KeyError(name)

    def _release_json(self, release: Release) -> dict[str, object]:
        assets = []
        for asset_id, (name, data) in self._assets().items():
            owner = list(self.releases.values())[asset_id // 10 - 1]
            if owner.version == release.version:
                assets.append({"name": name, "id": asset_id, "size": len(data), "state": "uploaded"})
        return {"tag_name": release.tag, "assets": assets}

    def handler(self, request: httpx.Request) -> httpx.Response:
        host, path = request.url.host, request.url.path
        self.requests.append((request.method, host, path, "authorization" in request.headers))
        if self.raise_error is not None:
            raise self.raise_error
        base = f"/repos/{REPO}"
        if host == "api.github.com" and path == f"{base}/releases/latest":
            if self.latest_status is not None:
                return httpx.Response(self.latest_status, headers=self.latest_headers, json={"message": "x"})
            if self.latest_tag is None:
                return httpx.Response(404, headers=self.latest_headers, json={"message": "Not Found"})
            return httpx.Response(
                200, headers=self.latest_headers, json=self._release_json(self.releases[self.latest_tag])
            )
        if host == "api.github.com" and path.startswith(f"{base}/releases/tags/"):
            tag = path.rsplit("/", 1)[1]
            if tag in self.releases:
                return httpx.Response(200, headers=self.latest_headers, json=self._release_json(self.releases[tag]))
            return httpx.Response(404, json={"message": "Not Found"})
        if host == "api.github.com" and path == base:
            return httpx.Response(self.repo_status, headers=self.repo_headers, json={"full_name": REPO})
        if host == "api.github.com" and path.startswith(f"{base}/releases/assets/"):
            asset_id = int(path.rsplit("/", 1)[1])
            if asset_id in self.asset_override:
                return self.asset_override[asset_id](request)
            if self.redirect:
                return httpx.Response(
                    302, headers={"location": f"https://release-assets.githubusercontent.com/a/{asset_id}?sig=abc123"}
                )
            return httpx.Response(200, content=self._assets()[asset_id][1])
        if host == "release-assets.githubusercontent.com" and path.startswith("/a/"):
            return httpx.Response(200, content=self._assets()[int(path.rsplit("/", 1)[1])][1])
        return httpx.Response(404)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)


# ---- the install layout on disk, with fakes for links, processes, lock, health -----------------------------------


def make_install(
    root: Path, keys: Keys, versions: Mapping[str, dict[str, bytes] | None], *, schema: int = 1
) -> dict[str, Release]:
    """Version folders with their files and kept, signed manifests. `None` means the default files for that version."""
    layout = InstallLayout(root)
    built: dict[str, Release] = {}
    for version, files in versions.items():
        release = build_release(version, keys, files, schema=schema)
        built[version] = release
        folder = layout.version_dir(version)
        for name, data in release.files.items():
            target = folder.joinpath(*name.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        layout.manifests.mkdir(parents=True, exist_ok=True)
        layout.manifest_path(version).write_bytes(release.manifest_bytes)
        layout.signature_path(version).write_bytes(release.signature)
    return built


class FakeLinks:
    """Directory links in memory. `fail_at=n` makes the n-th changing call (create, rename, remove) raise LinkError."""

    def __init__(self, fail_at: int | None = None) -> None:
        self.table: dict[str, Path] = {}
        self.fail_at = fail_at
        self.calls = 0
        self.log: list[str] = []

    @staticmethod
    def _key(path: Path) -> str:
        return str(path)

    def _tick(self, what: str) -> None:
        self.calls += 1
        self.log.append(what)
        if self.fail_at is not None and self.calls == self.fail_at:
            raise LinkError(f"injected failure at {what}")

    def create(self, link: Path, target: Path) -> None:
        self._tick("create")
        assert target.is_dir(), target
        assert self._key(link) not in self.table
        self.table[self._key(link)] = target

    def exists(self, path: Path) -> bool:
        return self._key(path) in self.table

    def target(self, link: Path) -> Path | None:
        return self.table.get(self._key(link))

    def rename(self, source: Path, destination: Path) -> None:
        self._tick("rename")
        if self._key(source) not in self.table or self._key(destination) in self.table:
            raise LinkError("rename refused")
        self.table[self._key(destination)] = self.table.pop(self._key(source))

    def remove(self, link: Path) -> None:
        self._tick("remove")
        if self._key(link) not in self.table:
            raise LinkError("not a link")
        del self.table[self._key(link)]


class FakeProc:
    _next_pid = 5000

    def __init__(self, exit_code: int | None = None) -> None:
        FakeProc._next_pid += 1
        self._pid = FakeProc._next_pid
        self.exit_code = exit_code
        self.terminated = False
        self.killed = False

    @property
    def pid(self) -> int:
        return self._pid

    def poll(self) -> int | None:
        return self.exit_code

    def terminate(self) -> None:
        self.terminated = True
        if self.exit_code is None:
            self.exit_code = 1

    def kill(self) -> None:
        self.killed = True
        if self.exit_code is None:
            self.exit_code = 1

    def wait(self, timeout: float) -> int | None:
        return self.exit_code


class FakeWatch:
    """A handle on a process that is still in `running`; `closed` records that it was released."""

    def __init__(self, processes: FakeProcesses, pid: int, image: str | None) -> None:
        self._processes = processes
        self._pid = pid
        self.image = image
        self.closed = False

    def is_running(self) -> bool:
        return self._pid in self._processes.running

    def close(self) -> None:
        self.closed = True


@dataclass
class FakeProcesses:
    """Spawned programs are recorded; `on_spawn(argv, cwd)` decides what each one does (default: runs for ever)."""

    running: set[int] = field(default_factory=set)
    images: dict[int, str] = field(default_factory=dict)  # the program file each running PID shows
    watches: list[FakeWatch] = field(default_factory=list)
    spawned: list[tuple[list[str], Path, FakeProc]] = field(default_factory=list)
    on_spawn: Callable[[list[str], Path], FakeProc] = lambda argv, cwd: FakeProc()
    terminated_pids: list[int] = field(default_factory=list)

    def is_running(self, pid: int) -> bool:
        return pid in self.running

    def watch(self, pid: int) -> FakeWatch | None:
        if pid not in self.running:
            return None  # no such process: it has already gone
        handle = FakeWatch(self, pid, self.images.get(pid))
        self.watches.append(handle)
        return handle

    def spawn_detached(self, argv: Sequence[str], cwd: Path, env: Mapping[str, str] | None = None) -> FakeProc:
        arguments = list(argv)
        proc = self.on_spawn(arguments, cwd)
        self.spawned.append((arguments, cwd, proc))
        return proc

    def terminate_pid(self, pid: int) -> None:
        self.terminated_pids.append(pid)
        self.running.discard(pid)


class FakeLock:
    def __init__(self, busy_for: int = 0) -> None:
        self.busy_for = busy_for  # the first n acquire calls fail
        self.held = False
        self.acquired = 0
        self.released = 0

    def acquire(self) -> bool:
        if self.busy_for > 0:
            self.busy_for -= 1
            return False
        self.held = True
        self.acquired += 1
        return True

    def release(self) -> None:
        self.held = False
        self.released += 1


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def data_paths(tmp_path: Path) -> DataPaths:
    paths = DataPaths(tmp_path / "data")
    for folder in (paths.root, paths.logs, paths.backups, paths.tmp):
        folder.mkdir(parents=True, exist_ok=True)
    return paths


def json_of(data: bytes) -> dict[str, object]:
    loaded = json.loads(data)
    assert isinstance(loaded, dict)
    return loaded


def make_dir_link(link: Path, target: Path) -> None:
    """A directory link the way this system makes one (a junction on Windows needs no right; a symlink may)."""
    if sys.platform == "win32":
        WindowsJunctions().create(link, target)
        return
    os.symlink(target, link, target_is_directory=True)
