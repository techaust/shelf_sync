"""Tray icons (UI-TRAY): `tray-<state>-<light|dark>.ico`, "light" meaning for a light taskbar, from
`paths.tray_icon_dir()` (`brand/assets/tray` in the source layout, `<version folder>\\tray` when installed).

Which one: the state (normal, paused, attention) and the taskbar theme, read from
`HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize\\SystemUsesLightTheme` (the taskbar's setting,
not the apps' `AppsUseLightTheme`). The .ico files hold 16, 20, 24 and 32 px; the one nearest the system's small-icon
size is handed to pystray.
"""

import functools
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from shelfsync.paths import tray_icon_dir
from shelfsync.tray.state import IconState

if TYPE_CHECKING:
    from PIL.Image import Image

AVAILABLE_SIZES = (16, 20, 24, 32)
PERSONALIZE_KEY = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
TASKBAR_THEME_VALUE = "SystemUsesLightTheme"


@functools.cache
def default_icon_dir() -> Path:
    """`paths.tray_icon_dir()`, worked out once (the layout can't change while the process runs)."""
    return tray_icon_dir()


def icon_file(state: IconState, light_taskbar: bool, folder: Path | None = None) -> Path:
    return (folder or default_icon_dir()) / f"tray-{state.value}-{'light' if light_taskbar else 'dark'}.ico"


def nearest_size(wanted: int) -> int:
    return min(AVAILABLE_SIZES, key=lambda size: (abs(size - wanted), size))


def load_icon(path: Path, size: int) -> Image:
    """The frame of the .ico nearest `size`, as a Pillow image (pystray saves it again and Windows loads that)."""
    from PIL import Image

    with Image.open(path) as ico:
        frames = ico.info.get("sizes", set())
        chosen = min(frames, key=lambda frame: (abs(frame[0] - size), frame[0])) if frames else ico.size
        ico.size = chosen  # type: ignore[misc]  # Pillow lets an .ico choose its frame here
        ico.load()
        return ico.copy()


if sys.platform == "win32":
    import ctypes
    import winreg

    _SM_CXSMICON = 49

    def taskbar_is_light() -> bool:
        """True when Windows' taskbar is light. If the value isn't there or can't be read the answer is dark, which
        is Windows' own default."""
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, PERSONALIZE_KEY, 0, winreg.KEY_QUERY_VALUE) as key:
                value, _kind = winreg.QueryValueEx(key, TASKBAR_THEME_VALUE)
        except OSError:
            return False
        return bool(value)

    def system_small_icon_size() -> int:
        return int(ctypes.windll.user32.GetSystemMetrics(_SM_CXSMICON)) or 16

else:

    def taskbar_is_light() -> bool:
        return False

    def system_small_icon_size() -> int:
        return 16
