"""UI-TRAY, SYS-01: the tray icons are found in both layouts (the installed copy shipped none and its tray failed)."""

from pathlib import Path

import pytest

from shelfsync.paths import tray_icon_dir
from shelfsync.tray.icons import icon_file, load_icon
from shelfsync.tray.state import IconState
from tests.test_packaging_build import build

REPO = Path(__file__).resolve().parents[1]


def packaged_init(tmp_path: Path) -> Path:
    version = tmp_path / "versions" / "1.2.3"
    (version / "shelfsync").mkdir(parents=True)
    (version / "python314._pth").write_text("python314.zip\n.\n", encoding="utf-8")
    init = version / "shelfsync" / "__init__.py"
    init.write_text("", encoding="utf-8")
    return init


def test_a_packaged_copy_reads_the_icons_from_a_tray_folder_beside_the_package(tmp_path: Path) -> None:
    """SYS-01: `<version folder>/tray`, the folder build.py fills."""
    assert tray_icon_dir(packaged_init(tmp_path)) == (tmp_path / "versions" / "1.2.3" / "tray").resolve()


def test_the_source_layout_reads_brand_assets_tray(tmp_path: Path) -> None:
    """UI-TRAY: the development layout, unchanged."""
    package = tmp_path / "repo" / "backend" / "shelfsync"
    package.mkdir(parents=True)
    init = package / "__init__.py"
    init.write_text("", encoding="utf-8")
    assert tray_icon_dir(init) == (tmp_path / "repo" / "brand" / "assets" / "tray").resolve()
    assert tray_icon_dir() == REPO / "brand" / "assets" / "tray"


def test_every_tray_icon_exists_in_the_source_layout_and_loads() -> None:
    """UI-TRAY: all six, through the same path helper the tray uses."""
    for state in IconState:
        for light in (True, False):
            path = icon_file(state, light)
            assert path.parent == tray_icon_dir() and path.is_file()
            load_icon(path, 16).close()


def test_the_icon_names_the_build_ships_are_the_names_the_tray_asks_for() -> None:
    """SYS-01: build.py's list and icons.icon_file can't drift apart."""
    wanted = {icon_file(state, light).name for state in IconState for light in (True, False)}
    assert wanted == set(build.TRAY_ICON_NAMES)


def test_the_build_copies_the_six_icons_and_stops_when_one_is_missing(tmp_path: Path) -> None:
    """SYS-01: they land in `tray/`, so they are in files.txt and the signed manifest."""
    source = tmp_path / "source"
    source.mkdir()
    for name in build.TRAY_ICON_NAMES:
        (source / name).write_bytes(b"ico")
    build.copy_tray_icons(source, tmp_path / "out" / "tray")
    assert sorted(p.name for p in (tmp_path / "out" / "tray").iterdir()) == sorted(build.TRAY_ICON_NAMES)
    entries = build.file_listing(tmp_path / "out")
    assert [e.path for e in entries] == sorted(f"tray/{name}" for name in build.TRAY_ICON_NAMES)
    (source / build.TRAY_ICON_NAMES[0]).unlink()
    with pytest.raises(build.BuildError, match="missing tray icons"):
        build.copy_tray_icons(source, tmp_path / "out2" / "tray")


def test_the_smoke_test_loads_the_launcher_and_every_icon_and_quits_through_request_quit() -> None:
    """SYS-01: the class of miss that shipped no icons fails the build's smoke test."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("shelfsync_packaging_smoke2", REPO / "packaging" / "smoke.py")
    assert spec is not None and spec.loader is not None
    smoke = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(smoke)
    assert "tray_icon_dir" in smoke.ICONS_PROBE and "load_icon" in smoke.ICONS_PROBE
    assert "from shelfsync.tray import launcher" in smoke.ICONS_PROBE
    assert "request_quit" in smoke.LAUNCHER_ENTRY and '["--background"]' in smoke.LAUNCHER_ENTRY


def test_the_default_icon_folder_is_worked_out_once() -> None:
    """UI-TRAY: icon_file asks `default_icon_dir()` on every repaint; it is cached."""
    from shelfsync.tray import icons

    icons.default_icon_dir.cache_clear()
    for _ in range(3):
        icon_file(IconState.NORMAL, True)
    info = icons.default_icon_dir.cache_info()
    assert info.misses == 1 and info.hits == 2
