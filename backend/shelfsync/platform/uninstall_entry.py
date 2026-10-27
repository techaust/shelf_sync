"""The `DisplayVersion` of ShelfSync's uninstall entry (Settings, Apps, Installed apps).

The installer writes the whole key (04 section 8, the m1b.2 contracts); after each switch the updater writes only
`DisplayVersion`, and only into a key that already exists: it never creates one, so a development copy leaves the
registry alone. Tests use a throwaway key path.
"""

import sys
from typing import Protocol

from shelfsync.update.versions import parse_version

UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\ShelfSync"


class UninstallEntry(Protocol):
    def set_display_version(self, version: str) -> bool:
        """Write `DisplayVersion`. False (and nothing written) if the key doesn't exist or can't be written."""
        ...


class MemoryUninstallEntry:
    """Fake for tests and for systems without a registry."""

    def __init__(self, present: bool = True) -> None:
        self.present = present
        self.display_version: str | None = None

    def set_display_version(self, version: str) -> bool:
        parse_version(version)
        if not self.present:
            return False
        self.display_version = version
        return True


if sys.platform == "win32":
    import winreg

    class RegistryUninstallEntry:
        def __init__(self, key_path: str = UNINSTALL_KEY) -> None:
            self._key_path = key_path

        def set_display_version(self, version: str) -> bool:
            parse_version(version)
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self._key_path, 0, winreg.KEY_SET_VALUE) as key:
                    winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, version)
            except OSError:
                return False
            return True

else:

    class RegistryUninstallEntry:
        def __init__(self, key_path: str = UNINSTALL_KEY) -> None:
            self._key_path = key_path

        def set_display_version(self, version: str) -> bool:
            parse_version(version)
            return False  # there is no registry here


def default_uninstall_entry() -> UninstallEntry:
    return RegistryUninstallEntry()
