"""The data folder (04 section 8): %LOCALAPPDATA%\\ShelfSync\\ with logs\\, tmp\\, backups\\ and runtime.json."""

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

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


def prepare_data_folder(paths: DataPaths) -> None:
    """Create the folders and empty tmp\\ (leftovers of a crash, 06 section 4)."""
    for folder in (paths.root, paths.logs, paths.backups, paths.tmp):
        folder.mkdir(parents=True, exist_ok=True)
    for entry in paths.tmp.iterdir():
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()  # a symlink is removed itself, never followed


def write_runtime_json(paths: DataPaths, port: int, pid: int) -> None:
    """Write the port in use and the PID, and nothing else (04 section 8), in one atomic replace."""
    temporary = paths.runtime_json.with_name("runtime.json.tmp")
    temporary.write_text(json.dumps({"port": port, "pid": pid}), encoding="utf-8")
    os.replace(temporary, paths.runtime_json)
