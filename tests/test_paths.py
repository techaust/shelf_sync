"""The data folder and its override."""

import subprocess
import sys
from pathlib import Path

import pytest

from shelfsync.paths import (
    DATA_DIR_ENV,
    DataPaths,
    create_data_folders,
    empty_tmp,
    prepare_data_folder,
    resolve_data_paths,
)


def test_an_entry_that_cant_be_removed_is_logged_and_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    paths = DataPaths(tmp_path / "ShelfSync")
    create_data_folders(paths)
    (paths.tmp / "locked.bin").write_text("x")
    (paths.tmp / "ordinary.bin").write_text("x")
    real_unlink = Path.unlink

    def unlink(self: Path, missing_ok: bool = False) -> None:
        if self.name == "locked.bin":
            raise PermissionError("in use")
        real_unlink(self, missing_ok)

    monkeypatch.setattr(Path, "unlink", unlink)
    with caplog.at_level("WARNING"):
        empty_tmp(paths)  # does not raise
    assert [p.name for p in paths.tmp.iterdir()] == ["locked.bin"]
    assert "locked.bin" in caplog.text


@pytest.mark.windows
@pytest.mark.skipif(sys.platform != "win32", reason="Windows only: directory junctions")
def test_a_junction_in_tmp_is_removed_without_touching_its_target(tmp_path: Path) -> None:
    paths = DataPaths(tmp_path / "ShelfSync")
    create_data_folders(paths)
    target = tmp_path / "precious"
    target.mkdir()
    (target / "keep.txt").write_text("keep")
    link = paths.tmp / "link"
    subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True)
    empty_tmp(paths)
    assert list(paths.tmp.iterdir()) == []
    assert (target / "keep.txt").read_text() == "keep"


def test_env_var_overrides_the_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DATA_DIR_ENV, str(tmp_path / "x"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "ignored"))
    assert resolve_data_paths().root == tmp_path / "x"


def test_default_is_localappdata_shelfsync(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(DATA_DIR_ENV, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert resolve_data_paths().root == tmp_path / "ShelfSync"


def test_no_location_is_a_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(DATA_DIR_ENV, raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    with pytest.raises(RuntimeError, match=DATA_DIR_ENV):
        resolve_data_paths()


def test_layout(tmp_path: Path) -> None:
    paths = DataPaths(tmp_path / "ShelfSync")
    prepare_data_folder(paths)
    assert paths.logs == paths.root / "logs"
    assert paths.tmp.is_dir() and paths.backups.is_dir() and paths.logs.is_dir()
    assert paths.runtime_json == paths.root / "runtime.json"
