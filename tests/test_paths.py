"""The data folder and its override."""

from pathlib import Path

import pytest

from shelfsync.paths import DATA_DIR_ENV, DataPaths, prepare_data_folder, resolve_data_paths


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
