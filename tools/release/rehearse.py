"""A local rehearsal of the updater (SYS-06, SYS-07) against a release build, with THROWAWAY roots, keys, names and
Credential Manager service. Run by a developer on Windows, from the repository root. It never contacts GitHub, a store
or S3, and never changes the real data folder, install folder, Run value, uninstall key or AUMID: it reads them (never
printing a value) before and after the run and checks they are the same. The real Credential Manager service is never
read at all: it is proven unreachable instead (no module of the build but `platform/secrets.py` talks to Credential
Manager, and each copy's own Python reports the throwaway service as both its service and the store's default).

    PYTHONPATH=backend uv run python tools/release/rehearse.py --base <build\\ShelfSync-<v>> --work <new empty folder>

`--base` is the embedded build folder `packaging/build.py` makes (`packaging/release-build.ps1 ... -Suffix -rehearsal`
leaves it in `build\\ShelfSync-<v>`). It is only COPIED, never changed, and it is run as built: nothing from this
checkout is copied into it (a note says when the checkout's code differs from the build's). Each fake version folder
is a copy of it, changed in the copy only, for the rehearsal:
  * `__version__` (the fake version) and the release public key (a key made here, in memory);
  * the schedule: the first update check is pushed out so nothing ever asks GitHub;
  * the Credential Manager service and the uninstall key: throwaway ones, made here and removed at the end;
  * opening a browser tab does nothing (the plain launcher a switch starts would open one);
  * `shelfsync/platform/build-suffix.txt` holds a throwaway suffix, so the Run value a copy writes (it counts as an
    installed copy, and Start with Windows is on by default) and its AUMID are `ShelfSync-rehearse-<id>` and
    `TecHaust.ShelfSync-rehearse-<id>`, never the real names;
  * `paths.py`: a copy started without SHELFSYNC_DATA_DIR stops instead of using the real data folder (so the Run
    value a killed run leaves behind can never start a copy on the real database at the next sign-in).
Before a copy runs, its own Python must report the throwaway Run value, AUMID and Credential Manager service and
refuse to find a data folder without SHELFSYNC_DATA_DIR; anything else stops the run. Then it follows the updater's
sequence: install 0.0.1; update to 0.0.2 (one extra migration); roll back (backup restored); a tampered 0.0.3 is
refused; a broken 0.0.4 (its migration fails, exit 2) is switched back. Last it removes everything it made and checks
that: no throwaway Credential Manager entry, uninstall key, Run value, AUMID key or folder is left, and the real names
and folders read the same as before.

Quit ShelfSync first: the copies use the app's single-instance lock, so the rehearsal stops if a copy is running. If
the run is killed, its first lines name what to remove by hand (docs/runs/t7-rehearse-current-build.md has the steps).
"""

import argparse
import contextlib
import ctypes
import dataclasses
import filecmp
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
import winreg
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from ctypes import wintypes
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from shelfsync.db.backup import database_schema, latest_schema
from shelfsync.paths import DataPaths
from shelfsync.platform import aumid, names
from shelfsync.platform.autostart import RUN_KEY
from shelfsync.platform.junction import WindowsJunctions
from shelfsync.platform.process import RealProcesses
from shelfsync.platform.secrets import OWNED_SECRET_NAMES, KeyringSecretStore
from shelfsync.platform.sockets import current_user_sid
from shelfsync.platform.uninstall_entry import UNINSTALL_KEY
from shelfsync.secure.token import INSTALL_TOKEN_NAME
from shelfsync.tray.instance import mutex_name
from shelfsync.update.layout import InstallLayout, UpdatePaths
from shelfsync.update.manifest import FileEntry, make_manifest, setup_asset_name, zip_asset_name
from shelfsync.update.state import PendingUpdate, ResultStore, StateStore, SwitchResult

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "backend" / "shelfsync"
ORIGIN_HEADERS = {"X-ShelfSync": "1"}
# The rehearsal's own migrations carry numbers no real migration will reach, so they never collide with one the source
# tree adds (0002_store, ...). BASE is the schema the copied build already has; NEW and BROKEN come after it.
BASE_SCHEMA = 0  # set in main() from the --base build's own migrations folder
NEW_SCHEMA = 9001
BROKEN_SCHEMA = 9002
MIGRATION_2 = "CREATE TABLE rehearsal_note (id INTEGER PRIMARY KEY, body TEXT NOT NULL);\n"
MIGRATION_3_BROKEN = "CREATE TABLE half_done (id INTEGER);\nINSERT INTO table_that_does_not_exist VALUES (1);\n"

# Every throwaway name carries this run's id, so nothing here can match a real name or another run's.
RUN_ID = uuid.uuid4().hex[:8]
SERVICE = f"ShelfSyncRehearsal-{RUN_ID}"  # the Credential Manager service the copies use
SUFFIX = f"-rehearse-{RUN_ID}"  # the copies' build suffix: their Run value and AUMID
RUN_VALUE = names.run_value_name(SUFFIX) or ""  # ShelfSync-rehearse-<id> ("" only if the suffix broke the rule)
AUMID = names.aumid_for(SUFFIX) or ""  # TecHaust.ShelfSync-rehearse-<id>
# The copies' uninstall entry. An "installed" copy (and the fake versions are: they sit in versions\<their own version>)
# updates `DisplayVersion` in its uninstall key. The copies are patched to a THROWAWAY key, which this script makes
# first and deletes at the end, so the real `...\Uninstall\ShelfSync` key is never opened for writing.
UNINSTALL_PARENT = rf"Software\ShelfSyncRehearsal-{RUN_ID}"
UNINSTALL_KEY_PATH = rf"{UNINSTALL_PARENT}\Uninstall"
# A copy's data folder comes only from SHELFSYNC_DATA_DIR: without it, it stops (never %LOCALAPPDATA%\ShelfSync).
REAL_DATA_FOLDER_LINE = '    return DataPaths(Path(local_app_data) / "ShelfSync")'
NO_REAL_DATA_FOLDER_LINE = '    raise RuntimeError("a rehearsal copy runs only with SHELFSYNC_DATA_DIR")'
# Only platform/secrets.py (patched to SERVICE) may talk to Credential Manager; checked in --base before anything runs.
CREDENTIAL_CALL = re.compile(r"keyring|win32cred|Cred(Read|Write|Delete|Enumerate)")
SECRETS_MODULE = "platform/secrets.py"
# What each copy's own Python runs: smoke.py's names probe (it also requires the modules to be the copy's own), then
# the Credential Manager service it would use and whether it finds a data folder without SHELFSYNC_DATA_DIR.
COPY_PROBE_TAIL = """
from shelfsync import paths
from shelfsync.platform import secrets
print(secrets.SERVICE_NAME)
print(secrets.KeyringSecretStore.__init__.__defaults__[0])
try:
    paths.resolve_data_paths()
except RuntimeError:
    print('no-data-folder')
else:
    print('data-folder-found')
"""

steps: list[tuple[str, bool, str]] = []


class RehearsalError(Exception):
    """A patch target or a precondition is missing. The sequence stops; the clean-up still runs and is checked."""


def say(text: str) -> None:
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def check(name: str, ok: bool, detail: str = "") -> bool:
    steps.append((name, ok, detail))
    say(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    return ok


def child_env() -> dict[str, str]:
    """The environment for a copy's own Python: nothing that could point it at this checkout's code."""
    return {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME", "SHELFSYNC_INSTALL_DIR")}


def load_smoke() -> ModuleType:
    """packaging/smoke.py, for its names probe: the same check the release build makes of the built folder."""
    spec = importlib.util.spec_from_file_location("shelfsync_packaging_smoke", REPO / "packaging" / "smoke.py")
    if spec is None or spec.loader is None:
        raise RehearsalError("packaging/smoke.py can't be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SMOKE = load_smoke()


def replace(path: Path, old: str, new: str) -> None:
    """Replace `old`, which must be in the file exactly once."""
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise RehearsalError(f"rehearsal patch target not found exactly once in {path.name}: {old[:60]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="")


def replace_line(path: Path, pattern: str, new: str) -> None:
    """Replace the one line start that `pattern` matches (multi-line mode)."""
    text = path.read_text(encoding="utf-8")
    changed, count = re.subn(pattern, new, text, flags=re.MULTILINE)
    if count != 1:
        raise RehearsalError(f"rehearsal patch target not found exactly once in {path.name}: {pattern!r}")
    path.write_text(changed, encoding="utf-8", newline="")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def public_bytes(key: Ed25519PrivateKey) -> bytes:
    return key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


# ---- reading Windows state (values are compared, never printed) --------------------------------------------------


def registry_values(path: str) -> dict[str, Any] | None:
    """Every value of `HKCU\\<path>`, or None when the key isn't there."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_QUERY_VALUE) as key:
            values: dict[str, Any] = {}
            index = 0
            while True:
                try:
                    name, value, kind = winreg.EnumValue(key, index)
                except OSError:
                    return values
                values[name] = (kind, value)
                index += 1
    except FileNotFoundError:
        return None


def registry_key_exists(path: str) -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_QUERY_VALUE):
            return True
    except FileNotFoundError:
        return False


def display_version() -> str | None:
    values = registry_values(UNINSTALL_KEY_PATH)
    found = values.get("DisplayVersion") if values else None
    return str(found[1]) if found else None


def run_value(name: str) -> str | None:
    values = registry_values(RUN_KEY)
    found = values.get(name) if values else None
    return str(found[1]) if found else None


class _CredentialHead(ctypes.Structure):
    """The first fields of CREDENTIALW: only the target name is ever read (never the secret)."""

    _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR)]


_ERROR_NOT_FOUND = 1168
_CRED_TYPE_GENERIC = 1
_advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
_advapi32.CredEnumerateW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.POINTER(ctypes.POINTER(ctypes.POINTER(_CredentialHead))),
]
_advapi32.CredEnumerateW.restype = wintypes.BOOL
_advapi32.CredFree.argtypes = [ctypes.c_void_p]
_advapi32.CredFree.restype = None
_advapi32.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
_advapi32.CredDeleteW.restype = wintypes.BOOL


def throwaway_targets() -> list[str]:
    """The Credential Manager target names that start with the throwaway service (`ShelfSyncRehearsal-<id>`; the run id
    makes the prefix this run's own). Only this filter is ever passed: no other credential is enumerated."""
    count = wintypes.DWORD()
    found = ctypes.POINTER(ctypes.POINTER(_CredentialHead))()
    if not _advapi32.CredEnumerateW(f"{SERVICE}*", 0, ctypes.byref(count), ctypes.byref(found)):
        error = ctypes.get_last_error()
        if error == _ERROR_NOT_FOUND:
            return []
        raise OSError(f"CredEnumerateW failed (Windows error {error})")
    try:
        targets = [found[index].contents.TargetName or "" for index in range(count.value)]
    finally:
        _advapi32.CredFree(found)
    return sorted(target for target in targets if target.startswith(SERVICE))


def throwaway_entries_left() -> list[str]:
    """What is left under the throwaway service: targets that start with it, and each owned entry keyring still finds
    under it (that also covers keyring's `<entry>@<service>` targets, which the prefix filter can't)."""
    store = KeyringSecretStore(service=SERVICE)
    return throwaway_targets() + [name for name in OWNED_SECRET_NAMES if store.get(name) is not None]


def folder_listing(root: Path) -> dict[str, tuple[Any, ...]] | None:
    """Every entry under `root` (links and junctions are listed, never followed) with its size and modified time, or
    None when `root` isn't there."""
    if not os.path.lexists(root):
        return None
    listing: dict[str, tuple[Any, ...]] = {}
    pending = [root]
    while pending:
        folder = pending.pop()
        try:
            with os.scandir(folder) as entries:
                for entry in entries:
                    relative = os.path.relpath(entry.path, root)
                    if entry.is_symlink() or entry.is_junction():
                        listing[relative] = ("link", os.readlink(entry.path))
                    elif entry.is_dir(follow_symlinks=False):
                        listing[relative] = ("folder",)
                        pending.append(Path(entry.path))
                    else:
                        found = entry.stat(follow_symlinks=False)
                        listing[relative] = ("file", found.st_size, found.st_mtime_ns)
        except OSError as error:
            listing[os.path.relpath(folder, root)] = ("unreadable", type(error).__name__)
    return listing


def real_state() -> dict[str, Any]:
    """What the run must leave exactly as it found it: the real names and folders (and any other ShelfSync Run value,
    a rehearsal install's included). The real Credential Manager service isn't read: `check_base` and each copy's
    probe prove the copies can't reach it."""
    local = Path(os.environ["LOCALAPPDATA"])
    run_values = registry_values(RUN_KEY) or {}
    return {
        "the ShelfSync Run values": {
            name: value
            for name, value in run_values.items()
            if name.casefold().startswith(names.BASE_RUN_VALUE_NAME.casefold()) and name != RUN_VALUE
        },
        "the real uninstall key": registry_values(UNINSTALL_KEY),
        "the real AUMID key": registry_values(aumid.key_path(names.BASE_AUMID)),
        "the real data folder": folder_listing(local / "ShelfSync"),
        "the real install folder": folder_listing(local / "Programs" / "ShelfSync"),
    }


def shelfsync_running() -> bool:
    """True when some copy of ShelfSync holds the single-instance mutex (checked without taking it)."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.OpenMutexW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel32.OpenMutexW(0x00100000, False, mutex_name(current_user_sid()))  # SYNCHRONIZE
    if handle:
        kernel32.CloseHandle(handle)
        return True
    return ctypes.get_last_error() == 5  # ERROR_ACCESS_DENIED: the name exists


# ---- building a fake version ---------------------------------------------------------------------------------------


def code_differences(base: Path) -> list[str]:
    """The files of this checkout's `backend/shelfsync` that the build lacks or holds differently (a note only: the
    rehearsal runs the build's code)."""
    differences: list[str] = []
    for source in sorted(SRC.rglob("*")):
        if not source.is_file() or "__pycache__" in source.parts or source.name == names.SUFFIX_FILE_NAME:
            continue
        relative = source.relative_to(SRC)
        built = base / "shelfsync" / relative
        if not built.is_file() or not filecmp.cmp(source, built, shallow=False):
            differences.append(relative.as_posix())
    return differences


def credential_callers(base: Path) -> list[str]:
    """The build's modules, other than `platform/secrets.py`, that name a Credential Manager API (none may)."""
    package = base / "shelfsync"
    return sorted(
        found.relative_to(package).as_posix()
        for found in package.rglob("*.py")
        if found.relative_to(package).as_posix() != SECRETS_MODULE
        and CREDENTIAL_CALL.search(found.read_text(encoding="utf-8"))
    )


def copy_report(folder: Path) -> list[str]:
    """What the copy's own Python reports (COPY_PROBE_TAIL after smoke.py's names probe), with SHELFSYNC_DATA_DIR
    removed from its environment, or why it couldn't."""
    env = child_env()
    env.pop("SHELFSYNC_DATA_DIR", None)
    done = subprocess.run(
        [str(folder / "python.exe"), "-B", "-c", SMOKE.NAMES_PROBE + "\n" + COPY_PROBE_TAIL],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        env=env,
    )
    return done.stdout.split() if done.returncode == 0 else [f"exit {done.returncode}: {done.stderr[-300:]}"]


def build_version(
    layout: InstallLayout,
    base: Path,
    version: str,
    schema: int,
    signer: Ed25519PrivateKey,
    app_key: Ed25519PrivateKey,
    extra_migrations: dict[str, str],
) -> Path:
    """`versions\\<version>`: a copy of the base, patched, compiled, its names checked, and a manifest signed by
    `signer`. The release key baked into the app is `app_key`'s."""
    folder = layout.version_dir(version)
    shutil.copytree(base, folder)
    package = folder / "shelfsync"
    replace_line(package / "__init__.py", r'^__version__ = "[^"\n]*"', f'__version__ = "{version}"')
    replace(
        package / "update" / "release_key.py",
        "PUBLIC_KEY: bytes | None = None",
        f"PUBLIC_KEY: bytes | None = bytes.fromhex('{public_bytes(app_key).hex()}')",
    )
    replace(package / "update" / "service.py", "FIRST_CHECK_SECONDS = 60.0", "FIRST_CHECK_SECONDS = 3.0e6")
    replace(package / "platform" / "secrets.py", 'SERVICE_NAME = "ShelfSync"', f'SERVICE_NAME = "{SERVICE}"')
    replace(
        package / "platform" / "uninstall_entry.py",
        'UNINSTALL_KEY = r"Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\ShelfSync"',
        f'UNINSTALL_KEY = r"{UNINSTALL_KEY_PATH}"',
    )
    replace(
        package / "platform" / "shell.py",
        "os.startfile(url)  # nosec B606",
        "None  # the rehearsal opens no browser tab",
    )
    replace(package / "paths.py", REAL_DATA_FOLDER_LINE, NO_REAL_DATA_FOLDER_LINE)
    # The suffix the build may carry (-rehearsal) is replaced by this run's own, in the place platform/names.py reads.
    (package / "platform" / names.SUFFIX_FILE_NAME).write_text(SUFFIX, encoding="ascii", newline="")
    migrations = package / "db" / "migrations"
    for name, sql in extra_migrations.items():
        (migrations / name).write_text(sql, encoding="utf-8", newline="")
    for pycache in package.rglob("__pycache__"):
        shutil.rmtree(pycache)
    subprocess.run(
        [
            str(folder / "python.exe"),
            "-m",
            "compileall",
            "-q",
            "-f",
            "--invalidation-mode",
            "checked-hash",
            str(package),
        ],
        check=True,
        env=child_env(),
    )
    reported = copy_report(folder)
    if not check(
        f"{version}: its own Python reports the throwaway Run value, AUMID and Credential Manager service (as the "
        "service and the store's default), and finds no data folder without SHELFSYNC_DATA_DIR",
        reported == [RUN_VALUE, AUMID, SERVICE, SERVICE, "no-data-folder"],
        " ".join(reported),
    ):
        raise RehearsalError(f"the {version} copy isn't safe to run: the rehearsal stops here")
    write_manifest(layout, folder, version, schema, signer)
    return folder


def write_manifest(layout: InstallLayout, folder: Path, version: str, schema: int, signer: Ed25519PrivateKey) -> None:
    files = {
        path.relative_to(folder).as_posix(): FileEntry(path.stat().st_size, sha256(path))
        for path in sorted(folder.rglob("*"))
        if path.is_file()
    }
    manifest = make_manifest(
        version=version,
        source_commit="0" * 40,
        built_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        schema_version=schema,
        assets={
            setup_asset_name(version): FileEntry(1, "0" * 64),
            zip_asset_name(version): FileEntry(1, "0" * 64),
        },
        files=files,
    )
    layout.manifests.mkdir(parents=True, exist_ok=True)
    layout.manifest_path(version).write_bytes(manifest)
    layout.signature_path(version).write_bytes(signer.sign(manifest))


# ---- talking to the running app ----------------------------------------------------------------------------------


class App:
    def __init__(self, layout: InstallLayout, paths: DataPaths, env: dict[str, str], work: Path) -> None:
        self.layout, self.paths, self.env, self.work = layout, paths, env, work
        self.processes = RealProcesses()

    def start(self) -> None:
        self.processes.spawn_detached(
            [str(self.layout.current / "pythonw.exe"), "-m", "shelfsync.launcher", "--background"],
            self.layout.current,
            self.env,
        )

    def runtime(self) -> tuple[int, int] | None:
        try:
            data = json.loads(self.paths.runtime_json.read_text(encoding="utf-8"))
            return int(data["port"]), int(data["pid"])
        except OSError, ValueError, KeyError:
            return None

    def health(self) -> str | None:
        found = self.runtime()
        if found is None:
            return None
        try:
            response = httpx.get(f"http://127.0.0.1:{found[0]}/api/health", timeout=3.0, trust_env=False)
            return str(response.json().get("version")) if response.status_code == 200 else None
        except httpx.HTTPError, ValueError:
            return None

    def wait_version(self, version: str, seconds: float = 120.0, other_pid: int | None = None) -> bool:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            found = self.runtime()
            if self.health() == version and (other_pid is None or (found is not None and found[1] != other_pid)):
                return True
            time.sleep(0.5)
        return False

    @contextmanager
    def client(self) -> Iterator[httpx.Client]:
        """A signed-in client: the install token (from the throwaway Credential Manager service, never printed) buys a
        ticket, the ticket a session cookie, exactly as the launcher and the page do."""
        found = self.runtime()
        if found is None:
            raise RehearsalError("the app isn't running (no runtime.json)")
        base = f"http://127.0.0.1:{found[0]}"
        token = KeyringSecretStore(service=SERVICE).get(INSTALL_TOKEN_NAME)
        client = httpx.Client(base_url=base, trust_env=False, timeout=120.0)
        try:
            ticket = client.post("/api/session/ticket", headers={"Authorization": f"Bearer {token}"}).json()["ticket"]
            client.post(
                "/api/session", json={"ticket": ticket}, headers={"Origin": base, **ORIGIN_HEADERS}
            ).raise_for_status()
            client.headers.update({"Origin": base, **ORIGIN_HEADERS})
            yield client
        finally:
            client.close()

    def stop(self) -> None:
        """End the running copy, and only if Windows says its program file is under --work (runtime.json is the
        copy's, but a stale one could name a PID that some other program has since been given)."""
        found = self.runtime()
        if found is None:
            return
        watch = self.processes.watch(found[1])
        if watch is None:
            return
        try:  # the open handle keeps the PID from being reused until the process is ended
            image = watch.image
            inside = os.path.join(os.path.normcase(str(self.work)), "")
            if image is not None and os.path.normcase(image).startswith(inside):
                self.processes.terminate_pid(found[1])
            else:
                say(f"  (PID {found[1]} isn't a program under --work: left alone)")
        finally:
            watch.close()


def wait_result(paths: DataPaths, to_version: str, newer_than: str, seconds: float = 150.0) -> SwitchResult | None:
    store = ResultStore(UpdatePaths(paths))
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = store.load()
        if result is not None and result.to_version == to_version and result.at > newer_than:
            return result
        time.sleep(0.5)
    return None


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def stage(layout: InstallLayout, paths: DataPaths, version: str) -> None:
    """Make `version` the downloaded, ready update (what a successful check leaves behind)."""
    StateStore(UpdatePaths(paths)).update(
        lambda s: dataclasses.replace(s, pending=PendingUpdate(version, str(layout.version_dir(version)), now_iso()))
    )


# ---- the sequence --------------------------------------------------------------------------------------------------


def sequence(app: App, layout: InstallLayout, paths: DataPaths, base: Path) -> None:
    key, wrong = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    links = WindowsJunctions()
    say("Building the fake versions (a copy of the embedded build each, patched and signed with a throwaway key)")
    build_version(layout, base, "0.0.1", BASE_SCHEMA, key, key, {})
    build_version(layout, base, "0.0.2", NEW_SCHEMA, key, key, {f"{NEW_SCHEMA:04d}_rehearsal.sql": MIGRATION_2})
    links.create(layout.current, layout.version_dir("0.0.1"))

    say("\n1. Install 0.0.1")
    app.start()
    check("0.0.1 starts and answers /api/health as 0.0.1", app.wait_version("0.0.1", 90))
    check(f"the database is at schema {BASE_SCHEMA}", database_schema(paths.database) == BASE_SCHEMA)
    wanted = os.path.normcase(os.path.join(os.path.realpath(layout.root), "current", "pythonw.exe"))
    written = run_value(RUN_VALUE)
    check(f"Start with Windows wrote the throwaway Run value {RUN_VALUE}, naming this rehearsal's current\\pythonw.exe",
          written is not None and wanted in os.path.normcase(written))  # fmt: skip
    found = app.runtime()
    old_pid = found[1] if found else 0
    with app.client() as client:
        status = client.get("/api/updates").json()
    check("GET /api/updates: installed 0.0.1, not development, a key in the build",
          status["installed"] == "0.0.1" and not status["development"] and status["key_available"])  # fmt: skip

    say("\n2. Update to 0.0.2 (one extra migration)")
    stage(layout, paths, "0.0.2")
    began = now_iso()
    with app.client() as client:
        response = client.post("/api/updates/install")
    check("POST /api/updates/install answers 202", response.status_code == 202, str(response.status_code))
    result = wait_result(paths, "0.0.2", began)
    check("the switch reports updated", result is not None and result.outcome == "updated", str(result))
    check("0.0.2 is running (a new process, a new answer)", app.wait_version("0.0.2", 60, other_pid=old_pid))
    check("current points at 0.0.2", os.path.realpath(layout.current).endswith("0.0.2"))
    check(f"the database moved to schema {NEW_SCHEMA}", database_schema(paths.database) == NEW_SCHEMA)
    check(
        "DisplayVersion in the throwaway uninstall key is 0.0.2",
        display_version() == "0.0.2",
        str(display_version()),
    )
    backups = sorted(paths.backups.glob(f"pre-migration-{BASE_SCHEMA:04d}-to-{NEW_SCHEMA:04d}-*.db"))
    check("a pre-migration backup was taken first", len(backups) == 1)
    with app.client() as client:
        status = client.get("/api/updates").json()
    check("the picture says: previous 0.0.1, roll back possible, database changed",
          status["previous"] == "0.0.1" and status["can_roll_back"] and status["database_changed"]
          and status["backup_available"])  # fmt: skip

    say("\n3. Roll back, with the backup restored")
    found = app.runtime()
    old_pid = found[1] if found else 0
    watch = app.processes.watch(old_pid)
    if watch is not None:
        say(f"  (the running app's image as Windows reports it: {watch.image!r})")
        watch.close()
    with app.client() as client:
        refused = client.post("/api/updates/rollback", json={})
        check("a roll back that loses data needs confirmation (422 confirm_required)",
              refused.status_code == 422 and refused.json() == {"error": "confirm_required"})  # fmt: skip
        began = now_iso()
        accepted = client.post("/api/updates/rollback", json={"confirm_data_loss": True})
    check("the confirmed roll back answers 202", accepted.status_code == 202)
    result = wait_result(paths, "0.0.1", began)
    check("the switch reports rolled_back", result is not None and result.outcome == "rolled_back", str(result))
    check("0.0.1 is running again", app.wait_version("0.0.1", 60, other_pid=old_pid))
    check(
        f"the database is back at schema {BASE_SCHEMA} (the backup was restored)",
        database_schema(paths.database) == BASE_SCHEMA,
    )
    check("DisplayVersion is 0.0.1 again", display_version() == "0.0.1", str(display_version()))
    check(
        "a pre-rollback snapshot of the updated database was kept",
        len(list(paths.backups.glob("pre-rollback-0.0.2-*.db"))) == 1,
    )
    check(
        "both version folders are still there",
        layout.version_dir("0.0.1").is_dir() and layout.version_dir("0.0.2").is_dir(),
    )

    say("\n4. A tampered 0.0.3 is refused")
    # built only now: a switch prunes every version but the two it keeps, so an earlier one would be gone
    build_version(layout, base, "0.0.3", NEW_SCHEMA, wrong, key, {f"{NEW_SCHEMA:04d}_rehearsal.sql": MIGRATION_2})
    found = app.runtime()
    pid_before = found[1] if found else 0
    stage(layout, paths, "0.0.3")
    with app.client() as client:
        wrong_key = client.post("/api/updates/install")
    check("0.0.3 is signed by another key: install answers 409 manifest_invalid",
          wrong_key.status_code == 409 and wrong_key.json() == {"error": "manifest_invalid"},
          f"{wrong_key.status_code} {wrong_key.text}")  # fmt: skip
    write_manifest(layout, layout.version_dir("0.0.3"), "0.0.3", NEW_SCHEMA, key)  # properly signed now ...
    (layout.version_dir("0.0.3") / "pythonw.exe").write_bytes(b"swapped after the download")  # ... but a file changed
    with app.client() as client:
        tampered = client.post("/api/updates/install")
    check("a file changed after the signed manifest was made: install answers 409 files_changed",
          tampered.status_code == 409 and tampered.json() == {"error": "files_changed"},
          f"{tampered.status_code} {tampered.text}")  # fmt: skip
    found = app.runtime()
    check(
        "nothing happened: 0.0.1 is still the same running process",
        app.health() == "0.0.1" and found is not None and found[1] == pid_before,
    )
    check("current still points at 0.0.1", os.path.realpath(layout.current).endswith("0.0.1"))

    say("\n5. A broken 0.0.4 (its second migration fails, the app exits 2) is switched back")
    build_version(
        layout, base, "0.0.4", BROKEN_SCHEMA, key, key,
        {
            f"{NEW_SCHEMA:04d}_rehearsal.sql": MIGRATION_2,
            f"{BROKEN_SCHEMA:04d}_broken.sql": MIGRATION_3_BROKEN,
        },
    )  # fmt: skip
    found = app.runtime()
    old_pid = found[1] if found else 0
    stage(layout, paths, "0.0.4")
    began = now_iso()
    with app.client() as client:
        accepted = client.post("/api/updates/install")
    check("install of 0.0.4 answers 202", accepted.status_code == 202)
    result = wait_result(paths, "0.0.4", began, 180.0)
    check(
        "the switch reports kept_old with migration_failed",
        result is not None and (result.outcome, result.reason) == ("kept_old", "migration_failed"),
        str(result),
    )
    check("0.0.1 is running again", app.wait_version("0.0.1", 60, other_pid=old_pid))
    check("current points at 0.0.1", os.path.realpath(layout.current).endswith("0.0.1"))
    check(
        f"the database is unchanged by the failed migration (schema {BASE_SCHEMA}, no half-done table)",
        database_schema(paths.database) == BASE_SCHEMA,
    )
    check("DisplayVersion went to 0.0.4 and back: it is 0.0.1", display_version() == "0.0.1", str(display_version()))
    with app.client() as client:
        status = client.get("/api/updates").json()
    check("the last result is reported through GET /api/updates", status["last_result"]["outcome"] == "kept_old")


# ---- clean-up --------------------------------------------------------------------------------------------------------


def guarded(what: str, action: Callable[[], object]) -> None:
    """One clean-up step: a failure is a FAIL line, and the next step still runs."""
    try:
        action()
    except Exception as error:
        check(f"clean-up: {what}", False, f"{type(error).__name__}: {error}")


def check_safely(name: str, test: Callable[[], bool]) -> None:
    """A check whose test may itself fail (a registry or Credential Manager read): that is a FAIL, not a stop."""
    try:
        ok, detail = test(), ""
    except Exception as error:
        ok, detail = False, f"{type(error).__name__}: {error}"
    check(name, ok, detail)


def stop_leftovers(work: Path) -> None:
    """End whatever still runs from --work (nothing, normally), so the folder can be removed. The path reaches
    PowerShell through the environment, never inside the command text."""
    command = (
        r"$p = $env:SHELFSYNC_REHEARSAL_WORK + '\'; "
        r"Get-Process | Where-Object { $_.Path -and "
        r"$_.Path.StartsWith($p, [System.StringComparison]::OrdinalIgnoreCase) } | Stop-Process -Force"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        check=False,
        env={**os.environ, "SHELFSYNC_REHEARSAL_WORK": str(work)},
    )


def delete_throwaway_run_value() -> None:
    with (
        contextlib.suppress(FileNotFoundError),
        winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key,
    ):
        winreg.DeleteValue(key, RUN_VALUE)  # the throwaway Run value (ShelfSync-rehearse-<id>) only


def delete_throwaway_uninstall_key() -> None:
    for path in (UNINSTALL_KEY_PATH, UNINSTALL_PARENT):  # children first
        with contextlib.suppress(FileNotFoundError):
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)


def delete_throwaway_credentials() -> None:
    store = KeyringSecretStore(service=SERVICE)
    for name in OWNED_SECRET_NAMES:  # removing one that was never stored is not an error
        store.delete(name)
    for target in throwaway_targets():  # anything else whose name starts with the throwaway service
        _advapi32.CredDeleteW(target, _CRED_TYPE_GENERIC, 0)


def keep_logs(paths: DataPaths) -> None:
    keep = REPO / ".logs" / "rehearsal"  # what a failed run needs: the app's log and the updater's two files
    shutil.rmtree(keep, ignore_errors=True)
    for source in (paths.logs, UpdatePaths(paths).root):
        if source.exists():
            shutil.copytree(source, keep / source.name, ignore=shutil.ignore_patterns("downloads"), dirs_exist_ok=True)


def remove_junction(layout: InstallLayout) -> None:
    if os.path.lexists(layout.current):
        WindowsJunctions().remove(layout.current)


def clean_up(app: App, layout: InstallLayout, paths: DataPaths, work: Path) -> None:
    """Remove everything the run made (only names carrying this run's id, and the --work folder). Each step is
    guarded, so one that fails never skips the others."""
    time.sleep(6.0)  # the plain launcher a switch starts (a second launch) must finish before the app is stopped
    guarded("stop the running copy", app.stop)
    time.sleep(2.0)
    guarded("stop what still runs from --work", lambda: stop_leftovers(work))
    time.sleep(1.0)
    guarded("remove the throwaway Run value", delete_throwaway_run_value)
    guarded("remove the throwaway uninstall key", delete_throwaway_uninstall_key)
    guarded("remove the throwaway Credential Manager entries", delete_throwaway_credentials)
    guarded("remove the current junction", lambda: remove_junction(layout))
    guarded("keep the logs in .logs/rehearsal", lambda: keep_logs(paths))
    guarded("remove --work", lambda: shutil.rmtree(work, ignore_errors=True))


def check_clean(work: Path, before: dict[str, Any]) -> None:
    say("\n6. Nothing is left, and nothing real was touched")
    check_safely(f"nothing is left under the throwaway Credential Manager service {SERVICE}",
                 lambda: throwaway_entries_left() == [])  # fmt: skip
    check_safely("the throwaway uninstall key is gone", lambda: not registry_key_exists(UNINSTALL_PARENT))
    check_safely(f"the throwaway Run value {RUN_VALUE} is gone", lambda: run_value(RUN_VALUE) is None)
    check_safely(f"no AUMID key for {AUMID} (the app only reads it)",
                 lambda: not registry_key_exists(aumid.key_path(AUMID)))  # fmt: skip
    check_safely("the --work folder is gone", lambda: not os.path.lexists(work))
    try:
        after: dict[str, Any] | None = real_state()
    except Exception as error:
        after = None
        check("the real names and folders can be read again", False, f"{type(error).__name__}: {error}")
    for name, found in before.items():
        check(f"{name}: the same as before the run", after is not None and after[name] == found)


def summary() -> int:
    failed = [name for name, ok, _ in steps if not ok]
    say(f"\n{len(steps) - len(failed)} of {len(steps)} checks passed")
    for name in failed:
        say(f"FAILED: {name}")
    return 1 if failed else 0


def main() -> int:
    global BASE_SCHEMA
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    base, work = args.base.resolve(), args.work.resolve()
    if not (base / "python.exe").is_file() or not (base / "shelfsync" / "__init__.py").is_file():
        raise SystemExit(f"--base {base} isn't an embedded build folder (no python.exe or shelfsync)")
    if work.exists() and any(work.iterdir()):
        raise SystemExit("--work must be an empty or new folder")
    if not RUN_VALUE or not AUMID:
        raise SystemExit(f"the throwaway suffix {SUFFIX!r} breaks the suffix rule")
    if shelfsync_running():
        raise SystemExit("ShelfSync is running: quit it from its tray icon first (the copies use its single lock)")
    # What a killed run leaves behind, named first so it can be removed by hand (the run file has the steps).
    say(f"Throwaway names of this run (id {RUN_ID}): Credential Manager service {SERVICE}; Run value {RUN_VALUE} in "
        rf"HKCU\{RUN_KEY}; uninstall key HKCU\{UNINSTALL_PARENT}; AUMID {AUMID}; folder {work}")  # fmt: skip
    BASE_SCHEMA = latest_schema(base / "shelfsync" / "db" / "migrations")  # the build's own, not this repo's
    differences = code_differences(base)
    if differences:
        shown = ", ".join(differences[:5]) + (", ..." if len(differences) > 5 else "")
        say(f"(note: this checkout's code differs from the build's in {len(differences)} files: {shown}; the build's "
            "code is what runs)")  # fmt: skip
    callers = credential_callers(base)
    if not check(f"--base: no module but {SECRETS_MODULE} names a Credential Manager API", callers == [],
                 ", ".join(callers)):  # fmt: skip
        return summary()  # nothing was made
    before = real_state()
    layout = InstallLayout(work / "Programs" / "ShelfSync")
    paths = DataPaths(work / "data")
    env = child_env()
    env["SHELFSYNC_DATA_DIR"] = str(paths.root)
    app = App(layout, paths, env, work)
    try:
        paths.root.mkdir(parents=True)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY_PATH) as throwaway:  # the throwaway uninstall key
            winreg.SetValueEx(throwaway, "DisplayName", 0, winreg.REG_SZ, "ShelfSync (rehearsal)")
            winreg.SetValueEx(throwaway, "DisplayVersion", 0, winreg.REG_SZ, "0.0.1")
        sequence(app, layout, paths, base)
    except Exception as error:
        check("the sequence ran to the end", False, f"{type(error).__name__}: {error}")
    finally:
        clean_up(app, layout, paths, work)
        check_clean(work, before)
    return summary()


if __name__ == "__main__":
    sys.exit(main())
