"""M1a.5, Quit always exits (UI-TRAY, SYS-02): the tray's stop checks its work, menu actions run off the loop thread.
Fakes from test_tray.py; the `windows` checks use the real pystray."""

import sys
import threading
import time
import types
from typing import Any

import pytest

from shelfsync.tray.state import TrayState
from shelfsync.tray.tray import Tray
from tests.test_tray import FakeIcon, fake_pystray, make_tray, nothing, wait_for

__all__ = ["fake_pystray"]  # the fixture, imported so pytest finds it here


def test_stop_warns_and_returns_when_the_loop_never_ends(
    fake_pystray: types.SimpleNamespace, caplog: pytest.LogCaptureFixture
) -> None:
    """UI-TRAY, SYS-02 (D1): `Icon.stop()` only posts a message. A loop that never ends is reported, the stop is posted
    once more, the icon is hidden by hand, and `stop()` still returns (2 s + 1 s)."""
    FakeIcon.loop_never_ends = True
    tray = make_tray(TrayState(), [True], [], poll=60)
    tray.start()
    (icon,) = FakeIcon.instances
    assert wait_for(lambda: icon.visible)
    started = time.monotonic()
    with caplog.at_level("INFO", logger="shelfsync.tray"):
        tray.stop()
    took = time.monotonic() - started
    assert 2.5 <= took < 3.5
    assert caplog.text.count("message loop didn't end in 2 seconds") == 1
    assert icon.reposts == 1
    assert icon.visible is False  # hidden by hand: the icon leaves the tray
    assert "Tray stopped in" not in caplog.text
    assert "Tray loop still running; icon hidden (" in caplog.text  # the forced path reports its own outcome


def test_a_second_stop_that_works_is_reported(
    fake_pystray: types.SimpleNamespace, caplog: pytest.LogCaptureFixture
) -> None:
    """UI-TRAY: the loop ignores the first stop but ends after the re-post: INFO with the time, no "still running"."""
    FakeIcon.loop_never_ends = True
    FakeIcon.repost_ends_loop = True
    tray = make_tray(TrayState(), [True], [], poll=60)
    tray.start()
    (icon,) = FakeIcon.instances
    assert wait_for(lambda: icon.visible)
    with caplog.at_level("INFO", logger="shelfsync.tray"):
        tray.stop()
    assert "Tray loop ended after the second stop (" in caplog.text
    assert "still running" not in caplog.text
    assert icon.reposts == 1 and icon.visible is False


def test_a_clean_stop_logs_how_long_it_took(
    fake_pystray: types.SimpleNamespace, caplog: pytest.LogCaptureFixture
) -> None:
    """UI-TRAY: INFO "Tray stopped in N.N s", no warning, no second post."""
    tray = make_tray(TrayState(), [True], [], poll=60)
    tray.start()
    (icon,) = FakeIcon.instances
    assert wait_for(lambda: icon.visible)
    with caplog.at_level("INFO", logger="shelfsync.tray"):
        tray.stop()
    assert "Tray stopped in" in caplog.text and "didn't end" not in caplog.text
    assert icon.reposts == 0


def test_menu_actions_run_off_the_loop_thread(fake_pystray: types.SimpleNamespace) -> None:
    """UI-TRAY (D1): Open and View logs run in `tray-action-<name>` daemon threads; a hung one doesn't block the caller
    (pystray's loop thread)."""
    names: dict[str, str] = {}
    daemons: dict[str, bool] = {}
    release = threading.Event()

    def hung_open() -> None:
        names["open"] = threading.current_thread().name
        daemons["open"] = threading.current_thread().daemon
        release.wait(10)

    def logs() -> None:
        names["logs"] = threading.current_thread().name

    tray = Tray(TrayState(), hung_open, logs, nothing, light_taskbar=lambda: True, icon_size=lambda: 16)
    tray.start()
    try:
        (icon,) = FakeIcon.instances
        started = time.monotonic()
        icon.menu.items[0].action()  # the hung Open
        icon.menu.items[2].action()  # View logs, while Open is still hung
        assert time.monotonic() - started < 1  # both returned at once
        assert wait_for(lambda: len(names) == 2)
        assert names == {"open": "tray-action-open", "logs": "tray-action-view-logs"}
        assert daemons["open"] is True
    finally:
        release.set()
        tray.stop()


def test_quit_runs_inline_even_while_open_is_hung(fake_pystray: types.SimpleNamespace) -> None:
    """UI-TRAY: Quit only sets two events; a hung Open must not queue ahead of it."""
    release = threading.Event()
    quit_thread: list[threading.Thread] = []
    tray = Tray(
        TrayState(),
        lambda: release.wait(10),
        nothing,
        lambda: quit_thread.append(threading.current_thread()),
        light_taskbar=lambda: True,
        icon_size=lambda: 16,
    )
    tray.start()
    try:
        (icon,) = FakeIcon.instances
        icon.menu.items[0].action()  # Open hangs in its own thread
        icon.menu.items[4].action()
        assert quit_thread == [threading.current_thread()]  # inline: the caller's thread, no hand-off
    finally:
        release.set()
        tray.stop()


def test_refresh_after_stop_does_nothing(fake_pystray: types.SimpleNamespace) -> None:
    """UI-TRAY: the sequential contract only: once `stop()` has returned, `refresh()` (the theme thread, a state change)
    doesn't touch the icon. This passes on the old code too; the race itself is the next test."""
    state = TrayState()
    tray = make_tray(state, [True], [], poll=60)
    tray.start()
    (icon,) = FakeIcon.instances
    assert wait_for(lambda: icon.visible)
    tray.stop()
    menus, images = len(icon.menus), len(icon.icon_sets)
    state.set_paused(True)
    tray.refresh()
    assert (len(icon.menus), len(icon.icon_sets)) == (menus, images)


def test_stop_waits_for_a_refresh_that_is_in_the_middle_of_rebuilding_the_menu(
    fake_pystray: types.SimpleNamespace,
) -> None:
    """UI-TRAY (D1, lock race): `refresh()` is blocked inside setting `icon.menu` while `stop()` runs. `stop()` takes
    the lock to clear the icon, so it must not stop the icon until the refresh is done. (Without the lock it
    stopped the icon under the refresh's feet.)"""
    state = TrayState()
    tray = make_tray(state, [True], [], poll=60)
    tray.start()
    (icon,) = FakeIcon.instances
    assert wait_for(lambda: icon.visible)
    inside, release = threading.Event(), threading.Event()

    def slow_rebuild() -> None:
        inside.set()
        release.wait(10)

    FakeIcon.menu_hook = slow_rebuild
    refresher = threading.Thread(target=lambda: state.set_paused(True), name="refresher", daemon=True)
    refresher.start()
    assert inside.wait(5)
    stopper = threading.Thread(target=tray.stop, name="stopper", daemon=True)
    stopper.start()
    time.sleep(0.3)
    try:
        assert stopper.is_alive() and not icon.stopped  # waiting for the refresh, not racing it
    finally:
        release.set()
    stopper.join(5)
    refresher.join(5)
    assert not stopper.is_alive() and icon.stopped


def test_the_menu_is_rebuilt_only_when_the_paused_flag_changed(fake_pystray: types.SimpleNamespace) -> None:
    """UI-TRAY: a theme-only refresh leaves the menu alone."""
    light = [True]
    state = TrayState()
    tray = make_tray(state, light, [], poll=60)
    tray.start()
    try:
        (icon,) = FakeIcon.instances
        before = len(icon.menus)
        light[0] = False
        tray.refresh()
        assert len(icon.menus) == before
        state.set_paused(True)
        assert len(icon.menus) == before + 1
    finally:
        tray.stop()


# ---- the real pystray (Windows) --------------------------------------------------------------------------------------

NIM_MODIFY = 0x1
NIM_DELETE = 0x2
NIF_TIP = 0x4


@pytest.fixture
def shell_notify_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, int]]:
    """Wraps pystray's `Shell_NotifyIcon` to record `(code, BOOL result)`: pystray's own `visible` flag is set whatever
    Windows answered, so the BOOL is the evidence that the icon really went."""
    from pystray._util import win32

    real = win32.Shell_NotifyIcon
    calls: list[tuple[int, int]] = []

    def recording(code: int, data: Any) -> int:
        result = real(code, data)
        calls.append((int(code), int(result)))
        return result

    monkeypatch.setattr(win32, "Shell_NotifyIcon", recording)
    return calls


WM_USER = 0x400
WM_STOP = WM_USER + 10
WM_NOTIFY = WM_USER + 11
WM_LBUTTONUP = 0x0202


@pytest.mark.windows
@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_real_stop_while_an_action_is_blocked_still_ends_the_loop() -> None:
    """UI-TRAY, SYS-02 (D1): the default item is run on the loop thread by a WM_NOTIFY with WM_LBUTTONUP (posted by
    hand, no mouse). Open is blocked, but runs off the loop thread, so `stop()` still ends the loop."""
    import ctypes

    blocked, release = threading.Event(), threading.Event()

    def blocking_open() -> None:
        blocked.set()
        release.wait(15)

    tray = Tray(TrayState(), blocking_open, nothing, nothing)
    tray.start()
    try:
        icon = tray._icon
        assert icon is not None and wait_for(lambda: icon.visible)
        hwnd = icon._hwnd  # type: ignore[attr-defined]
        assert ctypes.windll.user32.PostMessageW(hwnd, WM_NOTIFY, 0, WM_LBUTTONUP)
        assert blocked.wait(5), "the default action didn't run"
        started = time.monotonic()
        tray.stop()
        assert time.monotonic() - started < 3
        assert tray._loop is not None and not tray._loop.is_alive()
    finally:
        release.set()
        tray.stop()


@pytest.mark.windows
@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_real_nested_loop_that_eats_wm_quit_cannot_keep_the_icon(
    caplog: pytest.LogCaptureFixture, shell_notify_calls: list[tuple[int, int]]
) -> None:
    """UI-TRAY (D1): a stop handler that swallows the stop (as a nested message loop would eat WM_QUIT) leaves the loop
    running; `stop()` warns, returns within about 3 s, and the icon is hidden anyway."""
    tray = Tray(TrayState(), nothing, nothing, nothing)
    tray.start()
    icon = tray._icon
    assert icon is not None and wait_for(lambda: icon.visible)
    handlers = icon._message_handlers  # type: ignore[attr-defined]
    real_stop = handlers[WM_STOP]
    handlers[WM_STOP] = lambda wparam, lparam: 0  # swallowed
    started = time.monotonic()
    try:
        with caplog.at_level("WARNING", logger="shelfsync.tray"):
            tray.stop()
        assert time.monotonic() - started < 4
        assert "message loop didn't end in 2 seconds" in caplog.text
        assert tray._loop is not None and tray._loop.is_alive()  # still stuck, as designed
        assert icon.visible is False
        # Windows itself said the icon was deleted (the loop is still stuck, so this is the forced hide's NIM_DELETE)
        assert (NIM_DELETE, 1) in shell_notify_calls, shell_notify_calls
        print("nested-loop test, Shell_NotifyIcon (code, BOOL):", shell_notify_calls)
    finally:
        handlers[WM_STOP] = real_stop
        icon._stop()  # type: ignore[attr-defined]
        assert tray._loop is not None
        tray._loop.join(timeout=5)
        assert not tray._loop.is_alive()


@pytest.mark.windows
@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_real_hide_from_another_thread_removes_the_icon(shell_notify_calls: list[tuple[int, int]]) -> None:
    """UI-TRAY (becomes a 04-A row): `icon.visible = False` from a thread that isn't the loop's works. Evidence is
    Windows' own answer: `Shell_NotifyIcon(NIM_DELETE)` returns TRUE, and a NIM_MODIFY on the same window and id
    afterwards returns FALSE (the icon no longer exists)."""
    tray = Tray(TrayState(), nothing, nothing, nothing)
    tray.start()
    try:
        icon = tray._icon
        assert icon is not None and wait_for(lambda: icon.visible)
        errors: list[BaseException] = []

        def hide() -> None:
            try:
                icon.visible = False
            except BaseException as error:
                errors.append(error)

        thread = threading.Thread(target=hide, name="hider")
        thread.start()
        thread.join(5)
        assert errors == [] and icon.visible is False
        deletes = [result for code, result in shell_notify_calls if code == NIM_DELETE]
        assert deletes == [1], shell_notify_calls  # exactly one NIM_DELETE, and Windows said TRUE
        before = len(shell_notify_calls)
        icon._message(NIM_MODIFY, NIF_TIP, szTip="gone?")  # type: ignore[attr-defined]
        assert shell_notify_calls[before:] == [(NIM_MODIFY, 0)]  # FALSE: no such icon any more
        print("hide-from-another-thread test, Shell_NotifyIcon (code, BOOL):", shell_notify_calls)
        assert tray._loop is not None and tray._loop.is_alive()  # only the icon went; the loop is still up
    finally:
        tray.stop()
