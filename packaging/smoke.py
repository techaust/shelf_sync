"""Smoke test of the built folder: `python -I packaging/smoke.py build/ShelfSync-<v> --version <v>` (SYS-01, V38, V47).

Starts the folder's own `python.exe` running the server (no tray) with a throwaway `SHELFSYNC_DATA_DIR`, then
checks that `/api/health` answers with the right version, that `/` serves the folder's `ui/index.html`, and
that afterwards nothing under the folder has changed: no file added, removed or rewritten, so a first start leaves
the folder matching `files.txt` (V47: the precompiled `checked-hash` caches are enough). Nothing is read from or
written to the real data folder or the Run key, and by default not to Credential Manager either (an in-memory
store); CI adds `--real-secrets` to run the real `python -m shelfsync`.
Run it with the Python that built the folder, not the folder's own.
"""

import argparse
import contextlib
import importlib.util
import json
import os
import subprocess  # nosec B404 - starts the built python.exe with a fixed argument list
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from pathlib import Path

START_SECONDS = 60.0

# The same start-up as `python -m shelfsync`, with an in-memory secret store: nothing reaches the PC's Credential
# Manager. CI (a throwaway runner) passes --real-secrets to run the real entry and prove keyring imports.
MEMORY_STORE_ENTRY = (
    "from shelfsync import server; from shelfsync.platform.notify import LogNotifier; "
    "from shelfsync.platform.secrets import MemorySecretStore; "
    "raise SystemExit(server.run_application(lambda paths: server.serve_with_uvicorn, LogNotifier(), "
    "server._already_running, secrets=MemorySecretStore()))"
)

# What the installed copy runs at sign-in, `pythonw -m shelfsync.launcher --background`: `shelfsync.tray.launcher.main`
# with the real exit guard from `shelfsync.launcher` (only that module's own `__main__` line is not run), plus one
# addition: a thread
# that waits for `quit.flag` in the data folder and then calls `app.state.request_quit()`, the way the updater asks the
# tray to quit, so the run ends cleanly and headless (there is no menu to click). SECRETS is replaced below.
LAUNCHER_ENTRY = """
import threading, time
import shelfsync.launcher as entry
from shelfsync.paths import resolve_data_paths
from shelfsync.platform.secrets import MemorySecretStore
from shelfsync.tray import launcher
flag = resolve_data_paths().root / "quit.flag"
original = launcher.TrayServe.__call__
def call(self, app, sock):
    def watch():
        while not flag.exists():
            time.sleep(0.2)
        app.state.request_quit()
    threading.Thread(target=watch, daemon=True).start()
    return original(self, app, sock)
launcher.TrayServe.__call__ = call
raise SystemExit(launcher.main(["--background"], secrets=SECRETS, make_exit_guard=entry.make_real_exit_guard))
"""

# Import the launcher and load every tray icon from the folder itself (the class of miss that shipped no icons).
ICONS_PROBE = """
from shelfsync.paths import tray_icon_dir
from shelfsync.tray import launcher
from shelfsync.tray.icons import icon_file, load_icon
from shelfsync.tray.state import IconState
folder = tray_icon_dir()
count = 0
for state in IconState:
    for light in (True, False):
        path = icon_file(state, light)
        assert path.parent == folder and path.is_file(), path
        load_icon(path, 16).close()
        count += 1
print(count)
"""

# The backup export's key derivation (SET-05, 04-A V21, R6): the folder's own Python must have scrypt in its OpenSSL and
# accept the 256 MiB memory limit (about 128 MiB are used at N = 2**17; the default limit would refuse). A failure
# prints nothing, so the check below fails.
SCRYPT_PROBE = (
    "import hashlib; "
    "print(len(hashlib.scrypt(b'x', salt=b'0' * 16, n=2**17, r=8, p=1, maxmem=256 * 1024 * 1024, dklen=32)))"
)


def load_build() -> object:
    spec = importlib.util.spec_from_file_location("shelfsync_packaging_build", Path(__file__).with_name("build.py"))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def changes(before: dict[str, tuple[int, str]], after: dict[str, tuple[int, str]]) -> list[str]:
    """What differs between two listings: `added`, `removed` and `changed` paths."""
    found = [f"added: {path}" for path in sorted(after.keys() - before.keys())]
    found += [f"removed: {path}" for path in sorted(before.keys() - after.keys())]
    found += [f"changed: {path}" for path in sorted(before.keys() & after.keys()) if before[path] != after[path]]
    return found


def get(url: str) -> tuple[int, bytes]:
    if not url.startswith("http://127.0.0.1:"):
        raise ValueError("loopback only")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # no proxy: this is 127.0.0.1
    try:
        with opener.open(url, timeout=10) as response:  # nosec B310 - the scheme and host are checked above
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def wait_for_port(runtime_json: Path, process: subprocess.Popen[bytes]) -> int:
    deadline = time.monotonic() + START_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise SystemExit(f"ShelfSync exited with code {process.returncode} before it was listening")
        try:
            return int(json.loads(runtime_json.read_text(encoding="utf-8"))["port"])
        except OSError, ValueError, KeyError:
            time.sleep(0.25)
    raise SystemExit("ShelfSync didn't write runtime.json in time")


def run_launcher(folder: Path, data: Path, real_secrets: bool, version: str) -> None:
    """Start the folder's `pythonw -m shelfsync.launcher --background` (with the quit thread above), check it answers
    /api/health with the right version, then ask it to quit through `request_quit` and require exit code 0 and no
    runtime.json left. Raises SystemExit with a message on any failure."""
    secrets = "None" if real_secrets else "MemorySecretStore()"
    environment = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
    environment["SHELFSYNC_DATA_DIR"] = str(data)
    process = subprocess.Popen(  # nosec B603
        [str(folder / "pythonw.exe"), "-c", LAUNCHER_ENTRY.replace("SECRETS", secrets)],
        cwd=folder,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        port = wait_for_port(data / "runtime.json", process)
        status, body = get(f"http://127.0.0.1:{port}/api/health")
        if status != 200 or json.loads(body) != {"app": "shelfsync", "version": version}:
            raise SystemExit(f"The launcher answered /api/health with {status} {body!r}")
        (data / "quit.flag").write_text("quit", encoding="utf-8")
        try:
            code = process.wait(timeout=45)
        except subprocess.TimeoutExpired:
            raise SystemExit("The launcher didn't quit within 45 s after request_quit") from None
        if code != 0:
            raise SystemExit(f"The launcher exited with code {code}, not 0, after request_quit")
        if (data / "runtime.json").exists():
            raise SystemExit("The launcher left runtime.json behind")
    finally:
        if process.poll() is None:
            process.kill()
            with contextlib.suppress(subprocess.TimeoutExpired):  # reap it so the data folder can be removed
                process.wait(timeout=10)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument(
        "--real-secrets",
        action="store_true",
        help="run `python -m shelfsync` with the real Credential Manager (CI's throwaway runner only)",
    )
    arguments = parser.parse_args(argv)
    build = load_build()
    folder: Path = arguments.folder.resolve()
    folder_python = folder / "python.exe"
    # The listing is taken before ANY probe runs, so a `__pycache__` written by the isolation or icon probe is caught
    # by the "folder unchanged" check at the end (V47).
    before = {e.path: (e.size, e.sha256) for e in build.file_listing(folder)}  # type: ignore[attr-defined]
    # python314._pth puts the interpreter in isolated mode: neither PYTHONPATH nor the working folder is on sys.path,
    # so nothing loads from wherever a shortcut or the Run key happens to start it.
    probe = subprocess.run(  # nosec B603
        [str(folder_python), "-c", "import sys; print(sys.flags.isolated, sys.flags.safe_path)"],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    if probe.stdout.split() != ["1", "True"]:
        sys.stderr.write(f"The built Python isn't isolated (isolated, safe_path = {probe.stdout.strip()})\n")
        return 1
    icons = subprocess.run(  # nosec B603
        [str(folder_python), "-c", ICONS_PROBE], capture_output=True, text=True, timeout=120, check=False
    )
    if icons.returncode != 0 or icons.stdout.strip() != "6":
        sys.stderr.write(f"The launcher or a tray icon can't be loaded from the built folder:\n{icons.stderr[-800:]}\n")
        return 1
    scrypt = subprocess.run(  # nosec B603
        [str(folder_python), "-c", SCRYPT_PROBE], capture_output=True, text=True, timeout=120, check=False
    )
    if scrypt.returncode != 0 or scrypt.stdout.strip() != "32":
        sys.stderr.write(f"The built Python can't derive a backup key (hashlib.scrypt):\n{scrypt.stderr[-800:]}\n")
        return 1

    with tempfile.TemporaryDirectory(prefix="shelfsync-smoke-") as data:
        environment = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
        environment["SHELFSYNC_DATA_DIR"] = str(Path(data) / "ShelfSync")
        entry = ["-m", "shelfsync"] if arguments.real_secrets else ["-c", MEMORY_STORE_ENTRY]
        process = subprocess.Popen(  # nosec B603
            [str(folder / "python.exe"), *entry],
            cwd=folder,
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            port = wait_for_port(Path(data) / "ShelfSync" / "runtime.json", process)
            status, body = get(f"http://127.0.0.1:{port}/api/health")
            health = json.loads(body)
            assert status == 200 and health == {"app": "shelfsync", "version": arguments.version}, (status, health)
            status, page = get(f"http://127.0.0.1:{port}/")
            assert status == 200 and page == (folder / "ui" / "index.html").read_bytes(), "/ isn't ui/index.html"
        finally:
            process.terminate()
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                with contextlib.suppress(subprocess.TimeoutExpired):
                    process.wait(timeout=10)
    with tempfile.TemporaryDirectory(prefix="shelfsync-smoke-launcher-") as data:
        run_launcher(folder, Path(data) / "ShelfSync", arguments.real_secrets, arguments.version)
    after = {e.path: (e.size, e.sha256) for e in build.file_listing(folder)}  # type: ignore[attr-defined]
    differences = changes(before, after)
    if differences:
        sys.stderr.write("The folder changed during the first start (V47):\n" + "\n".join(differences[:40]) + "\n")
        return 1
    sys.stdout.write(
        f"Smoke test passed: version {arguments.version} answered, UI served, the tray icons load, the launcher"
        " started and quit through request_quit, folder unchanged\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
