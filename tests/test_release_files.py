"""SYS-01, SYS-08: guard rails on the release workflow and the installer script, checked as text (the real run is
release.yml itself and the local rehearsal): pinned actions, least privilege, the contract keys, delete order."""

import importlib.util
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RELEASE = (REPO / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
CHECKS = (REPO / ".github" / "workflows" / "checks.yml").read_text(encoding="utf-8")
NSI = (REPO / "packaging" / "ShelfSync.nsi").read_text(encoding="utf-8")

USES = re.compile(r"^\s*(?:-\s+)?uses:\s*(\S+)@([0-9a-f]{40})\s*#\s*(\S+)", re.MULTILINE)


def used(text: str) -> set[tuple[str, str]]:
    return {(name, sha) for name, sha, _ in USES.findall(text)}


def test_every_action_is_pinned_by_commit_sha_and_already_pinned_in_checks() -> None:
    """Supply chain: no new action; the same commits checks.yml pins."""
    all_uses = re.findall(r"^\s*(?:-\s+)?uses:\s*(\S+)", RELEASE, re.MULTILINE)
    pinned = re.findall(r"^\s*(?:-\s+)?uses:\s*\S+@[0-9a-f]{40}\s*#", RELEASE, re.MULTILINE)
    assert all_uses and len(all_uses) == len(pinned)  # every `uses:` has a 40-hex commit and a version comment
    assert used(RELEASE) <= used(CHECKS)


def test_the_workflow_triggers_on_v_tags_and_manual_runs_only() -> None:
    """SYS-01."""
    assert 'tags: ["v*"]' in RELEASE and "workflow_dispatch:" in RELEASE
    assert "pull_request" not in RELEASE.split("jobs:")[0]
    assert "runs-on: windows-2025" in RELEASE


def test_read_only_by_default_and_only_the_draft_job_may_write() -> None:
    """06 section 6: contents: write in one job, which runs only for tags and runs no repository code."""
    head, jobs = RELEASE.split("\njobs:\n", 1)
    assert "permissions:\n  contents: read" in head
    assert jobs.count("contents: write") == 1
    draft = jobs.split("  draft-release:")[1]
    assert "contents: write" in draft and "if: github.ref_type == 'tag'" in draft
    assert "uses: actions/checkout" not in draft  # no repository code in the job that can write
    assert "--draft" in draft and "--verify-tag" in draft


def test_no_secret_is_used_and_nothing_is_signed() -> None:
    """06 section 6."""
    assert "secrets." not in RELEASE
    assert "signtool" not in RELEASE.lower()
    assert "UV_PYTHON_DOWNLOADS: never" in RELEASE


def test_the_nsis_zip_is_checked_against_the_pinned_hash() -> None:
    """04-A V37, V50: the hash is the one in 04 section 2.1."""
    text = (REPO / "docs" / "04-architecture.md").read_text(encoding="utf-8")
    pinned = "ba63dffc4410ee89193e1cb5a41989991bd77c61068da17e3156d136b7b0b3d8"
    assert pinned in text and pinned in RELEASE


def test_the_release_workflow_runs_the_smoke_the_installer_test_and_the_sentinel() -> None:
    """04-A V38, V40, V47."""
    for step in ("packaging/build.py", "packaging/smoke.py", "makensis", "packaging/test-installer.ps1"):
        assert step in RELEASE or step.removeprefix("packaging/") in RELEASE
    assert "-RemoveData" in RELEASE


def test_the_installer_is_per_user_and_writes_the_contract_keys() -> None:
    """m1b.2 section 0: the Uninstall key's values, exactly."""
    assert "RequestExecutionLevel user" in NSI and "Unicode true" in NSI
    assert 'InstallDir "$LOCALAPPDATA\\Programs\\ShelfSync"' in NSI
    for value in (
        '"DisplayName" "ShelfSync"',
        '"DisplayVersion" "${VERSION}"',
        '"Publisher" "${PUBLISHER}"',
        '"DisplayIcon"',
        '"UninstallString" \'"$INSTDIR\\uninstall.exe"\'',
        '"InstallLocation" "$INSTDIR"',
        '"NoModify" 1',
        '"NoRepair" 1',
    ):
        assert value in NSI, value
    assert '!define PUBLISHER "TecHaust Technologies"' in NSI
    assert 'Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\ShelfSync${SUFFIX}"' in NSI
    assert "Software\\Classes\\AppUserModelId\\${AUMID}" in NSI and '!define AUMID "TecHaust.ShelfSync${SUFFIX}"' in NSI


def test_no_plugin_beyond_the_builtin_ones_is_used() -> None:
    """Supply chain: MUI2, nsDialogs, nsExec, LogicLib, FileFunc, WordFunc only."""
    plugins = set(re.findall(r"^\s*(\w+)::", NSI, re.MULTILINE))
    assert plugins <= {"nsExec", "nsDialogs"}
    assert "!addplugindir" not in NSI.lower()


def test_uninstall_order_is_current_first_then_links_then_versions() -> None:
    """V40: raw `RMDir /r` follows junctions on NSIS 3.13 (checked on this PC), so `current` and links go first."""
    section = NSI.split('Section "Uninstall"')[1]
    order = [
        section.index("shelfsync.uninstall --remove-data"),
        section.index('RMDir "$INSTDIR\\current"'),
        section.index('!insertmacro RemoveTreeSafely "un." "$INSTDIR\\versions"'),
        section.index('Delete "$SMPROGRAMS'),
        section.index("DeleteRegValue HKCU"),
        section.index("DeleteRegKey HKCU"),
        section.index('RMDir "$INSTDIR"'),
    ]
    assert order == sorted(order)
    assert "RMDir /r" not in section  # only through the macro that unlinks first
    assert "UnlinkAll" in NSI and "dir /AL" in NSI


def test_data_is_kept_unless_the_box_is_ticked() -> None:
    """SYS-08: unticked by default; the module runs only when ticked (or /REMOVEDATA)."""
    assert "${NSD_SetState} $RemoveDataBox ${BST_UNCHECKED}" in NSI
    assert "${If} $RemoveData == 1" in NSI
    assert "/REMOVEDATA" in NSI


def test_the_smoke_test_reports_what_changed() -> None:
    """V47: added, removed and changed files are all differences."""
    spec = importlib.util.spec_from_file_location("shelfsync_packaging_smoke", REPO / "packaging" / "smoke.py")
    assert spec is not None and spec.loader is not None
    smoke = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(smoke)
    before = {"a": (1, "x"), "b": (2, "y"), "c": (3, "z")}
    after = {"a": (1, "x"), "b": (2, "CHANGED"), "d": (4, "w")}
    assert smoke.changes(before, after) == ["added: d", "removed: c", "changed: b"]
    assert smoke.changes(before, dict(before)) == []
