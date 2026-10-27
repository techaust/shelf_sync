"""A local rehearsal of the updater with THROWAWAY roots, keys and Credential Manager service (M1b.2 "Done means").
Run by a developer, from the repository root; it never contacts GitHub, a store or S3 and never touches the real data
folder, install folder, Run key, uninstall key or Credential Manager entries.

    PYTHONPATH=backend uv run python tools/release/rehearse.py --base <an embedded build folder> --work <empty folder>

`--base` is a folder made by m1b.1's `packaging/build.py` (a real embedded Python with the app's packages): it is only
COPIED, never changed. Each fake version folder is that copy with this branch's update code overlaid (and
`cryptography` from this checkout's environment), patched in the copy only for the rehearsal:
  * `__version__` and the release public key (a key made here, in memory);
  * the Credential Manager service name (a throwaway one, removed at the end);
  * the schedule: the first update check is pushed out so nothing ever asks GitHub;
  * `server.py` and `api/app.py` get the two wiring changes of this task on top of m1b.1's versions.
Then it follows the brief's sequence: install 0.0.1; update to 0.0.2 (one extra migration); roll back (backup restored);
a tampered 0.0.3 is refused; a broken 0.0.4 (its migration fails, exit 2) is switched back.
"""

import argparse
import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
import winreg
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from shelfsync.db.backup import database_schema
from shelfsync.paths import DataPaths
from shelfsync.platform.junction import WindowsJunctions
from shelfsync.platform.process import RealProcesses
from shelfsync.platform.secrets import KeyringSecretStore
from shelfsync.secure.token import INSTALL_TOKEN_NAME
from shelfsync.update.layout import InstallLayout, UpdatePaths
from shelfsync.update.manifest import FileEntry, make_manifest, setup_asset_name, zip_asset_name
from shelfsync.update.state import PendingUpdate, ResultStore, StateStore, SwitchResult

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "backend" / "shelfsync"
ORIGIN_HEADERS = {"X-ShelfSync": "1"}
OVERLAY = [
    "update",
    "db/backup.py",
    "platform/junction.py",
    "platform/process.py",
    "platform/uninstall_entry.py",
    "api/updates.py",
    "api/secrets.py",
    "secure/headers.py",
]
MIGRATION_2 = "CREATE TABLE rehearsal_note (id INTEGER PRIMARY KEY, body TEXT NOT NULL);\n"
MIGRATION_3_BROKEN = "CREATE TABLE half_done (id INTEGER);\nINSERT INTO table_that_does_not_exist VALUES (1);\n"

steps: list[tuple[str, bool, str]] = []

# The copies' uninstall entry. An "installed" copy (and the fake versions are: they sit in versions\<their own version>)
# updates `DisplayVersion` in `UNINSTALL_KEY`. The rehearsal copies are patched to a THROWAWAY key, which this script
# makes first and deletes at the end, so the real `...\Uninstall\ShelfSync` key is never opened.
UNINSTALL_PARENT = rf"Software\ShelfSyncRehearsal-{uuid.uuid4().hex[:8]}"
UNINSTALL_KEY_PATH = rf"{UNINSTALL_PARENT}\Uninstall"


def display_version() -> str | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY_PATH) as key:
            return str(winreg.QueryValueEx(key, "DisplayVersion")[0])
    except OSError:
        return None


def say(text: str) -> None:
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def check(name: str, ok: bool, detail: str = "") -> bool:
    steps.append((name, ok, detail))
    say(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    return ok


def replace(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"rehearsal patch not found in {path.name}: {old[:60]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def public_bytes(key: Ed25519PrivateKey) -> bytes:
    return key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


# ---- building a fake version ---------------------------------------------------------------------------------------


def build_version(
    layout: InstallLayout,
    base: Path,
    version: str,
    schema: int,
    signer: Ed25519PrivateKey,
    app_key: Ed25519PrivateKey,
    service: str,
    extra_migrations: dict[str, str],
) -> Path:
    """`versions\\<version>`: a copy of the base, this branch's code overlaid, patched, compiled, and a manifest signed
    by `signer`. The release key baked into the app is `app_key`'s."""
    folder = layout.version_dir(version)
    shutil.copytree(base, folder)
    package = folder / "shelfsync"
    for relative in OVERLAY:
        source, target = SRC / relative, package / relative
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copyfile(source, target)
    # server.py and api/app.py: m1b.1's versions with this task's wiring added (what integration will merge)
    server = package / "server.py"
    replace(
        server,
        "from shelfsync.db.connection import connect\nfrom shelfsync.db.migrate import MigrationError, migrate\n",
        "from shelfsync.db.backup import migrate_with_backup\nfrom shelfsync.db.connection import connect\n"
        "from shelfsync.db.migrate import MigrationError\n",
    )
    replace(server, "        migrate(connection)\n", "        migrate_with_backup(connection, paths)\n")
    replace(
        server,
        "serve(create_app(port, install_token, ui_dir=ui), sock)",
        "serve(create_app(port, install_token, ui_dir=ui, updates=build_update_service(paths, secrets)), sock)",
    )
    replace(
        server,
        "from shelfsync.tray.instance import",
        "from shelfsync.update.service import build_update_service\nfrom shelfsync.tray.instance import",
    )
    app_py = package / "api" / "app.py"
    shutil.copyfile(SRC / "api" / "app.py", app_py)
    replace(
        app_py,
        'UI_DIR = Path(__file__).resolve().parents[3] / "frontend" / "dist"',
        "from shelfsync.paths import source_ui_dir\n\nUI_DIR = source_ui_dir()",
    )
    replace(package / "__init__.py", '__version__ = "0.1.0"', f'__version__ = "{version}"')
    replace(
        package / "update" / "release_key.py",
        "PUBLIC_KEY: bytes | None = None",
        f"PUBLIC_KEY: bytes | None = bytes.fromhex('{public_bytes(app_key).hex()}')",
    )
    replace(package / "update" / "service.py", "FIRST_CHECK_SECONDS = 60.0", "FIRST_CHECK_SECONDS = 3.0e6")
    replace(package / "platform" / "secrets.py", 'SERVICE_NAME = "ShelfSync"', f'SERVICE_NAME = "{service}"')
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
    migrations = package / "db" / "migrations"
    for name, sql in extra_migrations.items():
        (migrations / name).write_text(sql, encoding="utf-8", newline="")
    site = folder / "Lib" / "site-packages"
    venv_site = Path(sys.prefix) / "Lib" / "site-packages"
    for name in ("cryptography", "cffi", "pycparser"):
        shutil.copytree(venv_site / name, site / name, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
    for found in venv_site.glob("_cffi_backend*"):
        shutil.copyfile(found, site / found.name)
    for pycache in package.rglob("__pycache__"):
        shutil.rmtree(pycache)
    targets = [str(package)] + [str(site / name) for name in ("cryptography", "cffi", "pycparser")]
    subprocess.run(
        [str(folder / "python.exe"), "-m", "compileall", "-q", "-f", "--invalidation-mode", "checked-hash", *targets],
        check=True,
        env={k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")},
    )
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
    def __init__(self, layout: InstallLayout, paths: DataPaths, service: str, env: dict[str, str]) -> None:
        self.layout, self.paths, self.service, self.env = layout, paths, service, env
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
        assert found is not None
        base = f"http://127.0.0.1:{found[0]}"
        token = KeyringSecretStore(service=self.service).get(INSTALL_TOKEN_NAME)
        client = httpx.Client(base_url=base, trust_env=False, timeout=120.0)
        ticket = client.post("/api/session/ticket", headers={"Authorization": f"Bearer {token}"}).json()["ticket"]
        client.post(
            "/api/session", json={"ticket": ticket}, headers={"Origin": base, **ORIGIN_HEADERS}
        ).raise_for_status()
        client.headers.update({"Origin": base, **ORIGIN_HEADERS})
        try:
            yield client
        finally:
            client.close()

    def stop(self) -> None:
        found = self.runtime()
        if found is not None:
            self.processes.terminate_pid(found[1])


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
        lambda s: __import__("dataclasses").replace(
            s, pending=PendingUpdate(version, str(layout.version_dir(version)), now_iso())
        )
    )


# ---- the sequence --------------------------------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    if args.work.exists() and any(args.work.iterdir()):
        raise SystemExit("--work must be an empty or new folder")
    layout = InstallLayout(args.work / "Programs" / "ShelfSync")
    paths = DataPaths(args.work / "data")
    paths.root.mkdir(parents=True)
    service = f"ShelfSyncRehearsal-{uuid.uuid4().hex[:8]}"
    key, wrong = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME", "SHELFSYNC_INSTALL_DIR")}
    env["SHELFSYNC_DATA_DIR"] = str(paths.root)
    app = App(layout, paths, service, env)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY_PATH) as throwaway:  # the throwaway uninstall key
        winreg.SetValueEx(throwaway, "DisplayName", 0, winreg.REG_SZ, "ShelfSync (rehearsal)")
        winreg.SetValueEx(throwaway, "DisplayVersion", 0, winreg.REG_SZ, "0.0.1")
    links = WindowsJunctions()
    try:
        say("Building the fake versions (a copy of the embedded build each, overlaid and signed with a throwaway key)")
        build_version(layout, args.base, "0.0.1", 1, key, key, service, {})
        build_version(layout, args.base, "0.0.2", 2, key, key, service, {"0002_rehearsal.sql": MIGRATION_2})
        links.create(layout.current, layout.version_dir("0.0.1"))

        say("\n1. Install 0.0.1")
        app.start()
        check("0.0.1 starts and answers /api/health as 0.0.1", app.wait_version("0.0.1", 90))
        check("the database is at schema 1", database_schema(paths.database) == 1)
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
        check("the database moved to schema 2", database_schema(paths.database) == 2)
        check(
            "DisplayVersion in the throwaway uninstall key is 0.0.2",
            display_version() == "0.0.2",
            str(display_version()),
        )
        backups = sorted(paths.backups.glob("pre-migration-0001-to-0002-*.db"))
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
        check("the database is back at schema 1 (the backup was restored)", database_schema(paths.database) == 1)
        check("DisplayVersion is 0.0.1 again", display_version() == "0.0.1", str(display_version()))
        check(
            "a pre-rollback snapshot of the schema-2 database was kept",
            len(list(paths.backups.glob("pre-rollback-0.0.2-*.db"))) == 1,
        )
        check(
            "both version folders are still there",
            layout.version_dir("0.0.1").is_dir() and layout.version_dir("0.0.2").is_dir(),
        )

        say("\n4. A tampered 0.0.3 is refused")
        # built only now: a switch prunes every version but the two it keeps, so an earlier one would be gone
        build_version(layout, args.base, "0.0.3", 2, wrong, key, service, {"0002_rehearsal.sql": MIGRATION_2})
        found = app.runtime()
        pid_before = found[1] if found else 0
        stage(layout, paths, "0.0.3")
        with app.client() as client:
            wrong_key = client.post("/api/updates/install")
        check("0.0.3 is signed by another key: install answers 409 manifest_invalid",
              wrong_key.status_code == 409 and wrong_key.json() == {"error": "manifest_invalid"},
              f"{wrong_key.status_code} {wrong_key.text}")  # fmt: skip
        write_manifest(layout, layout.version_dir("0.0.3"), "0.0.3", 2, key)  # properly signed now ...
        (layout.version_dir("0.0.3") / "pythonw.exe").write_bytes(
            b"swapped after the download"
        )  # ... but a file changed
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
            layout, args.base, "0.0.4", 3, key, key, service,
            {"0002_rehearsal.sql": MIGRATION_2, "0003_broken.sql": MIGRATION_3_BROKEN},
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
            "the database is unchanged by the failed migration (schema 1, no half-done table)",
            database_schema(paths.database) == 1,
        )
        check(
            "DisplayVersion went to 0.0.4 and back: it is 0.0.1", display_version() == "0.0.1", str(display_version())
        )
        with app.client() as client:
            status = client.get("/api/updates").json()
        check("the last result is reported through GET /api/updates", status["last_result"]["outcome"] == "kept_old")
    finally:
        time.sleep(6.0)  # the plain launcher a switch starts (a second launch) must finish before the app is stopped
        app.stop()
        time.sleep(2.0)
        # whatever is still running from the throwaway folder (nothing, normally) goes too, so the folder can be removed
        subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                f"Get-Process | Where-Object {{ $_.Path -like '{args.work}\\*' }} | Stop-Process -Force",
            ],
            check=False,
        )  # fmt: skip
        time.sleep(1.0)
        for path in (UNINSTALL_KEY_PATH, UNINSTALL_PARENT):  # the throwaway uninstall key goes, children first
            with contextlib.suppress(OSError):
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
        try:
            KeyringSecretStore(service=service).delete(INSTALL_TOKEN_NAME)
        except Exception as error:
            say(f"(the throwaway Credential Manager entry could not be removed: {type(error).__name__})")
        if layout.current.exists() or os.path.lexists(layout.current):
            with contextlib.suppress(Exception):
                links.remove(layout.current)
        keep = REPO / ".logs" / "rehearsal"  # what a failed run needs: the app's log and the updater's two files
        shutil.rmtree(keep, ignore_errors=True)
        for source in (paths.logs, UpdatePaths(paths).root):
            if source.exists():
                shutil.copytree(
                    source, keep / source.name, ignore=shutil.ignore_patterns("downloads"), dirs_exist_ok=True
                )
        shutil.rmtree(args.work, ignore_errors=True)
    failed = [name for name, ok, _ in steps if not ok]
    say(f"\n{len(steps) - len(failed)} of {len(steps)} checks passed")
    for name in failed:
        say(f"FAILED: {name}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
