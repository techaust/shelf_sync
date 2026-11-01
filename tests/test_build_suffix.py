"""SYS-04, SYS-05: a build's suffix (`platform/names.py`). A normal build, a development run and every test use the
real `ShelfSync` Run value and `TecHaust.ShelfSync` AUMID; a build made with `--suffix` uses the suffixed names its
installer writes; a suffix file that is present but invalid never yields the real names. Only fakes and throwaway
copies of the package are used: the real Run key and AUMID key are never touched."""

import importlib.util
import logging
import shutil
import subprocess
import sys
import types
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from shelfsync.platform import aumid, autostart, names, notify
from shelfsync.platform.autostart import (
    AutostartError,
    FakeRunKey,
    apply_start_with_windows,
    apply_start_with_windows_safely,
)
from shelfsync.tray import launcher

REPO = Path(__file__).resolve().parents[1]
COMMAND = r'"C:\Users\x\AppData\Local\Programs\ShelfSync\current\pythonw.exe" -m shelfsync.launcher --background'


def _load(name: str, file: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, REPO / "packaging" / file)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build = _load("shelfsync_packaging_build_suffix", "build.py")
smoke = _load("shelfsync_packaging_smoke_suffix", "smoke.py")

INVALID_FILES = [
    b"",  # present but empty: a suffixed build always writes one
    b"rehearsal",  # no leading dash
    b"-",  # nothing after the dash
    b"-" + b"a" * 33,  # too long
    b"-a b",
    b"-a/b",
    b"-a\\b",
    b" -ok",
    b"-ok ",
    b"-ok\n\n",
    b"\xef\xbb\xbf-ok",  # a byte-order mark
    "-r\u00e9p".encode(),  # not ASCII
    b"-ok\x00",
    b"-" + b"a" * 100,  # longer than the reader reads
]


# ---- the names (names.py) ---------------------------------------------------------------------------------------


def test_a_normal_build_or_a_development_run_uses_the_real_names() -> None:
    """SYS-04, SYS-05: the source tree has no suffix file, so the app's names are the ones the installer writes
    without /DSUFFIX."""
    assert not names.SUFFIX_FILE.exists()
    assert names.BUILD_SUFFIX == ""
    assert names.RUN_VALUE_NAME == autostart.VALUE_NAME == "ShelfSync"
    assert names.AUMID == aumid.AUMID == "TecHaust.ShelfSync"


def test_a_suffixed_build_carries_the_suffix_in_both_names(tmp_path: Path) -> None:
    """SYS-04, SYS-05: what `build.py --suffix=-rehearsal` writes reads back as the installer's suffixed names."""
    file = tmp_path / names.SUFFIX_FILE_NAME
    file.write_bytes(b"-rehearsal")
    suffix = names.read_build_suffix(file)
    assert suffix == "-rehearsal"
    assert names.run_value_name(suffix) == "ShelfSync-rehearsal"
    assert names.aumid_for(suffix) == "TecHaust.ShelfSync-rehearsal"


def test_no_file_means_no_suffix(tmp_path: Path) -> None:
    """SYS-04, SYS-05: the real names."""
    suffix = names.read_build_suffix(tmp_path / names.SUFFIX_FILE_NAME)
    assert suffix == ""
    assert (names.run_value_name(suffix), names.aumid_for(suffix)) == ("ShelfSync", "TecHaust.ShelfSync")


@pytest.mark.parametrize("ending", [b"\n", b"\r\n"])
def test_one_trailing_line_end_is_allowed(tmp_path: Path, ending: bytes) -> None:
    """SYS-04: a file saved by an editor still reads as the suffix."""
    file = tmp_path / names.SUFFIX_FILE_NAME
    file.write_bytes(b"-a.b_c-1" + ending)
    assert names.read_build_suffix(file) == "-a.b_c-1"


@pytest.mark.parametrize("content", INVALID_FILES)
def test_an_invalid_suffix_file_never_yields_the_real_names(tmp_path: Path, content: bytes) -> None:
    """SYS-04, SYS-05: no Run value name and no AUMID (None), never `ShelfSync` or `TecHaust.ShelfSync`."""
    file = tmp_path / names.SUFFIX_FILE_NAME
    file.write_bytes(content)
    suffix = names.read_build_suffix(file)
    assert suffix is None
    assert names.run_value_name(suffix) is None
    assert names.aumid_for(suffix) is None


def test_a_suffix_file_that_cant_be_read_never_yields_the_real_names(tmp_path: Path) -> None:
    """SYS-04, SYS-05: a folder where the file should be can't be read as one."""
    (tmp_path / names.SUFFIX_FILE_NAME).mkdir()
    assert names.read_build_suffix(tmp_path / names.SUFFIX_FILE_NAME) is None


@pytest.mark.parametrize("suffix", ["rehearsal", "-", "-a b", "-" + "a" * 33, "-\u00e9"])
def test_the_name_functions_refuse_an_invalid_suffix_too(suffix: str) -> None:
    """SYS-04, SYS-05."""
    assert names.run_value_name(suffix) is None
    assert names.aumid_for(suffix) is None


@pytest.mark.parametrize("suffix", ["", "-rehearsal", "-a.b_c-1", "-" + "x" * 32, "-A9"])
def test_the_rule_accepts_empty_or_a_dash_and_1_to_32_allowed_characters(suffix: str) -> None:
    """SYS-04, SYS-05."""
    assert names.is_valid_suffix(suffix)


@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(content=st.binary(max_size=80))
def test_a_present_suffix_file_never_reads_as_the_real_names(tmp_path: Path, content: bytes) -> None:
    """SYS-04, SYS-05 (property): whatever a present file holds, it reads as a valid non-empty suffix or as None,
    never as "" (the real names)."""
    file = tmp_path / names.SUFFIX_FILE_NAME
    file.write_bytes(content)
    suffix = names.read_build_suffix(file)
    assert suffix != ""
    assert names.run_value_name(suffix) != "ShelfSync"
    assert names.aumid_for(suffix) != "TecHaust.ShelfSync"
    if suffix is not None:
        assert names.is_valid_suffix(suffix) and suffix.startswith("-")


# ---- the package as a build would ship it (a throwaway copy, its own Python process) ------------------------------


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (None, ["ShelfSync", "TecHaust.ShelfSync", "TecHaust.ShelfSync"]),
        (b"-rehearsal", ["ShelfSync-rehearsal", "TecHaust.ShelfSync-rehearsal", "TecHaust.ShelfSync-rehearsal"]),
        (b"rehearsal", ["None", "None", "None"]),
    ],
)
def test_a_copy_of_the_package_reads_its_own_suffix_file(
    tmp_path: Path, content: bytes | None, expected: list[str]
) -> None:
    """SYS-04, SYS-05: the file next to `names.py` decides the names the app uses (autostart's Run value, aumid's
    AUMID and the toast's AUMID of a registered installed copy); an invalid one gives none at all."""
    package = tmp_path / "shelfsync"
    shutil.copytree(REPO / "backend" / "shelfsync", package, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    if content is not None:
        (tmp_path / build.SUFFIX_FILE).write_bytes(content)
    probe = (
        f"import sys; sys.path.insert(0, {str(tmp_path)!r}); "
        "from shelfsync.platform import aumid, autostart, notify; "
        "assert autostart.__file__.startswith(sys.path[0]); "
        "print(autostart.VALUE_NAME); print(aumid.AUMID); print(notify.toast_aumid(True, True))"
    )
    done = subprocess.run(
        [sys.executable, "-I", "-B", "-c", probe], capture_output=True, text=True, timeout=120, check=False
    )
    assert done.returncode == 0, done.stderr[-800:]
    assert done.stdout.split() == expected


@pytest.mark.parametrize("suffix", ["", "-rehearsal"])
def test_the_smoke_probe_reports_the_names_a_build_with_that_suffix_expects(tmp_path: Path, suffix: str) -> None:
    """SYS-04, SYS-05: smoke.py's own probe, run against a copy of the package built with `suffix`."""
    package = tmp_path / "shelfsync"
    shutil.copytree(REPO / "backend" / "shelfsync", package, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    build.write_build_suffix(tmp_path, suffix)
    probe = f"import sys; sys.path.insert(0, {str(tmp_path)!r}); " + smoke.NAMES_PROBE
    done = subprocess.run(
        [sys.executable, "-I", "-B", "-c", probe], capture_output=True, text=True, timeout=120, check=False
    )
    assert done.returncode == 0, done.stderr[-800:]
    assert done.stdout.split() == smoke.expected_names(suffix) == [f"ShelfSync{suffix}", f"TecHaust.ShelfSync{suffix}"]


# ---- the Run value (autostart.py), the settings API and the launcher --------------------------------------------


def test_a_suffixed_build_writes_and_removes_only_its_own_run_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """SYS-04: the real `ShelfSync` value (an installed copy's) is left alone by a rehearsal copy."""
    monkeypatch.setattr(autostart, "VALUE_NAME", "ShelfSync-rehearsal")
    key = FakeRunKey()
    key.values["ShelfSync"] = "the real one"
    assert apply_start_with_windows(True, key, command=COMMAND, installed=True) == "set"
    assert key.values == {"ShelfSync": "the real one", "ShelfSync-rehearsal": COMMAND}
    assert apply_start_with_windows(False, key, installed=True) == "removed"
    assert key.values == {"ShelfSync": "the real one"}


@pytest.mark.parametrize("enabled", [True, False])
def test_an_invalid_suffix_file_leaves_every_run_value_alone(monkeypatch: pytest.MonkeyPatch, enabled: bool) -> None:
    """SYS-04: no name, so nothing is written or removed, and the real `ShelfSync` value least of all."""
    monkeypatch.setattr(autostart, "VALUE_NAME", None)
    key = FakeRunKey()
    key.values["ShelfSync"] = "the real one"
    with pytest.raises(AutostartError, match="suffix file is invalid"):
        apply_start_with_windows(enabled, key, command=COMMAND, installed=True)
    assert key.values == {"ShelfSync": "the real one"}


def test_the_safe_apply_reports_an_invalid_suffix_file_as_failed(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """SYS-04: "failed" with a warning in the log (a broken build), not "skipped" (a development copy)."""
    monkeypatch.setattr(autostart, "VALUE_NAME", None)
    key = FakeRunKey()
    with caplog.at_level(logging.WARNING, logger="shelfsync.autostart"):
        assert apply_start_with_windows_safely(True, key, installed=True) == "failed"
    assert key.values == {}
    assert "suffix file is invalid" in caplog.text


def test_a_development_run_with_an_invalid_suffix_file_is_still_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    """SYS-04: a copy that isn't installed touches nothing, as before."""
    monkeypatch.setattr(autostart, "VALUE_NAME", None)
    assert apply_start_with_windows_safely(True, FakeRunKey(), installed=False) == "skipped"


def test_a_throwaway_name_is_still_used_as_given(monkeypatch: pytest.MonkeyPatch) -> None:
    """SYS-04: the Windows tests pass their own `name`; it wins over this build's (even an invalid build's)."""
    monkeypatch.setattr(autostart, "VALUE_NAME", None)
    key = FakeRunKey()
    assert apply_start_with_windows(True, key, name="ShelfSync-test-x", command=COMMAND, installed=True) == "set"
    assert key.values == {"ShelfSync-test-x": COMMAND}


def test_the_settings_api_says_failed_for_an_invalid_suffix_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SET-06, SYS-04: `start_with_windows_result` keeps its three values; the Run key is untouched."""
    from tests.test_app_settings import GOOD, Rig, put

    monkeypatch.setattr(autostart, "VALUE_NAME", None)
    rig = Rig(tmp_path)
    try:
        rig.run_key.values["ShelfSync"] = "the real one"
        response = put(rig, {**GOOD, "start_with_windows": True})
        assert response.status_code == 200
        assert response.json()["start_with_windows_result"] == "failed"
        assert rig.run_key.values == {"ShelfSync": "the real one"}
    finally:
        rig.close()


def test_the_launcher_logs_an_invalid_suffix_file_and_starts(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """SYS-04: the start-up hook goes through the safe apply: a warning, no exception, no value."""
    monkeypatch.setattr(autostart, "VALUE_NAME", None)
    key = FakeRunKey()
    with caplog.at_level(logging.WARNING, logger="shelfsync.autostart"):
        launcher.make_on_settings(key, installed=True)({"start_with_windows": True})
    assert key.values == {}
    assert "suffix file is invalid" in caplog.text


# ---- the toast AUMID (aumid.py, notify.py) ------------------------------------------------------------------------


def test_a_suffixed_build_sends_toasts_as_its_own_aumid(monkeypatch: pytest.MonkeyPatch) -> None:
    """SYS-05: the AUMID its installer registered."""
    monkeypatch.setattr(aumid, "AUMID", "TecHaust.ShelfSync-rehearsal")
    assert notify.toast_aumid(installed=True, registered=True) == "TecHaust.ShelfSync-rehearsal"


def test_an_invalid_suffix_file_sends_toasts_with_no_aumid(monkeypatch: pytest.MonkeyPatch) -> None:
    """SYS-05: no AUMID (windows-toasts' default), never `TecHaust.ShelfSync`; and it is never "registered"."""
    monkeypatch.setattr(aumid, "AUMID", None)
    assert aumid.is_registered() is False
    assert notify.toast_aumid(installed=True, registered=True) is None

    calls: list[str | None] = []

    class FakeToaster:
        def __init__(self, text: str, notifierAUMID: str | None = None) -> None:
            calls.append(notifierAUMID)

        def show_toast(self, toast: object) -> None: ...

    module: Any = types.SimpleNamespace(InteractableWindowsToaster=FakeToaster, Toast=lambda fields: fields)
    monkeypatch.setitem(sys.modules, "windows_toasts", module)
    monkeypatch.setattr(notify, "_toaster", None)
    monkeypatch.setattr(notify, "is_installed_copy", lambda: True)
    notify.show_toast(["a"])
    assert calls == [None]
