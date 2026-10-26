"""UI-TRAY, SYS-02: the tray menu, the three icon states and the taskbar theme. pystray is faked on Linux CI; one
Windows check runs the real icon."""

import sys
import threading
import time
import types
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar

import pytest

from shelfsync.tray import icons
from shelfsync.tray.state import IconState, TrayState
from shelfsync.tray.tray import THEME_POLL_SECONDS, TOOLTIP, MenuEntry, Tray, menu_entries

TRAY_ASSETS = Path(__file__).parents[1] / "brand" / "assets" / "tray"


def nothing() -> None:
    return None


# ---- the menu as data -----------------------------------------------------------------------------------------------


def test_the_menu_is_open_pause_logs_separator_quit_in_that_order() -> None:
    """UI-TRAY (05 section 6)."""
    entries = menu_entries(False, nothing, nothing, nothing)
    assert [(e.text, e.separator) for e in entries] == [
        ("Open ShelfSync", False),
        ("Pause everything", False),
        ("View logs", False),
        ("", True),
        ("Quit", False),
    ]


def test_open_shelfsync_is_the_only_default_item() -> None:
    """UI-TRAY: bold, and what a click on the icon runs (V13)."""
    entries = menu_entries(False, nothing, nothing, nothing)
    assert [e.text for e in entries if e.default] == ["Open ShelfSync"]


def test_pause_is_shown_but_disabled_until_m5_and_reads_resume_when_paused() -> None:
    """UI-TRAY: as on the M1a.3 screens, Pause everything / Resume does nothing yet."""
    running, paused = menu_entries(False, nothing, nothing, nothing), menu_entries(True, nothing, nothing, nothing)
    assert running[1].text == "Pause everything" and paused[1].text == "Resume"
    for entry in (running[1], paused[1]):
        assert entry.enabled is False and entry.action is None


def test_the_actions_are_the_ones_given() -> None:
    """UI-TRAY."""
    calls: list[str] = []
    entries = menu_entries(
        False, lambda: calls.append("open"), lambda: calls.append("logs"), lambda: calls.append("quit")
    )
    for entry in entries:
        if entry.action is not None:
            entry.action()
    assert calls == ["open", "logs", "quit"]


# ---- the state object -----------------------------------------------------------------------------------------------


def test_the_icon_state_is_normal_paused_or_attention_and_attention_wins() -> None:
    """UI-TRAY: three states."""
    state = TrayState()
    assert state.icon_state is IconState.NORMAL
    state.set_paused(True)
    assert state.icon_state is IconState.PAUSED and state.paused
    state.set_attention(True)
    assert state.icon_state is IconState.ATTENTION
    state.set_attention(False)
    assert state.icon_state is IconState.PAUSED
    state.set_paused(False)
    assert state.icon_state is IconState.NORMAL


def test_listeners_hear_real_changes_only() -> None:
    """UI-TRAY."""
    state, heard = TrayState(), []
    state.subscribe(lambda: heard.append(state.icon_state))
    state.set_paused(False)  # no change
    state.set_attention(True)
    state.set_attention(True)  # no change
    state.set_paused(True)
    assert heard == [IconState.ATTENTION, IconState.ATTENTION]


# ---- icons ----------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("state", list(IconState))
@pytest.mark.parametrize("light", [True, False])
def test_every_state_and_theme_has_an_icon_file_with_the_four_sizes(state: IconState, light: bool) -> None:
    """UI-TRAY: tray-<state>-<light|dark>.ico, 16, 20, 24 and 32 px (brand README)."""
    path = icons.icon_file(state, light)
    assert path.parent == TRAY_ASSETS.resolve() and path.is_file()
    assert path.name == f"tray-{state.value}-{'light' if light else 'dark'}.ico"
    from PIL import Image

    with Image.open(path) as ico:
        assert ico.info["sizes"] == {(16, 16), (20, 20), (24, 24), (32, 32)}


@pytest.mark.parametrize(
    "wanted, chosen", [(16, 16), (17, 16), (18, 16), (19, 20), (22, 20), (23, 24), (28, 24), (40, 32), (0, 16)]
)
def test_the_frame_nearest_the_system_icon_size_is_chosen(wanted: int, chosen: int) -> None:
    """UI-TRAY: 100 % scaling asks for 16, 125 % for 20, 150 % for 24, 200 % for 32."""
    assert icons.nearest_size(wanted) == chosen


@pytest.mark.parametrize("size", icons.AVAILABLE_SIZES)
def test_load_icon_gives_the_requested_frame(size: int) -> None:
    """UI-TRAY."""
    image = icons.load_icon(icons.icon_file(IconState.NORMAL, True), size)
    assert image.size == (size, size)


def test_the_light_and_dark_icons_differ() -> None:
    """UI-TRAY: correct on light and dark taskbars means two different pictures."""
    light = icons.load_icon(icons.icon_file(IconState.NORMAL, True), 32)
    dark = icons.load_icon(icons.icon_file(IconState.NORMAL, False), 32)
    assert light.convert("RGBA").tobytes() != dark.convert("RGBA").tobytes()


@pytest.mark.skipif(sys.platform == "win32", reason="the registry read is Windows only")
def test_off_windows_the_taskbar_counts_as_dark() -> None:
    """UI-TRAY."""
    assert icons.taskbar_is_light() is False


@pytest.mark.windows
@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_the_real_taskbar_theme_and_icon_size_can_be_read() -> None:
    """UI-TRAY: SystemUsesLightTheme and SM_CXSMICON on this PC."""
    assert isinstance(icons.taskbar_is_light(), bool)
    assert icons.system_small_icon_size() in range(8, 65)


# ---- the Tray with pystray faked ----------------------------------------------------------------------------------


class FakeIcon:
    instances: ClassVar[list["FakeIcon"]] = []
    auto_ready: ClassVar[bool] = True

    def __init__(self, name: str, icon: Any, title: str, menu: Any) -> None:
        self.name, self._icon, self.title, self._menu = name, icon, title, menu
        self.icon_sets: list[Any] = [icon]
        self.menus: list[Any] = [menu]
        self.detached = self.stopped = False
        self.setup: Callable[[Any], None] | None = None
        self.visible = False
        self.stopped_before_ready = False
        FakeIcon.instances.append(self)

    @property
    def icon(self) -> Any:
        return self._icon

    @icon.setter
    def icon(self, value: Any) -> None:
        self._icon = value
        self.icon_sets.append(value)

    @property
    def menu(self) -> Any:
        return self._menu

    @menu.setter
    def menu(self, value: Any) -> None:
        self._menu = value
        self.menus.append(value)

    def run_detached(self, setup: Callable[[Any], None] | None = None) -> None:
        self.detached = True
        self.setup = setup
        if FakeIcon.auto_ready and setup is not None:
            threading.Thread(target=setup, args=(self,)).start()  # pystray runs setup on its own thread

    def stop(self) -> None:
        self.stopped = True
        if self.setup is not None and not self.visible:
            self.stopped_before_ready = True


class FakeMenu:
    SEPARATOR = object()

    def __init__(self, *items: Any) -> None:
        self.items = items


class FakeMenuItem:
    def __init__(
        self, text: str, action: Callable[[], None] | None, default: bool = False, enabled: bool = True
    ) -> None:
        self.text, self.action, self.default, self.enabled = text, action, default, enabled


@pytest.fixture
def fake_pystray(monkeypatch: pytest.MonkeyPatch) -> types.SimpleNamespace:
    FakeIcon.instances = []
    FakeIcon.auto_ready = True
    module = types.SimpleNamespace(Icon=FakeIcon, Menu=FakeMenu, MenuItem=FakeMenuItem)
    monkeypatch.setitem(sys.modules, "pystray", module)
    return module


def make_tray(state: TrayState, light: list[bool], calls: list[str], poll: float = 0.02) -> Tray:
    return Tray(
        state,
        lambda: calls.append("open"),
        lambda: calls.append("logs"),
        lambda: calls.append("quit"),
        light_taskbar=lambda: light[0],
        icon_size=lambda: 16,
        theme_poll_seconds=poll,
    )


def test_start_shows_the_normal_icon_with_the_menu_and_the_tooltip(fake_pystray: types.SimpleNamespace) -> None:
    """UI-TRAY, SYS-02: pystray's loop runs in its own thread (run_detached); tooltip "ShelfSync"."""
    calls: list[str] = []
    tray = make_tray(TrayState(), [True], calls)
    tray.start()
    try:
        (icon,) = FakeIcon.instances
        assert icon.detached and icon.title == TOOLTIP == "ShelfSync" and icon.name == "ShelfSync"
        items = icon.menu.items
        assert [getattr(item, "text", "-") for item in items] == [
            "Open ShelfSync",
            "Pause everything",
            "View logs",
            "-",
            "Quit",
        ]
        assert items[3] is FakeMenu.SEPARATOR
        assert items[0].default and not items[1].enabled
        items[0].action()
        items[2].action()
        items[4].action()
        assert calls == ["open", "logs", "quit"]
    finally:
        tray.stop()
    assert icon.stopped


def test_a_state_change_swaps_the_icon_and_the_menu_text(fake_pystray: types.SimpleNamespace) -> None:
    """UI-TRAY: paused and attention have their own icons; the menu reads Resume when paused."""
    state, calls = TrayState(), []
    tray = make_tray(state, [True], calls, poll=60)
    tray.start()
    try:
        (icon,) = FakeIcon.instances
        normal = icon.icon
        state.set_paused(True)
        assert icon.icon is not normal
        assert icon.menu.items[1].text == "Resume"
        paused = icon.icon
        state.set_attention(True)
        assert icon.icon is not paused
        state.set_attention(False)
        state.set_paused(False)
        assert icon.menu.items[1].text == "Pause everything"
    finally:
        tray.stop()


def wait_for(condition: Callable[[], bool], seconds: float = 3.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return condition()


def test_a_taskbar_theme_change_swaps_the_icon_without_a_restart(fake_pystray: types.SimpleNamespace) -> None:
    """UI-TRAY: pystray has no theme-change callback, so a small thread re-reads the setting."""
    light = [True]
    tray = make_tray(TrayState(), light, [], poll=0.02)
    tray.start()
    try:
        (icon,) = FakeIcon.instances
        before = len(icon.icon_sets)
        light[0] = False
        assert wait_for(lambda: len(icon.icon_sets) > before)
        dark = icons.load_icon(icons.icon_file(IconState.NORMAL, False), 16)
        assert icon.icon.convert("RGBA").tobytes() == dark.convert("RGBA").tobytes()
    finally:
        tray.stop()


def test_no_theme_change_means_no_icon_churn(fake_pystray: types.SimpleNamespace) -> None:
    """UI-TRAY."""
    tray = make_tray(TrayState(), [True], [], poll=0.01)
    tray.start()
    try:
        (icon,) = FakeIcon.instances
        time.sleep(0.1)
        assert len(icon.icon_sets) == 1
    finally:
        tray.stop()


def test_a_menu_action_that_raises_does_not_escape(
    fake_pystray: types.SimpleNamespace, caplog: pytest.LogCaptureFixture
) -> None:
    """UI-TRAY: an exception inside pystray's callback would end the tray's message loop."""

    def broken() -> None:
        raise RuntimeError("folder is gone")

    tray = Tray(TrayState(), broken, broken, broken, light_taskbar=lambda: True, icon_size=lambda: 16)
    tray.start()
    try:
        (icon,) = FakeIcon.instances
        with caplog.at_level("WARNING", logger="shelfsync.tray"):
            for item in icon.menu.items:
                if item is not FakeMenu.SEPARATOR and item.action is not None:
                    item.action()
    finally:
        tray.stop()
    assert caplog.text.count("failed (RuntimeError)") == 3


def test_a_missing_icon_file_is_logged_and_the_tray_stays_up(
    fake_pystray: types.SimpleNamespace, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """UI-TRAY: a refresh that can't load the new .ico keeps the old icon."""
    state = TrayState()
    tray = make_tray(state, [True], [], poll=60)
    tray.start()
    try:
        tray._icon_dir = tmp_path  # nothing there
        with caplog.at_level("WARNING", logger="shelfsync.tray"):
            state.set_paused(True)
        assert "The tray icon couldn't be changed" in caplog.text
    finally:
        tray.stop()


def test_stop_before_pystray_is_ready_waits_for_it_then_stops(fake_pystray: types.SimpleNamespace) -> None:
    """UI-TRAY (review 1): `Icon.stop()` before the loop is up does nothing and would leave the process running with
    the single-instance lock held. `stop()` waits for the setup callback, then stops."""
    FakeIcon.auto_ready = False
    tray = make_tray(TrayState(), [True], [], poll=60)
    tray.start()
    (icon,) = FakeIcon.instances
    assert icon.setup is not None and not icon.visible
    threading.Timer(0.2, lambda: icon.setup(icon)).start()  # the loop comes up a moment later
    tray.stop()
    assert icon.stopped and icon.visible
    assert not icon.stopped_before_ready


def test_the_setup_callback_shows_the_icon(fake_pystray: types.SimpleNamespace) -> None:
    """UI-TRAY: with a setup callback pystray no longer sets `visible` itself."""
    tray = make_tray(TrayState(), [True], [], poll=60)
    tray.start()
    try:
        (icon,) = FakeIcon.instances
        assert wait_for(lambda: icon.visible)
    finally:
        tray.stop()


def test_stop_when_pystray_never_gets_ready_still_returns_and_stops(
    fake_pystray: types.SimpleNamespace, caplog: pytest.LogCaptureFixture
) -> None:
    """UI-TRAY (review 1): pystray's thread failed before the loop came up, so nothing is running; `stop()` gives up
    waiting after the timeout, still asks the icon to stop, and the process can exit."""
    FakeIcon.auto_ready = False
    tray = Tray(
        TrayState(), nothing, nothing, nothing, light_taskbar=lambda: True, icon_size=lambda: 16, ready_timeout=0.1
    )
    tray.start()
    (icon,) = FakeIcon.instances
    started = time.monotonic()
    with caplog.at_level("WARNING", logger="shelfsync.tray"):
        tray.stop()
    assert time.monotonic() - started < 3
    assert icon.stopped
    assert "didn't come up" in caplog.text


def test_an_icon_that_cant_be_stopped_is_logged_not_raised(
    fake_pystray: types.SimpleNamespace, caplog: pytest.LogCaptureFixture
) -> None:
    """UI-TRAY."""
    tray = make_tray(TrayState(), [True], [], poll=60)
    tray.start()
    (icon,) = FakeIcon.instances
    wait_for(lambda: icon.visible)

    def broken() -> None:
        raise RuntimeError("window gone")

    icon.stop = broken  # type: ignore[method-assign]
    with caplog.at_level("WARNING", logger="shelfsync.tray"):
        tray.stop()
    assert "couldn't be stopped (RuntimeError)" in caplog.text


def test_a_missing_icon_file_is_warned_once_per_icon_not_every_poll(
    fake_pystray: types.SimpleNamespace, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """UI-TRAY (review 9): the poll retries every few seconds; the warning is once per state-and-theme icon."""
    state = TrayState()
    tray = make_tray(state, [True], [], poll=0.01)
    tray.start()
    try:
        tray._icon_dir = tmp_path
        with caplog.at_level("WARNING", logger="shelfsync.tray"):
            state.set_paused(True)  # the first failure
            time.sleep(0.2)  # many polls
            assert caplog.text.count("couldn't be changed") == 1
            state.set_attention(True)  # a different icon: its own warning
            time.sleep(0.1)
            assert caplog.text.count("couldn't be changed") == 2
    finally:
        tray.stop()


def test_stop_without_start_does_nothing() -> None:
    """UI-TRAY."""
    make_tray(TrayState(), [True], []).stop()


def test_the_theme_poll_is_a_few_seconds() -> None:
    """UI-TRAY: cheap enough to leave on."""
    assert 1 <= THEME_POLL_SECONDS <= 10


def test_menu_entry_is_plain_data() -> None:
    """UI-TRAY."""
    assert MenuEntry("x", None).enabled is True


# ---- the real pystray (Windows) --------------------------------------------------------------------------------------


@pytest.mark.windows
@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_the_real_icon_starts_changes_state_and_stops() -> None:
    """UI-TRAY, V13: a real tray icon appears for a moment, takes the three states and goes away."""
    import pystray

    state, calls = TrayState(), []
    tray = Tray(state, lambda: calls.append("open"), lambda: calls.append("logs"), lambda: calls.append("quit"))
    tray.start()
    try:
        icon = tray._icon
        assert isinstance(icon, pystray.Icon)
        assert wait_for(lambda: icon.visible)
        state.set_paused(True)
        state.set_attention(True)
        state.set_attention(False)
        state.set_paused(False)
        menu = icon.menu
        assert isinstance(menu, pystray.Menu)
        assert [item.text for item in menu.items if item is not pystray.Menu.SEPARATOR] == [
            "Open ShelfSync",
            "Pause everything",
            "View logs",
            "Quit",
        ]
        default = next(item for item in menu.items if item is not pystray.Menu.SEPARATOR and item.default)
        assert default.text == "Open ShelfSync"
    finally:
        tray.stop()
    assert tray._icon is None


@pytest.mark.windows
@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_the_real_icon_stopped_straight_after_start_really_stops() -> None:
    """UI-TRAY (review 1, 11): no wait for the icon to appear; `stop()` must still end pystray's message loop, or the
    process would stay up holding the single-instance lock."""
    tray = Tray(TrayState(), nothing, nothing, nothing)
    tray.start()
    icon = tray._icon
    assert icon is not None
    tray.stop()
    assert wait_for(lambda: not icon._running)  # type: ignore[attr-defined]
