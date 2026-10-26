"""The data folder (04 section 8): %LOCALAPPDATA%\\ShelfSync\\ with logs\\, tmp\\, backups\\ and runtime.json."""

import json
import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

_log = logging.getLogger("shelfsync.paths")

DATA_DIR_ENV = "SHELFSYNC_DATA_DIR"  # for tests and Linux CI; nothing else overrides the root


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


def _remove_entry(entry: Path) -> None:
    if entry.is_symlink() or os.path.isjunction(entry):
        # A link (a symlink, or a Windows directory junction) is removed itself, never followed into its target.
        try:
            entry.unlink()
        except (IsADirectoryError, PermissionError):
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
            _remove_entry(entry)
        except OSError as error:
            _log.warning("Couldn't remove %s from tmp: %s", entry.name, error)


def prepare_data_folder(paths: DataPaths) -> None:
    """Create the folders and empty tmp\\."""
    create_data_folders(paths)
    empty_tmp(paths)


def write_runtime_json(paths: DataPaths, port: int, pid: int) -> None:
    """Write the port in use and the PID, and nothing else (04 section 8), in one atomic replace."""
    temporary = paths.runtime_json.with_name("runtime.json.tmp")
    temporary.write_text(json.dumps({"port": port, "pid": pid}), encoding="utf-8")
    os.replace(temporary, paths.runtime_json)
