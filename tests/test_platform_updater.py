"""04-A V39, V43: the link, process and uninstall-entry adapters, on the pieces that run on any system. The Windows
parts (a real junction, a detached child that survives its parent, the registry) are in test_updater_windows.py."""

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from shelfsync.platform.junction import LinkError, SymlinkLinks, WindowsJunctions, default_links
from shelfsync.platform.process import RealProcesses, default_processes
from shelfsync.platform.uninstall_entry import MemoryUninstallEntry, RegistryUninstallEntry, default_uninstall_entry


def can_symlink(tmp_path: Path) -> bool:
    try:
        os.symlink(tmp_path, tmp_path / "probe", target_is_directory=True)
    except OSError:
        return False
    (tmp_path / "probe").unlink()
    return True


def test_symlink_links_make_rename_and_remove_only_links(tmp_path: Path) -> None:
    if not can_symlink(tmp_path):
        pytest.skip("this account can't make symlinks")
    links = SymlinkLinks()
    target, other = tmp_path / "a", tmp_path / "b"
    target.mkdir()
    other.mkdir()
    (target / "keep.txt").write_text("x", encoding="utf-8")
    link = tmp_path / "current"
    links.create(link, target)
    assert links.exists(link) and links.target(link) == target
    links.rename(link, tmp_path / "old")
    assert not links.exists(link) and links.target(tmp_path / "old") == target
    links.remove(tmp_path / "old")
    assert target.is_dir() and (target / "keep.txt").exists()  # the target is never touched
    with pytest.raises(LinkError):
        links.remove(target)  # a real folder is refused
    with pytest.raises(LinkError):
        links.rename(target, tmp_path / "x")
    with pytest.raises(LinkError):
        links.create(tmp_path / "bad", tmp_path / "missing")
    assert links.target(target) is None and links.target(tmp_path / "nothing") is None


def test_a_link_cannot_be_renamed_over_something(tmp_path: Path) -> None:
    if not can_symlink(tmp_path):
        pytest.skip("this account can't make symlinks")
    links = SymlinkLinks()
    (tmp_path / "t").mkdir()
    (tmp_path / "taken").mkdir()
    links.create(tmp_path / "l", tmp_path / "t")
    with pytest.raises(LinkError):
        links.rename(tmp_path / "l", tmp_path / "taken")


@pytest.mark.skipif(sys.platform == "win32", reason="the other systems refuse")
def test_junctions_are_windows_only() -> None:
    with pytest.raises(LinkError):
        WindowsJunctions().create(Path("/x/current"), Path("/x/target"))


def test_a_junction_path_with_command_characters_is_refused(tmp_path: Path) -> None:
    (tmp_path / "t").mkdir()
    for bad in ("a&b", "a%PATH%b", 'a"b', "a^b", "a|b", "a<b", "a!b"):
        with pytest.raises(LinkError):
            WindowsJunctions().create(tmp_path / bad, tmp_path / "t")


def test_junction_helpers_refuse_what_is_not_a_link(tmp_path: Path) -> None:
    folder = tmp_path / "real"
    folder.mkdir()
    adapter = WindowsJunctions()
    with pytest.raises(LinkError):
        adapter.remove(folder)
    with pytest.raises(LinkError):
        adapter.rename(folder, tmp_path / "other")
    assert adapter.target(folder) is None and adapter.exists(folder) and folder.is_dir()


def test_the_default_adapters_are_the_system_ones() -> None:
    assert isinstance(default_links(), WindowsJunctions if sys.platform == "win32" else SymlinkLinks)
    assert isinstance(default_processes(), RealProcesses)
    assert isinstance(default_uninstall_entry(), RegistryUninstallEntry)


def test_the_memory_uninstall_entry_writes_only_a_version_and_only_into_a_key_that_exists() -> None:
    entry = MemoryUninstallEntry(present=False)
    assert entry.set_display_version("0.0.2") is False and entry.display_version is None
    entry = MemoryUninstallEntry()
    assert entry.set_display_version("0.0.2") and entry.display_version == "0.0.2"
    with pytest.raises(ValueError):
        entry.set_display_version("not a version")


@pytest.mark.skipif(sys.platform == "win32", reason="the registry is the Windows adapter's job (see the windows tests)")
def test_off_windows_there_is_no_registry_to_write() -> None:
    assert RegistryUninstallEntry().set_display_version("0.0.2") is False
    with pytest.raises(ValueError):
        RegistryUninstallEntry().set_display_version("x")


def test_a_real_child_is_started_watched_and_ended(tmp_path: Path) -> None:
    processes = RealProcesses()
    child = processes.spawn_detached([sys.executable, "-c", "import time; time.sleep(60)"], tmp_path)
    try:
        assert child.poll() is None and processes.is_running(child.pid)
        assert child.wait(0.1) is None
        child.terminate()
        assert child.wait(10) is not None
        assert child.poll() is not None
        assert not processes.is_running(child.pid)
    finally:
        child.kill()


def test_a_child_that_exits_reports_its_code(tmp_path: Path) -> None:
    child = RealProcesses().spawn_detached([sys.executable, "-c", "raise SystemExit(7)"], tmp_path)
    assert child.wait(20) == 7 and child.poll() == 7


def test_the_child_gets_the_environment_it_is_given_and_no_console_input(tmp_path: Path) -> None:
    out = tmp_path / "out.txt"
    code = "import os, sys; open(sys.argv[1], 'w').write(os.environ['SHELF_TEST'] + ':' + repr(sys.stdin.read()))"
    child = RealProcesses().spawn_detached(
        [sys.executable, "-c", code, str(out)], tmp_path, {**os.environ, "SHELF_TEST": "yes"}
    )
    assert child.wait(20) == 0
    assert out.read_text(encoding="utf-8") == "yes:''"


def test_is_running_is_false_for_pids_that_cannot_be_a_process() -> None:
    processes = RealProcesses()
    assert processes.is_running(0) is False and processes.is_running(-3) is False
    processes.terminate_pid(0)
    processes.terminate_pid(os.getpid())  # never ends this process


def test_terminate_pid_ends_another_process(tmp_path: Path) -> None:
    sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        RealProcesses().terminate_pid(sleeper.pid)
        deadline = time.monotonic() + 10
        while sleeper.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        assert sleeper.poll() is not None
    finally:
        sleeper.kill()
