"""M1b.1: `--background`, `request_quit` for the updater, the data-folder lock, the AUMID choice and the UI folder."""

import secrets
import subprocess
import sys
import time
from pathlib import Path

import pytest

from shelfsync import server
from shelfsync.paths import DataPaths, UiMissingError, is_packaged_layout, source_ui_dir, ui_dir
from shelfsync.platform import aumid, notify
from shelfsync.platform.notify import FakeNotifier
from shelfsync.platform.secrets import MemorySecretStore
from shelfsync.platform.shell import FakeShell
from shelfsync.tray import launcher
from shelfsync.tray.instance import (
    CombinedInstanceLock,
    FakeFileLock,
    FakeInstanceLock,
    WindowsFileLock,
    default_instance_lock,
)
from shelfsync.tray.launcher import TrayServe
from tests.test_launcher import Running, wait_for

# ---- --background (SYS-04) ---------------------------------------------------------------------------------------


def _first_tab_flag(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> bool:
    seen: list[bool] = []
    monkeypatch.setattr(server, "default_instance_lock", lambda: FakeInstanceLock(set()))
    monkeypatch.setattr(launcher.logs, "install_output_guards", lambda: None)
    monkeypatch.setattr(launcher.TrayServe, "__call__", lambda self, app, sock: seen.append(self._open_first_tab))
    code = launcher.main(argv, notifier=FakeNotifier(), shell=FakeShell(), secrets=MemorySecretStore())
    assert code == 0
    (flag,) = seen
    return flag


def test_background_opens_no_first_tab(data_paths: DataPaths, monkeypatch: pytest.MonkeyPatch) -> None:
    """SYS-04: signing in to Windows starts ShelfSync in the tray only."""
    assert _first_tab_flag(monkeypatch, ["--background"]) is False


def test_without_the_flag_the_first_copy_opens_a_tab(data_paths: DataPaths, monkeypatch: pytest.MonkeyPatch) -> None:
    """SYS-02: the shortcuts keep opening a signed-in tab."""
    assert _first_tab_flag(monkeypatch, []) is True


@pytest.mark.parametrize("argv", [["--nope"], ["--background", "extra"], ["--backg"]])
def test_an_unknown_argument_is_an_error_not_ignored(argv: list[str]) -> None:
    """SYS-04: argparse refuses it (exit 2); abbreviations are off."""
    with pytest.raises(SystemExit) as stop:
        launcher.parse_arguments(argv)
    assert stop.value.code == 2


def test_background_first_copy_really_opens_no_tab(data_paths: DataPaths) -> None:
    """SYS-04: the wait loop with `open_first_tab=False` (what `--background` passes) shows the tray and no tab."""
    running = Running(data_paths, open_first_tab=False).start()
    try:
        assert running.shell.urls == []
        assert running.tray.started
    finally:
        running.finish()


# ---- request_quit for m1b.2 -------------------------------------------------------------------------------------


def test_request_quit_is_published_on_the_app_and_quits_like_the_menu(data_paths: DataPaths) -> None:
    """SYS-06 (for m1b.2): `app.state.request_quit()` asks the tray to quit and says so."""
    running = Running(data_paths).start()
    assert running.app.state.request_quit() is True
    running.thread.join(timeout=20)
    assert not running.thread.is_alive()
    assert running.error == []


def test_a_refusing_guard_makes_request_quit_return_false_and_nothing_quits(data_paths: DataPaths) -> None:
    """SYS-06: a quit guard (M5's running upload) refuses; the updater is told and the app keeps running."""
    running = Running(data_paths)
    allow = [False]
    running.serve.add_quit_guard(lambda: allow[0])
    running.start()
    try:
        assert running.app.state.request_quit() is False
        assert running.health() == 200
        assert running.thread.is_alive()
        allow[0] = True
        assert running.app.state.request_quit() is True
    finally:
        running.finish()


def test_the_developer_entry_does_not_publish_request_quit() -> None:
    """SYS-06: m1b.2 answers 409 when it is missing (`python -m shelfsync` has no tray to ask)."""
    from tests.support import make_harness

    assert not hasattr(make_harness(ui_dir=None).app.state, "request_quit")


def test_tray_serve_request_quit_returns_true_with_no_guard(data_paths: DataPaths) -> None:
    """SYS-06."""
    serve = TrayServe(data_paths, FakeNotifier(), FakeShell())
    assert serve.request_quit() is True


# ---- the data-folder lock (SYS-03) -------------------------------------------------------------------------------


def _combined(mutex_taken: set[str], file_taken: set[str]) -> CombinedInstanceLock:
    return CombinedInstanceLock(FakeInstanceLock(mutex_taken), FakeFileLock(file_taken))


def test_both_free_the_lock_is_won_and_both_are_held_until_release() -> None:
    """SYS-03: case 1 of 4."""
    mutex, file = set(), set()
    lock = _combined(mutex, file)
    assert lock.acquire()
    assert lock.acquire()  # asking again is still yes
    assert mutex == {"ShelfSync"} and file == {"instance.lock"}
    lock.release()
    assert mutex == set() and file == set()


def test_the_mutex_taken_means_a_second_launch_and_the_file_is_untouched() -> None:
    """SYS-03: case 2: another copy in this session."""
    mutex, file = {"ShelfSync"}, set()
    assert not _combined(mutex, file).acquire()
    assert file == set()


def test_the_file_taken_means_a_second_launch_and_the_mutex_is_given_back() -> None:
    """SYS-03: case 3: a copy in another logon session of the same user (it holds the file, not our mutex)."""
    mutex, file = set(), {"instance.lock"}
    assert not _combined(mutex, file).acquire()
    assert mutex == set()  # a refused launch holds nothing


def test_both_taken_means_a_second_launch() -> None:
    """SYS-03: case 4."""
    mutex, file = {"ShelfSync"}, {"instance.lock"}
    assert not _combined(mutex, file).acquire()
    assert mutex == {"ShelfSync"} and file == {"instance.lock"}  # the holder's locks are not disturbed


def test_a_file_lock_that_raises_gives_the_mutex_back() -> None:
    """SYS-03: an error opening the file can't leave the name taken."""

    class Broken:
        def acquire(self) -> bool:
            raise OSError("no")

        def release(self) -> None: ...

    mutex: set[str] = set()
    with pytest.raises(OSError):
        CombinedInstanceLock(FakeInstanceLock(mutex), Broken()).acquire()
    assert mutex == set()


def test_the_lock_file_is_instance_lock_in_the_data_folder(data_paths: DataPaths) -> None:
    """SYS-03, SYS-01: the installer and uninstaller try to open this file to tell whether ShelfSync runs."""
    assert data_paths.instance_lock == data_paths.root / "instance.lock"


@pytest.mark.skipif(sys.platform == "win32", reason="the other platforms refuse")
def test_off_windows_the_real_file_lock_refuses_to_pretend(tmp_path: Path) -> None:
    """SYS-03."""
    with pytest.raises(OSError):
        WindowsFileLock(tmp_path / "instance.lock")
    with pytest.raises(OSError):
        default_instance_lock()


@pytest.mark.windows
@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_the_real_lock_file_is_held_across_two_processes_and_freed_when_one_dies(tmp_path: Path) -> None:
    """SYS-03: a second process (any session) can't open it while the first lives; a killed holder leaves no lock."""
    path = tmp_path / "instance.lock"
    holder = subprocess.Popen(
        [
            sys.executable,
            "-I",
            "-c",
            "import sys, time; sys.path.insert(0, sys.argv[2]); "
            "from pathlib import Path; from shelfsync.tray.instance import WindowsFileLock; "
            "lock = WindowsFileLock(Path(sys.argv[1])); "
            "print('held' if lock.acquire() else 'refused', flush=True); time.sleep(60)",
            str(path),
            str(Path(__file__).parents[1] / "backend"),
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "held"
        mine = WindowsFileLock(path)
        assert not mine.acquire()  # the sharing violation: a second launch
        with pytest.raises(OSError):
            path.open("rb")  # nothing else can read it either (the installer's "is it running" test)
        holder.kill()
        holder.wait(timeout=10)
        assert wait_for(mine.acquire, 5)  # no stale lock: Windows closed the handle
        mine.release()
    finally:
        holder.kill()


@pytest.mark.windows
@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_a_folder_in_place_of_the_lock_file_is_never_taken_as_a_lock(tmp_path: Path) -> None:
    """SYS-03: a folder where the file should be is refused (fail closed): this launch is treated as a second one."""
    (tmp_path / "instance.lock").mkdir()
    assert WindowsFileLock(tmp_path / "instance.lock").acquire() is False


# ---- the toast AUMID (SYS-05) -----------------------------------------------------------------------------------


def test_an_installed_copy_with_the_key_uses_shelfsyncs_own_aumid() -> None:
    """SYS-05: `TecHaust.ShelfSync`, registered by the installer."""
    assert notify.toast_aumid(installed=True, registered=True) == "TecHaust.ShelfSync" == aumid.AUMID


def test_a_development_run_or_a_missing_key_keeps_the_m1a_default() -> None:
    """SYS-05: no AUMID (windows-toasts' default); an unregistered AUMID might drop the toast."""
    assert notify.toast_aumid(installed=False, registered=True) is None
    assert notify.toast_aumid(installed=True, registered=False) is None
    assert notify.toast_aumid(installed=False, registered=False) is None


def test_the_key_path_and_off_windows_behaviour() -> None:
    """SYS-05."""
    assert aumid.key_path("TecHaust.ShelfSync") == r"Software\Classes\AppUserModelId\TecHaust.ShelfSync"
    if sys.platform != "win32":
        assert aumid.is_registered() is False
        with pytest.raises(OSError):
            aumid.register("x", "y", "z")
        with pytest.raises(OSError):
            aumid.unregister("x")


def test_show_toast_passes_the_chosen_aumid_to_windows_toasts(monkeypatch: pytest.MonkeyPatch) -> None:
    """SYS-05: `notifierAUMID` is what windows-toasts takes (04-A V41)."""
    import types

    calls: list[tuple[str, str | None]] = []

    class FakeToaster:
        def __init__(self, text: str, notifierAUMID: str | None = None) -> None:
            calls.append((text, notifierAUMID))

        def show_toast(self, toast: object) -> None: ...

    module = types.SimpleNamespace(InteractableWindowsToaster=FakeToaster, Toast=lambda fields: fields)
    monkeypatch.setitem(sys.modules, "windows_toasts", module)
    monkeypatch.setattr(notify, "_toaster", None)
    notify.show_toast(["a"], notifier_aumid="Test.Id")
    monkeypatch.setattr(notify, "_toaster", None)
    monkeypatch.setattr(notify, "is_installed_copy", lambda: False)
    notify.show_toast(["a"])
    assert calls == [("ShelfSync", "Test.Id"), ("ShelfSync", None)]


@pytest.mark.windows
@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_the_aumid_key_is_written_read_and_removed_under_a_throwaway_id() -> None:
    """SYS-05, V41/V42: HKCU\\Software\\Classes\\AppUserModelId\\<id>; only a throwaway id, never the real one."""
    import winreg

    name = f"TecHaust.ShelfSyncTest{secrets.token_hex(5)}"
    assert not aumid.is_registered(name)
    try:
        aumid.register(name, "ShelfSync test", r"C:\nowhere\shelfsync.ico")
        assert aumid.is_registered(name)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, aumid.key_path(name)) as key:
            assert winreg.QueryValueEx(key, "DisplayName")[0] == "ShelfSync test"
            assert winreg.QueryValueEx(key, "IconUri")[0] == r"C:\nowhere\shelfsync.ico"
    finally:
        aumid.unregister(name)
    assert not aumid.is_registered(name)
    aumid.unregister(name)  # removing it twice is fine


@pytest.mark.windows
@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_cold_toast_time_from_process_start_to_a_shown_toast(capfd: pytest.CaptureFixture[str]) -> None:
    """SYS-05, V49: a fresh process shows its first toast well inside the safety exit's 10 s last stage (half is 5 s).
    A throwaway AUMID; the toast is a real one and appears on the desktop for a moment. The time is printed (run with
    -s) and recorded in the run file and 04-A V49; it fails only above 10 s."""
    name = f"TecHaust.ShelfSyncTest{secrets.token_hex(5)}"
    aumid.register(name, "ShelfSync test", r"C:\nowhere\shelfsync.ico")
    try:
        code = (
            "import sys, time; sys.path.insert(0, sys.argv[1]); "
            "from shelfsync.platform import notify; "
            "notify.show_toast(['ShelfSync timing check', 'This is a test toast.'], notifier_aumid=sys.argv[2]); "
            "print(time.time(), flush=True)"
        )
        started = time.time()
        done = subprocess.run(
            [sys.executable, "-I", "-c", code, str(Path(__file__).parents[1] / "backend"), name],
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
        shown = float(done.stdout.strip().splitlines()[-1])
        elapsed = shown - started
        with capfd.disabled():
            sys.stdout.write(f"\nCOLD TOAST: {elapsed:.2f} s from process start to a shown toast\n")
        assert 0 < elapsed < 10
    finally:
        aumid.unregister(name)


# ---- the UI folder (UI-SHELL, SYS-01) ---------------------------------------------------------------------------


def _packaged(tmp_path: Path, with_ui: bool) -> Path:
    """`versions\\<v>`: the package beside python314._pth, optionally with ui\\index.html. Returns the package's
    __init__.py (what `ui_dir` is given)."""
    version = tmp_path / "versions" / "1.2.3"
    (version / "shelfsync").mkdir(parents=True)
    (version / "python314._pth").write_text("python314.zip\n.\n", encoding="utf-8")
    init = version / "shelfsync" / "__init__.py"
    init.write_text("", encoding="utf-8")
    if with_ui:
        (version / "ui").mkdir()
        (version / "ui" / "index.html").write_text("<html></html>", encoding="utf-8")
    return init


def test_a_packaged_copy_serves_the_ui_beside_the_package(tmp_path: Path) -> None:
    """SYS-01."""
    init = _packaged(tmp_path, with_ui=True)
    assert is_packaged_layout(init)
    assert ui_dir(init) == (tmp_path / "versions" / "1.2.3" / "ui").resolve()


def test_a_packaged_copy_without_its_ui_is_a_start_up_error(tmp_path: Path) -> None:
    """SYS-01: not an API-only server."""
    init = _packaged(tmp_path, with_ui=False)
    with pytest.raises(UiMissingError):
        ui_dir(init)


def test_the_source_layout_keeps_frontend_dist_even_when_it_is_not_built(tmp_path: Path) -> None:
    """UI-SHELL: the M1a development behaviour (an "API only" log line later)."""
    package = tmp_path / "repo" / "backend" / "shelfsync"
    package.mkdir(parents=True)
    init = package / "__init__.py"
    init.write_text("", encoding="utf-8")
    assert not is_packaged_layout(init)
    assert ui_dir(init) == (tmp_path / "repo" / "frontend" / "dist").resolve()
    assert source_ui_dir(init) == ui_dir(init)


def test_this_checkout_is_the_source_layout() -> None:
    """UI-SHELL."""
    assert not is_packaged_layout()
    assert ui_dir() == source_ui_dir()


def test_a_missing_ui_stops_start_up_with_its_own_notice_and_exit_3(
    data_paths: DataPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SYS-01: exit 3 and a notice (wording for 13); no port is bound and nothing is served."""
    from shelfsync import messages

    def missing() -> Path:
        raise UiMissingError("no ui")

    monkeypatch.setattr(server, "ui_dir", missing)
    notifier = FakeNotifier()
    served: list[bool] = []
    code = server.run(data_paths, notifier, lambda app, sock: served.append(True), secrets=MemorySecretStore())
    assert code == server.EXIT_START_FAILED == 3
    assert notifier.messages == [messages.START_FAILED_UI_MISSING]
    assert served == [] and not data_paths.runtime_json.exists()
