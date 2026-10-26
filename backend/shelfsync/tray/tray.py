"""The tray icon and its menu (UI-TRAY, SYS-02): pystray 0.19.5 on Windows, Windows' own native menu.

Menu: Open ShelfSync (the default item, bold; a click on the icon runs it too), Pause everything / Resume (shown,
greyed out until M5), View logs, a separator, Quit. Tooltip "ShelfSync".

Threads: the icon's message loop runs in a daemon thread of ours (`tray-loop`) that calls `Icon.run(setup)`, so the
main thread stays free for the launcher's wait loop (which Ctrl+C can interrupt). pystray's docs say `run()` should be
called from the main thread "for platform independence"; the win32 backend creates its window and loop in whichever
thread runs it (its own `run_detached` does exactly this, in a non-daemon thread). Daemon matters: pystray starts its
setup thread from the thread that calls `run()`, so that one is daemon too, and if the loop never comes up (or comes
up after `stop()` gave up waiting) neither thread can keep the process, and the single-instance lock, alive.

Theme: pystray has no callback for a taskbar theme change, so a small thread re-reads the setting every few seconds
and swaps the icon.
"""

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shelfsync.tray import icons
from shelfsync.tray.state import IconState, TrayState

_log = logging.getLogger("shelfsync.tray")

TOOLTIP = "ShelfSync"
THEME_POLL_SECONDS = 5.0
READY_TIMEOUT_SECONDS = 5.0  # how long `stop()` waits for the icon's message loop to come up


@dataclass(frozen=True)
class MenuEntry:
    text: str
    action: Callable[[], None] | None  # None: no action (greyed out, or a separator)
    default: bool = False
    enabled: bool = True
    separator: bool = False


def menu_entries(
    paused: bool,
    on_open: Callable[[], None],
    on_view_logs: Callable[[], None],
    on_quit: Callable[[], None],
) -> list[MenuEntry]:
    """The menu as data (05 section 6). Pause everything / Resume does nothing until M5, so it is disabled."""
    return [
        MenuEntry("Open ShelfSync", on_open, default=True),
        MenuEntry("Resume" if paused else "Pause everything", None, enabled=False),
        MenuEntry("View logs", on_view_logs),
        MenuEntry("", None, separator=True),
        MenuEntry("Quit", on_quit),
    ]


def _guarded(name: str, action: Callable[[], None]) -> Callable[[], None]:
    """A menu action that can't take the tray's message loop down with it."""

    def run() -> None:
        try:
            action()
        except Exception as error:
            _log.warning("Tray action %r failed (%s)", name, type(error).__name__)

    return run


class Tray:
    """Owns the pystray icon. Built with callbacks, so tests and the launcher decide what each item does."""

    def __init__(
        self,
        state: TrayState,
        on_open: Callable[[], None],
        on_view_logs: Callable[[], None],
        on_quit: Callable[[], None],
        *,
        light_taskbar: Callable[[], bool] = icons.taskbar_is_light,
        icon_size: Callable[[], int] = icons.system_small_icon_size,
        icon_dir: Path | None = None,
        theme_poll_seconds: float = THEME_POLL_SECONDS,
        ready_timeout: float = READY_TIMEOUT_SECONDS,
    ) -> None:
        self._state = state
        self._on_open = _guarded("open", on_open)
        self._on_view_logs = _guarded("view logs", on_view_logs)
        self._on_quit = _guarded("quit", on_quit)
        self._light_taskbar = light_taskbar
        self._icon_size = icon_size
        self._icon_dir = icon_dir
        self._poll = theme_poll_seconds
        self._ready_timeout = ready_timeout
        self._ready = threading.Event()  # set once pystray's message loop is up (its setup callback has run)
        self._warned: set[tuple[IconState, bool]] = set()  # icon keys already reported as unloadable
        self._icon: Any = None
        self._stop = threading.Event()
        self._watcher: threading.Thread | None = None
        self._loop: threading.Thread | None = None
        self._shown: tuple[IconState, bool] | None = None
        self._lock = threading.Lock()

    # --- pystray objects -------------------------------------------------------------------------------------

    def _pystray_menu(self) -> Any:
        import pystray

        items = []
        for entry in menu_entries(self._state.paused, self._on_open, self._on_view_logs, self._on_quit):
            if entry.separator:
                items.append(pystray.Menu.SEPARATOR)
            else:
                items.append(pystray.MenuItem(entry.text, entry.action, default=entry.default, enabled=entry.enabled))
        return pystray.Menu(*items)

    def _key(self) -> tuple[IconState, bool]:
        return (self._state.icon_state, self._light_taskbar())

    def _image(self, key: tuple[IconState, bool]) -> Any:
        path = icons.icon_file(key[0], key[1], self._icon_dir)
        return icons.load_icon(path, icons.nearest_size(self._icon_size()))

    # --- life cycle ------------------------------------------------------------------------------------------

    def start(self) -> None:
        """Show the icon (its message loop runs in its own thread) and start watching for state and theme changes."""
        import pystray

        self._shown = self._key()
        image = self._image(self._shown)
        self._icon = pystray.Icon("ShelfSync", image, TOOLTIP, self._pystray_menu())
        self._state.subscribe(self.refresh)
        self._ready.clear()
        icon = self._icon
        self._loop = threading.Thread(target=lambda: icon.run(self._setup), name="tray-loop", daemon=True)
        self._loop.start()
        self._watcher = threading.Thread(target=self._watch_theme, name="tray-theme", daemon=True)
        self._watcher.start()

    def _setup(self, icon: Any) -> None:
        """pystray calls this on a separate thread once the message loop is up. With a setup callback, showing the
        icon is ours to do."""
        try:
            icon.visible = True
        finally:
            self._ready.set()

    def stop(self) -> None:
        self._stop.set()
        icon, self._icon = self._icon, None
        if icon is not None:
            # `Icon.stop()` before the loop is up does nothing, so wait for it to come up first. If it never does
            # (pystray's thread failed) stop anyway and carry on: the loop and setup threads are daemon, so they
            # can't hold the process even if the loop comes up later.
            if not self._ready.wait(self._ready_timeout):
                _log.warning("The tray icon didn't come up in %.0f seconds", self._ready_timeout)
            try:
                icon.stop()
            except Exception as error:
                _log.warning("The tray icon couldn't be stopped (%s)", type(error).__name__)
        if self._watcher is not None:
            self._watcher.join(timeout=THEME_POLL_SECONDS + 1)

    def refresh(self) -> None:
        """The state or the taskbar theme changed: show the matching icon and rebuild the menu."""
        with self._lock:
            icon = self._icon
            if icon is None:
                return
            key = self._key()
            icon.menu = (
                self._pystray_menu()
            )  # first: the menu text (Resume) must follow the state even if the image fails
            try:
                image = self._image(key)
            except Exception as error:  # a missing or damaged .ico must not stop the tray
                if key not in self._warned:  # once per icon, not on every poll
                    self._warned.add(key)
                    _log.warning("The tray icon couldn't be changed (%s)", type(error).__name__)
                return
            if key != self._shown:
                self._shown = key
                icon.icon = image

    def _watch_theme(self) -> None:
        while not self._stop.wait(self._poll):
            try:
                key = self._key()
                # An icon that failed to load is not read again every few seconds; a state or theme change (a new
                # key) or an explicit refresh() tries again.
                if key != self._shown and key not in self._warned:
                    self.refresh()
            except Exception as error:
                _log.warning("The tray theme check failed (%s)", type(error).__name__)
