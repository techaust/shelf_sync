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
    folder_python = arguments.folder.resolve() / "python.exe"
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
    folder: Path = arguments.folder.resolve()
    before = {e.path: (e.size, e.sha256) for e in build.file_listing(folder)}  # type: ignore[attr-defined]

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
    after = {e.path: (e.size, e.sha256) for e in build.file_listing(folder)}  # type: ignore[attr-defined]
    differences = changes(before, after)
    if differences:
        sys.stderr.write("The folder changed during the first start (V47):\n" + "\n".join(differences[:40]) + "\n")
        return 1
    sys.stdout.write(f"Smoke test passed: version {arguments.version} answered, UI served, folder unchanged\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
