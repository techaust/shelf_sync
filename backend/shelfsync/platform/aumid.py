"""ShelfSync's own toast AppUserModelID (SYS-05, 04-A V41).

The installer registers `TecHaust.ShelfSync` under `HKCU\\Software\\Classes\\AppUserModelId\\<id>` (`DisplayName`
"ShelfSync", `IconUri` the installed `shelfsync.ico`) and the uninstaller removes it. The app only *reads* the key, to
decide whether to use the AUMID: Windows may drop a toast sent for an AUMID nobody registered, so an installed copy
whose key is missing falls back to the M1a behaviour. The write and delete helpers below are what the installer's
script does, so the Windows tests (throwaway names) and the cold-toast timing can exercise the same key.
"""

import sys

AUMID = "TecHaust.ShelfSync"
DISPLAY_NAME = "ShelfSync"
KEY_ROOT = r"Software\Classes\AppUserModelId"


def key_path(aumid: str) -> str:
    return f"{KEY_ROOT}\\{aumid}"


if sys.platform == "win32":
    import winreg

    def is_registered(aumid: str = AUMID) -> bool:
        """True when `HKCU\\...\\AppUserModelId\\<id>` exists with a `DisplayName`."""
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path(aumid), 0, winreg.KEY_QUERY_VALUE) as key:
                name, _kind = winreg.QueryValueEx(key, "DisplayName")
        except OSError:
            return False
        return bool(name)

    def register(aumid: str, display_name: str, icon_uri: str) -> None:
        """Write the key. Raises OSError on failure."""
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path(aumid), 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, display_name)
            winreg.SetValueEx(key, "IconUri", 0, winreg.REG_SZ, icon_uri)

    def unregister(aumid: str) -> None:
        """Remove the key. A key that isn't there is not an error."""
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path(aumid))
        except FileNotFoundError:
            return

else:

    def is_registered(aumid: str = AUMID) -> bool:
        return False

    def register(aumid: str, display_name: str, icon_uri: str) -> None:
        raise OSError("The AppUserModelID key is available on Windows only")

    def unregister(aumid: str) -> None:
        raise OSError("The AppUserModelID key is available on Windows only")
