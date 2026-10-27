"""04-A V39, V42, V43, V44, 06 section 3: the updater's Windows parts, with the real junction, process, registry
and Credential Manager adapters, on THROWAWAY names and folders only. Run on purpose with
`uv run pytest -m windows --no-cov`
(and by the owner in Windows PowerShell outside the Claude app, whose private %LOCALAPPDATA% and registry view change
what some of these can show: V36, V42, V43)."""

import json
import os
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from shelfsync.paths import DataPaths, write_runtime_json
from shelfsync.platform.junction import WindowsJunctions
from shelfsync.platform.process import RealProcesses
from shelfsync.platform.secrets import KeyringSecretStore
from shelfsync.platform.sockets import expected_images, normalize_image, process_info
from shelfsync.platform.uninstall_entry import RegistryUninstallEntry
from shelfsync.update.layout import InstallLayout
from shelfsync.update.service import GITHUB_TOKEN_ENTRY, UpdateService
from shelfsync.update.switch import HealthProbe, current_version, repair_current, repoint, version_images

pytestmark = [pytest.mark.windows, pytest.mark.skipif(sys.platform != "win32", reason="Windows only")]

TOKEN = "github_pat_" + "Wx3Yz4Ab5C" * 4


@pytest.fixture
def layout(tmp_path: Path) -> InstallLayout:
    """A throwaway install root with two version folders, each holding one file."""
    layout = InstallLayout(tmp_path / "Programs" / "ShelfSync")
    for version in ("0.0.1", "0.0.2"):
        folder = layout.version_dir(version)
        folder.mkdir(parents=True)
        (folder / "marker.txt").write_text(version, encoding="utf-8")
    return layout


# ---- V39: a real junction and the rename sequence -------------------------------------------------


def test_v39_a_junction_is_made_without_admin_and_points_at_the_version(layout: InstallLayout) -> None:
    links = WindowsJunctions()
    links.create(layout.current, layout.version_dir("0.0.1"))
    assert os.path.isjunction(layout.current)
    assert (layout.current / "marker.txt").read_text(encoding="utf-8") == "0.0.1"
    assert current_version(layout, links) == "0.0.1"


def test_v39_the_rename_sequence_switches_current_and_never_touches_a_version_folder(layout: InstallLayout) -> None:
    links = WindowsJunctions()
    links.create(layout.current, layout.version_dir("0.0.1"))
    repoint(layout, links, "0.0.2")
    assert (layout.current / "marker.txt").read_text(encoding="utf-8") == "0.0.2"
    assert not links.exists(layout.current_old) and not links.exists(layout.current_next)
    assert (layout.version_dir("0.0.1") / "marker.txt").read_text(encoding="utf-8") == "0.0.1"  # the old one is intact
    repoint(layout, links, "0.0.1")
    assert current_version(layout, links) == "0.0.1"


def test_v39_a_current_left_missing_between_the_two_renames_is_repaired(layout: InstallLayout) -> None:
    links = WindowsJunctions()
    links.create(layout.current, layout.version_dir("0.0.1"))
    links.create(layout.current_next, layout.version_dir("0.0.2"))
    links.rename(layout.current, layout.current_old)  # the first rename done, the process "killed" here
    assert not links.exists(layout.current)
    assert repair_current(layout, links) is True
    assert current_version(layout, links) == "0.0.1" and not links.exists(layout.current_next)


def test_v39_removing_a_junction_removes_the_link_and_not_what_it_points_at(layout: InstallLayout) -> None:
    links = WindowsJunctions()
    links.create(layout.current, layout.version_dir("0.0.1"))
    links.remove(layout.current)
    assert not layout.current.exists() and (layout.version_dir("0.0.1") / "marker.txt").is_file()
    with pytest.raises(Exception):  # noqa: B017  # a real folder is refused (LinkError)
        links.remove(layout.version_dir("0.0.1"))
    assert layout.version_dir("0.0.1").is_dir()


def test_v39_a_junction_is_renamed_and_an_occupied_name_is_refused(layout: InstallLayout) -> None:
    links = WindowsJunctions()
    links.create(layout.current, layout.version_dir("0.0.1"))
    links.rename(layout.current, layout.current_old)
    assert links.exists(layout.current_old) and not links.exists(layout.current)
    links.create(layout.current, layout.version_dir("0.0.2"))
    with pytest.raises(Exception):  # noqa: B017
        links.rename(layout.current, layout.current_old)  # taken


# ---- V43: a detached child outlives its parent ----------------------------------------------------


def test_v43_a_detached_child_survives_the_exit_of_the_process_that_started_it(tmp_path: Path) -> None:
    pid_file = tmp_path / "child.pid"
    parent = (
        "import sys, time\n"
        "from pathlib import Path\n"
        "from shelfsync.platform.process import RealProcesses\n"
        "sleeper = [sys.executable, '-c', 'import time; time.sleep(60)']\n"
        "child = RealProcesses().spawn_detached(sleeper, Path(sys.argv[1]).parent)\n"
        "Path(sys.argv[1]).write_text(str(child.pid))\n"
    )
    environment = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "backend")}
    completed = subprocess.run([sys.executable, "-c", parent, str(pid_file)], env=environment, timeout=60, check=True)
    assert completed.returncode == 0
    child_pid = int(pid_file.read_text(encoding="utf-8"))
    processes = RealProcesses()
    try:
        time.sleep(1.0)  # the parent has exited by now
        assert processes.is_running(child_pid)
    finally:
        processes.terminate_pid(child_pid)
    deadline = time.monotonic() + 10
    while processes.is_running(child_pid) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not processes.is_running(child_pid)


# ---- V44: the image path of a program started through the junction --------------------------------


def test_v44_a_program_started_through_the_junction_is_recognised_whichever_path_windows_reports(
    layout: InstallLayout,
) -> None:
    base = Path(getattr(sys, "_base_executable", sys.executable))
    version_dir = layout.version_dir("0.0.1")
    for name in ("python.exe", "pythonw.exe"):
        (version_dir / name).write_bytes((base.parent / name).read_bytes())  # real interpreters, copied
    for dll in base.parent.glob("*.dll"):
        (version_dir / dll.name).write_bytes(dll.read_bytes())
    links = WindowsJunctions()
    links.create(layout.current, version_dir)
    environment = {**os.environ, "PYTHONHOME": str(base.parent)}
    child = RealProcesses().spawn_detached(
        [str(layout.current / "python.exe"), "-c", "import time; time.sleep(30)"], layout.current, environment
    )
    try:
        deadline = time.monotonic() + 20
        watch = None
        while watch is None and time.monotonic() < deadline:
            watch = RealProcesses().watch(child.pid)
            time.sleep(0.1)
        assert watch is not None
        try:
            reported = watch.image
            assert reported is not None
            # the same program, named through the junction or through its folder: both are accepted by the health check
            assert normalize_image(reported) in version_images(layout, "0.0.1")
            sockets_view = process_info(child.pid).image
            assert normalize_image(sockets_view) in version_images(layout, "0.0.1")
            print(f"V44: image reported {reported!r} for a program started as {str(layout.current / 'python.exe')!r}")
        finally:
            watch.close()
    finally:
        child.kill()


# ---- the real health probe: the real owner check against a stub that is this very process ---------


class _Health(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = json.dumps({"app": "shelfsync", "version": "9.9.9"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return None


@pytest.fixture
def stub_server() -> Iterator[HTTPServer]:
    server = HTTPServer(("127.0.0.1", 47617), _Health)  # inside ShelfSync's port range, which read_runtime requires
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def test_the_real_probe_trusts_the_owner_check_with_explicit_images(tmp_path: Path, stub_server: HTTPServer) -> None:
    paths = DataPaths(tmp_path / "data")
    paths.root.mkdir()
    write_runtime_json(paths, stub_server.server_address[1], os.getpid())
    probe = HealthProbe()
    assert probe.probe(paths, os.getpid(), "9.9.9", expected_images()) is None
    assert probe.probe(paths, os.getpid(), "9.9.8", expected_images()) == "wrong_version"
    nothing_like_us = frozenset({normalize_image(r"C:\Windows\System32\notepad.exe")})
    assert probe.probe(paths, os.getpid(), "9.9.9", nothing_like_us) == "untrusted_listener"  # not the target's Python
    assert probe.probe(paths, os.getpid() + 1, "9.9.9", expected_images()) == "no_answer"  # runtime.json names another


# ---- the registry (V42) ---------------------------------------------------------------------------


def test_display_version_is_written_to_a_throwaway_key_and_never_created(tmp_path: Path) -> None:
    import winreg

    path = rf"Software\ShelfSyncTest-{uuid.uuid4().hex}\Uninstall"
    entry = RegistryUninstallEntry(path)
    assert entry.set_display_version("0.0.2") is False  # the key doesn't exist: nothing is created
    with pytest.raises(FileNotFoundError):
        winreg.OpenKey(winreg.HKEY_CURRENT_USER, path)
    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, path)
    try:
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, "ShelfSync (test)")
        assert entry.set_display_version("0.0.2") is True
        assert winreg.QueryValueEx(key, "DisplayVersion") == ("0.0.2", winreg.REG_SZ)
        assert winreg.QueryValueEx(key, "DisplayName")[0] == "ShelfSync (test)"  # nothing else was touched
        assert entry.set_display_version("0.0.3") is True
        assert winreg.QueryValueEx(key, "DisplayVersion")[0] == "0.0.3"
    finally:
        winreg.CloseKey(key)
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
        parent = path.rsplit("\\", 1)[0]
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, parent)


# ---- Credential Manager: the github-token round trip under a throwaway service ----------


def test_the_github_token_round_trips_through_credential_manager_and_is_never_in_a_response(tmp_path: Path) -> None:
    store = KeyringSecretStore(service=f"ShelfSyncTest-{uuid.uuid4().hex}")
    service = UpdateService.development(store)
    try:
        assert service.token_status().is_set is False
        service.set_token(TOKEN)
        assert store.get(GITHUB_TOKEN_ENTRY) == TOKEN
        status = service.token_status()
        assert status.is_set is True and TOKEN not in repr(status)
        service.set_token("github_pat_" + "Qw1Er2Ty3U" * 4)  # replaced, not duplicated
        assert store.get(GITHUB_TOKEN_ENTRY) == "github_pat_" + "Qw1Er2Ty3U" * 4
    finally:
        service.delete_token()
    assert store.get(GITHUB_TOKEN_ENTRY) is None and service.token_status().is_set is False
