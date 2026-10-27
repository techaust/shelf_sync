"""The data folder (04 section 8): %LOCALAPPDATA%\\ShelfSync\\ with logs\\, tmp\\, backups\\ and runtime.json."""

import json
import logging
import os
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path

_log = logging.getLogger("shelfsync.paths")

DATA_DIR_ENV = "SHELFSYNC_DATA_DIR"  # for tests and Linux CI; nothing else overrides the root
INSTANCE_LOCK_NAME = "instance.lock"  # in the data folder; the installer and uninstaller also try to open it (SYS-01)


@dataclass(frozen=True)
class DataPaths:
    root: Path

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def tmp(self) -> Path:
        return self.root / "tmp"

    @property
    def backups(self) -> Path:
        return self.root / "backups"

    @property
    def runtime_json(self) -> Path:
        return self.root / "runtime.json"

    @property
    def database(self) -> Path:
        return self.root / "shelfsync.db"

    @property
    def instance_lock(self) -> Path:
        """The lock file that keeps a second logon session of the same user from starting a second server (SYS-03)."""
        return self.root / INSTANCE_LOCK_NAME


def resolve_data_paths() -> DataPaths:
    """The data folder: SHELFSYNC_DATA_DIR if set, otherwise %LOCALAPPDATA%\\ShelfSync."""
    override = os.environ.get(DATA_DIR_ENV)
    if override:
        return DataPaths(Path(override))
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise RuntimeError(
            f"LOCALAPPDATA is not set, so the data folder is unknown. Set {DATA_DIR_ENV} to use another folder."
        )
    return DataPaths(Path(local_app_data) / "ShelfSync")


def create_data_folders(paths: DataPaths) -> None:
    """Create the data folder and its logs\\, backups\\ and tmp\\ folders."""
    for folder in (paths.root, paths.logs, paths.backups, paths.tmp):
        folder.mkdir(parents=True, exist_ok=True)


def is_plain_file(path: Path) -> bool:
    """True if `path` is a regular file with one name, and not a link or a reparse point. False if it is anything
    else; an entry that doesn't exist is also False (nothing to read)."""
    try:
        info = path.lstat()
    except OSError:
        return False
    if path.is_symlink() or os.path.isjunction(path):
        return False
    if getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
        return False
    return stat.S_ISREG(info.st_mode) and info.st_nlink == 1


def remove_entry(entry: Path) -> None:
    """Remove a file, folder or link; a link is removed itself, never followed into its target."""
    if entry.is_symlink() or os.path.isjunction(entry):
        # A link (a symlink, or a Windows directory junction) is removed itself, never followed into its target.
        try:
            entry.unlink()
        except IsADirectoryError, PermissionError:
            entry.rmdir()  # how Windows removes a directory junction
    elif entry.is_dir():
        shutil.rmtree(entry)
    else:
        entry.unlink()


def empty_tmp(paths: DataPaths) -> None:
    """Empty tmp\\ (leftovers of a crash, 06 section 4). An entry that can't be removed is logged and skipped,
    so one locked file can't stop start-up."""
    for entry in paths.tmp.iterdir():
        try:
            remove_entry(entry)
        except OSError as error:
            _log.warning("Couldn't remove %s from tmp: %s", entry.name, error)


def write_runtime_json(paths: DataPaths, port: int, pid: int) -> None:
    """Write the port in use and the PID, and nothing else (04 section 8), in one atomic replace."""
    temporary = paths.runtime_json.with_name("runtime.json.tmp")
    temporary.write_text(json.dumps({"port": port, "pid": pid}), encoding="utf-8")
    os.replace(temporary, paths.runtime_json)


class UiMissingError(Exception):
    r"""An installed copy has no built UI (`ui\index.html`). A start-up error: the server must not run without it."""


def _version_folder(package_file: Path) -> Path:
    r"""The folder that holds the `shelfsync` package: `versions\<v>` when installed, `backend` in the source layout."""
    return package_file.resolve().parents[1]


def is_packaged_layout(package_file: Path | None = None) -> bool:
    """True when the package sits in an embedded-Python folder (the installed copy, or the build folder before it is
    packed): the embeddable package always has a `python*._pth` file beside the package; the source layout does not."""
    folder = _version_folder(package_file or Path(__file__))
    return any(folder.glob("python*._pth"))


def source_ui_dir(package_file: Path | None = None) -> Path:
    """`<repo>/frontend/dist`, the source layout's build folder (`npm run build`)."""
    return _version_folder(package_file or Path(__file__)).parent / "frontend" / "dist"


def ui_dir(package_file: Path | None = None) -> Path:
    """The built UI the server serves. A packaged copy uses `<version folder>\\ui` and raises `UiMissingError` when it
    has no `index.html`; the source layout keeps `frontend/dist`, which may be missing (API only, M1a)."""
    file = package_file or Path(__file__)
    if not is_packaged_layout(file):
        return source_ui_dir(file)
    folder = _version_folder(file) / "ui"
    if not (folder / "index.html").is_file():
        raise UiMissingError(f"The installed copy has no UI in {folder}")
    return folder


TRAY_ICON_FOLDER = "tray"  # `<version folder>\\tray` when packaged (build.py copies brand/assets/tray there)


def tray_icon_dir(package_file: Path | None = None) -> Path:
    """The tray icons (`tray-<state>-<light|dark>.ico`). A packaged copy has them in `<version folder>\\tray`; the
    source layout reads `<repo>/brand/assets/tray`. Raises nothing: a missing folder shows up when an icon is loaded
    (and in the build's smoke test, which loads every one)."""
    file = package_file or Path(__file__)
    if is_packaged_layout(file):
        return _version_folder(file) / TRAY_ICON_FOLDER
    return _version_folder(file).parent / "brand" / "assets" / "tray"
