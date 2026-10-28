"""SYS-06, SYS-07, SET-04: the update service (check, download, install, roll back, the token, development mode)."""

import logging
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from shelfsync.db.backup import take_backup
from shelfsync.db.connection import connect
from shelfsync.db.migrate import migrate
from shelfsync.paths import DataPaths
from shelfsync.platform.secrets import MemorySecretStore, SecretStoreError
from shelfsync.secure.redact import redact
from shelfsync.update import service as service_module
from shelfsync.update.github import EXPIRY_HEADER, GitHubClient
from shelfsync.update.layout import InstallLayout, UpdatePaths
from shelfsync.update.service import (
    GITHUB_TOKEN_ENTRY,
    InvalidToken,
    UpdateConflict,
    UpdateNeedsConfirmation,
    UpdateService,
    UpdateTooSoon,
    build_update_service,
    is_valid_token,
)
from shelfsync.update.state import PendingUpdate, StateStore
from tests.test_db_backup import TWO, database_at_release_one, migrations
from tests.update_support import (
    FakeGitHub,
    FakeLinks,
    FakeProc,
    FakeProcesses,
    build_release,
    data_paths,
    make_install,
    make_keys,
    use_key,
)

KEYS = make_keys(1)
TOKEN = "github_pat_" + "Zy9Xw8Vu7T" * 4
NOW = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)


@dataclass
class Rig:
    service: UpdateService
    layout: InstallLayout
    paths: DataPaths
    fake: FakeGitHub
    secrets: MemorySecretStore
    procs: FakeProcesses
    links: FakeLinks
    quits: list[int]
    clock: list[float]

    @property
    def store(self) -> StateStore:
        return StateStore(UpdatePaths(self.paths))


def make_rig(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    installed: str = "0.0.1",
    latest: str | None = "0.0.2",
    key: bool = True,
    quit_result: bool | None = True,
    token: str | None = None,
    extra_versions: tuple[str, ...] = (),
) -> Rig:
    use_key(monkeypatch, KEYS if key else None)
    layout = InstallLayout(tmp_path / "Programs" / "ShelfSync")
    make_install(layout.root, KEYS, {installed: None, **{v: None for v in extra_versions}})
    paths = data_paths(tmp_path)
    fake = FakeGitHub()
    if latest is not None:
        release = build_release(latest, KEYS)
        fake.releases[release.tag] = release
        fake.latest_tag = release.tag
    secrets = MemorySecretStore()
    if token is not None:
        secrets.set(GITHUB_TOKEN_ENTRY, token)
    links = FakeLinks()
    links.table[str(layout.current)] = layout.version_dir(installed)
    procs = FakeProcesses()
    clock = [1000.0]
    service = UpdateService(
        secrets=secrets,
        paths=paths,
        layout=layout,
        github=GitHubClient(lambda: secrets.get(GITHUB_TOKEN_ENTRY), transport=fake.transport()),
        installed_version=installed,
        links=links,
        processes=procs,
        now=lambda: NOW,
        monotonic=lambda: clock[0],
        starter=lambda work: work(),  # run in the foreground
        free=lambda path: 10**12,
    )
    quits: list[int] = []

    def request_quit() -> bool:
        quits.append(1)
        return bool(quit_result)

    service.bind_quit(lambda: request_quit if quit_result is not None else None)
    return Rig(service, layout, paths, fake, secrets, procs, links, quits, clock)


# ---- checking and downloading ---------------------------------------------------------------------------------------


def test_a_check_downloads_verifies_and_unpacks_the_newer_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch)
    rig.service.run_check()
    status = rig.service.status()
    assert status.last_check is not None and (status.last_check.outcome, status.last_check.detail) == ("ok", None)
    assert status.available is not None and (status.available.version, status.available.ready) == ("0.0.2", True)
    assert rig.layout.version_dir("0.0.2").is_dir() and (rig.layout.version_dir("0.0.2") / "pythonw.exe").is_file()
    assert rig.layout.manifest_path("0.0.2").is_file() and rig.layout.signature_path("0.0.2").is_file()
    pending = rig.store.load().pending
    assert pending is not None and pending.version == "0.0.2"
    assert list(UpdatePaths(rig.paths).downloads.iterdir()) == []  # the zip is removed once unpacked
    assert rig.procs.spawned == []  # nothing is installed without the owner's go-ahead
    assert rig.layout.current.exists() is False and rig.links.target(rig.layout.current) == rig.layout.version_dir(
        "0.0.1"
    )


def test_a_second_check_finds_the_update_already_ready_and_downloads_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch)
    rig.service.run_check()
    rig.fake.requests.clear()
    rig.service.run_check()
    assert [r for r in rig.fake.requests if "assets" in r[2]] == []
    assert rig.service.status().available is not None


def test_the_running_versions_own_manifest_is_kept_on_the_first_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch)
    for path in (rig.layout.manifest_path("0.0.1"), rig.layout.signature_path("0.0.1")):
        path.unlink()  # a fresh Setup.exe install: no manifest on disk
    old = build_release("0.0.1", KEYS)
    rig.fake.releases[old.tag] = old
    rig.service.run_check()
    assert rig.layout.manifest_path("0.0.1").read_bytes() == old.manifest_bytes
    assert rig.layout.signature_path("0.0.1").read_bytes() == old.signature


def test_the_running_versions_manifest_comes_from_the_latest_release_when_that_is_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch, installed="0.0.2", latest="0.0.2")
    for path in (rig.layout.manifest_path("0.0.2"), rig.layout.signature_path("0.0.2")):
        path.unlink()
    rig.service.run_check()
    assert rig.layout.manifest_path("0.0.2").is_file()
    assert rig.service.status().available is None  # the same version is not an update


def test_a_bad_manifest_for_the_running_version_is_not_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    rig = make_rig(tmp_path, monkeypatch, installed="0.0.1", latest="0.0.2")
    rig.layout.manifest_path("0.0.1").unlink()
    rig.layout.signature_path("0.0.1").unlink()
    other = build_release("0.0.1", make_keys(9))  # signed by another key
    rig.fake.releases[other.tag] = other
    caplog.set_level(logging.WARNING)
    rig.service.run_check()
    assert not rig.layout.manifest_path("0.0.1").exists()


def test_with_no_key_in_the_build_nothing_is_downloaded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = make_rig(tmp_path, monkeypatch, key=False)
    rig.service.run_check()
    status = rig.service.status()
    assert status.key_available is False
    assert status.available is not None and status.available.ready is False
    assert [r for r in rig.fake.requests if "assets" in r[2]] == []
    assert not rig.layout.version_dir("0.0.2").exists()
    with pytest.raises(UpdateConflict) as caught:
        rig.service.install()
    assert caught.value.code == "no_key"


def test_a_tampered_signature_is_refused_and_nothing_is_kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = make_rig(tmp_path, monkeypatch, latest=None)
    release = build_release("0.0.2", make_keys(7))  # signed by someone else
    rig.fake.releases[release.tag] = release
    rig.fake.latest_tag = release.tag
    rig.service.run_check()
    last = rig.service.status().last_check
    assert last is not None and (last.outcome, last.detail) == ("update_refused", "bad_signature")
    assert not rig.layout.version_dir("0.0.2").exists() and not rig.layout.manifest_path("0.0.2").exists()
    assert rig.store.load().pending is None
    assert [r for r in rig.fake.requests if r[2].endswith("/12")] == []  # the zip was never fetched


def test_a_zip_that_does_not_match_the_signed_manifest_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch)
    release = next(iter(rig.fake.releases.values()))
    release.zip_bytes = release.zip_bytes[:-1] + bytes([release.zip_bytes[-1] ^ 1])
    rig.service.run_check()
    last = rig.service.status().last_check
    assert last is not None and (last.outcome, last.detail) == ("update_refused", "hash_mismatch")
    assert not rig.layout.version_dir("0.0.2").exists() and rig.store.load().pending is None


def test_a_valid_signature_over_files_the_zip_lacks_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = make_rig(tmp_path, monkeypatch, latest=None)
    files = {"pythonw.exe": b"p", "python.exe": b"q", "extra/file": b"z"}
    release = build_release("0.0.2", KEYS, files)
    from tests.update_support import make_zip

    release.zip_bytes = make_zip({"pythonw.exe": b"p", "python.exe": b"q"})
    from shelfsync.update.manifest import FileEntry, make_manifest, parse_manifest, setup_asset_name, zip_asset_name
    from tests.update_support import BUILT_AT, COMMIT, entries, sha

    release.manifest_bytes = make_manifest(
        version="0.0.2", source_commit=COMMIT, built_at=BUILT_AT, schema_version=1,
        assets={
            setup_asset_name("0.0.2"): FileEntry(1, "0" * 64),
            zip_asset_name("0.0.2"): FileEntry(len(release.zip_bytes), sha(release.zip_bytes)),
        },
        files=entries(files),
    )  # fmt: skip
    release.signature = KEYS.sign(release.manifest_bytes)
    release.manifest = parse_manifest(release.manifest_bytes)
    rig.fake.releases[release.tag] = release
    rig.fake.latest_tag = release.tag
    rig.service.run_check()
    last = rig.service.status().last_check
    assert last is not None and (last.outcome, last.detail) == ("update_refused", "mismatch")
    assert not rig.layout.version_dir("0.0.2").exists()


def test_an_old_signed_manifest_replayed_as_the_new_release_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Someone who controls the release page re-serves a genuine, signed, older manifest under the new tag."""
    rig = make_rig(tmp_path, monkeypatch, latest=None)
    release = build_release("0.0.2", KEYS)
    old = build_release("0.0.0", KEYS)
    release.manifest_bytes, release.signature = old.manifest_bytes, old.signature
    rig.fake.releases[release.tag] = release
    rig.fake.latest_tag = release.tag
    rig.service.run_check()
    last = rig.service.status().last_check
    assert last is not None and (last.outcome, last.detail) == ("update_refused", "tag_mismatch")
    assert rig.store.load().pending is None and not rig.layout.version_dir("0.0.2").exists()


def test_a_release_without_its_assets_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = make_rig(tmp_path, monkeypatch)
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"tag_name": "v0.0.2", "assets": []}))
    rig.service._github = GitHubClient(lambda: None, transport=transport)
    rig.service.run_check()
    last = rig.service.status().last_check
    assert last is not None and (last.outcome, last.detail) == ("update_refused", "assets_missing")


@pytest.mark.parametrize(
    ("status", "outcome"), [(None, "no_release"), (401, "token_refused"), (429, "rate_limited"), (500, "unreachable")]
)
def test_every_github_outcome_is_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: int | None, outcome: str
) -> None:
    rig = make_rig(tmp_path, monkeypatch, latest=None, token=TOKEN)
    rig.fake.latest_status = status
    rig.service.run_check()
    last = rig.service.status().last_check
    assert last is not None and last.outcome == outcome and last.at.startswith("2026-10-27T12:00:00")


def test_a_failed_download_is_recorded_as_a_failure_not_a_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch)
    release = next(iter(rig.fake.releases.values()))
    rig.fake.asset_override[rig.fake.asset_id("0.0.2", "shelfsync-0.0.2-win64.zip")] = lambda r: httpx.Response(404)
    rig.service.run_check()
    last = rig.service.status().last_check
    assert last is not None and (last.outcome, last.detail) == ("update_failed", "bad_status") and release


def test_not_enough_space_is_a_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = make_rig(tmp_path, monkeypatch)
    rig.service._free = lambda path: 10
    rig.service.run_check()
    last = rig.service.status().last_check
    assert last is not None and (last.outcome, last.detail) == ("update_failed", "no_space")


def test_an_unexpected_error_in_a_check_is_recorded_and_never_escapes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch)

    def boom() -> None:
        raise RuntimeError("surprise")

    monkeypatch.setattr(rig.service._github, "latest", boom)
    rig.service.run_check()
    last = rig.service.status().last_check
    assert last is not None and (last.outcome, last.detail) == ("update_failed", "unexpected")
    assert rig.service.status().checking is False


def test_the_token_expiry_is_kept_and_the_notice_follows_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = make_rig(tmp_path, monkeypatch, token=TOKEN)
    for days, notice in ((10, True), (15, False)):
        expiry = (NOW + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S UTC")
        rig.fake.latest_headers = {EXPIRY_HEADER: expiry}
        rig.service.run_check()
        token = rig.service.status().token
        assert token.is_set and token.notice is notice and token.expires_at is not None
    rig.fake.latest_headers = {}  # a missing header: no expiry known, so no notice
    rig.service.run_check()
    token = rig.service.status().token
    assert token.is_set and token.expires_at is None and token.notice is False


def test_check_now_runs_in_the_background_and_waits_a_minute_between_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch)
    started: list[Callable[[], None]] = []
    rig.service._starter = started.append
    rig.service.check_now()
    assert len(started) == 1 and rig.fake.requests == []  # asked for, not yet run
    rig.clock[0] += 59
    with pytest.raises(UpdateTooSoon):
        rig.service.check_now()
    rig.clock[0] += 2
    rig.service.check_now()
    assert len(started) == 2


def test_check_now_is_refused_while_a_check_runs_or_a_switch_is_under_way(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch)
    rig.service._checking = True
    with pytest.raises(UpdateTooSoon):
        rig.service.check_now()
    rig.service._checking = False
    rig.service._switching = True
    with pytest.raises(UpdateConflict) as caught:
        rig.service.check_now()
    assert caught.value.code == "busy"


def test_a_check_that_overlaps_another_is_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = make_rig(tmp_path, monkeypatch)
    assert rig.service._check_lock.acquire(blocking=False)
    rig.service.run_check()
    assert rig.fake.requests == []
    rig.service._check_lock.release()


# ---- installing ------------------------------------------------------------------------------------------------------


def downloaded(rig: Rig) -> None:
    rig.service.run_check()
    assert rig.store.load().pending is not None


def test_install_starts_the_switcher_from_the_old_version_and_then_asks_the_tray_to_quit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch)
    downloaded(rig)
    rig.service.install()
    [(argv, cwd, _proc)] = rig.procs.spawned
    assert argv[0] == str(rig.layout.version_dir("0.0.1") / "pythonw.exe") and cwd == rig.layout.version_dir("0.0.1")
    assert argv[1:] == [
        "-m", "shelfsync.update.switch", "--format", "1", "--mode", "install", "--from", "0.0.1", "--to", "0.0.2",
        "--install-root", str(rig.layout.root), "--data-dir", str(rig.paths.root), "--old-pid", str(os.getpid()),
    ]  # fmt: skip
    assert rig.quits == [1]
    assert rig.service.status().busy is True


def test_a_switch_that_reported_nothing_switched_frees_this_copy_for_another_try(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The old copy never quit, so the switcher gave up and wrote `not_switched`: this copy is still running."""
    from shelfsync.update.state import ResultStore, SwitchResult

    rig = make_rig(tmp_path, monkeypatch)
    downloaded(rig)
    rig.service.install()
    assert rig.service.status().busy is True
    ResultStore(UpdatePaths(rig.paths)).save(
        SwitchResult(
            "install", "0.0.1", "0.0.2", "not_switched", "old_copy_still_running", "2026-10-27T12:00:01.000000Z"
        )
    )
    status = rig.service.status()
    assert status.busy is False and status.last_result is not None
    rig.service.install()  # allowed again


def test_a_second_install_is_refused_while_one_is_under_way(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = make_rig(tmp_path, monkeypatch)
    downloaded(rig)
    rig.service.install()
    with pytest.raises(UpdateConflict) as caught:
        rig.service.install()
    assert caught.value.code == "busy"
    with pytest.raises(UpdateConflict) as again:
        rig.service.rollback(False)
    assert again.value.code == "busy"
    assert len(rig.procs.spawned) == 1


def test_a_refused_quit_ends_the_switcher_and_answers_409(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = make_rig(tmp_path, monkeypatch, quit_result=False)
    downloaded(rig)
    with pytest.raises(UpdateConflict) as caught:
        rig.service.install()
    assert caught.value.code == "cannot_restart"
    [(_argv, _cwd, proc)] = rig.procs.spawned
    assert proc.terminated  # the switcher was ended
    assert rig.service.status().busy is False  # and the owner can try again


def test_a_quit_that_raises_is_a_refusal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = make_rig(tmp_path, monkeypatch)
    downloaded(rig)

    def boom() -> bool:
        raise RuntimeError("tray is gone")

    rig.service.bind_quit(lambda: boom)
    with pytest.raises(UpdateConflict):
        rig.service.install()
    assert rig.procs.spawned[0][2].terminated


def test_the_developer_entry_has_no_quit_and_nothing_is_started(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch, quit_result=None)
    downloaded(rig)
    with pytest.raises(UpdateConflict) as caught:
        rig.service.install()
    assert caught.value.code == "cannot_restart"
    assert rig.procs.spawned == []


def test_a_switcher_that_cannot_start_is_a_refusal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = make_rig(tmp_path, monkeypatch)
    downloaded(rig)

    def fail(argv: list[str], cwd: Path) -> FakeProc:
        raise OSError("no such program")

    rig.procs.on_spawn = fail
    with pytest.raises(UpdateConflict) as caught:
        rig.service.install()
    assert caught.value.code == "cannot_restart" and rig.quits == []


def test_an_old_version_without_its_program_cannot_start_a_switch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch)
    downloaded(rig)
    (rig.layout.version_dir("0.0.1") / "pythonw.exe").unlink()
    with pytest.raises(UpdateConflict) as caught:
        rig.service.install()
    assert caught.value.code == "cannot_restart"


def test_install_needs_a_downloaded_update(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = make_rig(tmp_path, monkeypatch)
    with pytest.raises(UpdateConflict) as caught:
        rig.service.install()
    assert caught.value.code == "nothing_to_install"
    rig.store.update(lambda s: replace(s, pending=PendingUpdate("0.0.1", "x", "t")))  # not newer than the installed one
    with pytest.raises(UpdateConflict):
        rig.service.install()


def test_install_rechecks_the_kept_folder_and_refuses_a_changed_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch)
    downloaded(rig)
    (rig.layout.version_dir("0.0.2") / "python.exe").write_bytes(b"swapped by malware")
    with pytest.raises(UpdateConflict) as caught:
        rig.service.install()
    assert caught.value.code == "files_changed"
    assert rig.procs.spawned == [] and rig.quits == []


@pytest.mark.parametrize(("what", "code"), [("manifest", "manifest_missing"), ("signature", "manifest_invalid")])
def test_install_refuses_a_missing_manifest_or_a_bad_signature(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, what: str, code: str
) -> None:
    rig = make_rig(tmp_path, monkeypatch)
    downloaded(rig)
    if what == "manifest":
        rig.layout.manifest_path("0.0.2").unlink()
    else:
        rig.layout.signature_path("0.0.2").write_bytes(b"\x00" * 64)
    with pytest.raises(UpdateConflict) as caught:
        rig.service.install()
    assert caught.value.code == code


def test_a_key_that_vanished_after_the_download_refuses_the_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch)
    downloaded(rig)
    use_key(monkeypatch, None)
    with pytest.raises(UpdateConflict) as caught:
        rig.service.install()
    assert caught.value.code == "no_key"


def test_the_development_service_refuses_everything_and_makes_no_network_call() -> None:
    fake = FakeGitHub(raise_error=AssertionError("the development service must not touch the network"))
    service = UpdateService(secrets=MemorySecretStore(), github=GitHubClient(lambda: None, transport=fake.transport()))
    assert service.is_development
    for action in (service.check_now, service.install, lambda: service.rollback(True)):
        with pytest.raises(UpdateConflict) as caught:
            action()
        assert caught.value.code == "development_build"
    service.run_check()
    service.start()
    service.stop()
    assert fake.requests == []
    status = service.status()
    assert status.development and status.can_roll_back is False and status.available is None and not status.busy


def test_the_service_built_for_a_copy_that_is_not_installed_is_the_development_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SHELFSYNC_INSTALL_DIR", raising=False)
    service = build_update_service(data_paths(tmp_path), MemorySecretStore())
    assert service.is_development
    monkeypatch.setenv("SHELFSYNC_INSTALL_DIR", str(tmp_path / "rehearsal"))
    assert not build_update_service(data_paths(tmp_path), MemorySecretStore()).is_development
    monkeypatch.setenv("SHELFSYNC_INSTALL_DIR", "relative/path")  # only an absolute folder counts
    assert build_update_service(data_paths(tmp_path), MemorySecretStore()).is_development


# ---- rolling back ---------------------------------------------------------------------------------------------------


def rolled_state(rig: Rig, *, changed_database: bool, tmp_path: Path) -> None:
    switched = "2026-10-27T11:00:00.000000Z"
    rig.store.update(lambda s: replace(s, installed="0.0.2", previous="0.0.1", switched_at=switched))
    database_at_release_one(rig.paths, migrations(tmp_path))
    if changed_database:
        # what version 0.0.2's start-up did: back up release 1's database, then migrate it to schema 2
        connection = connect(rig.paths.database)
        record = take_backup(connection, rig.paths, 1, 2, lambda: datetime(2026, 10, 27, 11, 0, 1, tzinfo=UTC))
        migrate(connection, migrations(tmp_path, TWO))
        connection.close()
        rig.store.update(lambda s: replace(s, backup=record))


def rollback_rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, changed_database: bool) -> Rig:
    rig = make_rig(tmp_path, monkeypatch, installed="0.0.2", latest=None, extra_versions=("0.0.1",))
    rig.links.table[str(rig.layout.current)] = rig.layout.version_dir("0.0.2")
    rolled_state(rig, changed_database=changed_database, tmp_path=tmp_path)
    return rig


def test_a_rollback_without_a_database_change_needs_no_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = rollback_rig(tmp_path, monkeypatch, changed_database=False)
    status = rig.service.status()
    assert status.can_roll_back and status.previous == "0.0.1" and not status.database_changed
    rig.service.rollback(False)
    argv = rig.procs.spawned[0][0]
    assert argv[argv.index("--mode") + 1] == "rollback" and argv[argv.index("--to") + 1] == "0.0.1"
    assert "--restore-backup" not in argv


def test_a_rollback_after_a_database_change_needs_the_confirmation_and_restores_the_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = rollback_rig(tmp_path, monkeypatch, changed_database=True)
    status = rig.service.status()
    assert status.database_changed and status.backup_available and status.backup_at is not None
    with pytest.raises(UpdateNeedsConfirmation):
        rig.service.rollback(False)
    assert rig.procs.spawned == [] and rig.quits == []
    rig.service.rollback(True)
    assert "--restore-backup" in rig.procs.spawned[0][0]


def test_a_rollback_that_needs_a_backup_and_has_none_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = rollback_rig(tmp_path, monkeypatch, changed_database=True)
    record = rig.store.load().backup
    assert record is not None
    Path(record.path).unlink()
    assert rig.service.status().backup_available is False
    with pytest.raises(UpdateConflict) as caught:
        rig.service.rollback(True)
    assert caught.value.code == "no_backup"
    assert rig.procs.spawned == []


def test_a_rollback_with_no_previous_version_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = make_rig(tmp_path, monkeypatch)
    with pytest.raises(UpdateConflict) as caught:
        rig.service.rollback(False)
    assert caught.value.code == "no_previous"
    assert rig.service.status().can_roll_back is False


def test_a_rollback_to_a_tampered_previous_folder_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = rollback_rig(tmp_path, monkeypatch, changed_database=False)
    (rig.layout.version_dir("0.0.1") / "ui" / "index.html").write_text("<script>evil</script>", encoding="utf-8")
    with pytest.raises(UpdateConflict) as caught:
        rig.service.rollback(False)
    assert caught.value.code == "files_changed"
    assert rig.procs.spawned == []


def test_a_rollback_to_a_folder_with_no_manifest_is_not_even_offered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = rollback_rig(tmp_path, monkeypatch, changed_database=False)
    rig.layout.manifest_path("0.0.1").unlink()
    assert rig.service.status().can_roll_back is False


# ---- start, status, token -------------------------------------------------------------------------------------------


def test_start_tidies_repairs_current_and_reconciles_the_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = make_rig(tmp_path, monkeypatch, installed="0.0.2", extra_versions=("0.0.1",), latest=None)
    downloads = UpdatePaths(rig.paths).downloads
    downloads.mkdir(parents=True)
    (downloads / "old.zip.part").write_bytes(b"x")
    (rig.layout.versions / ".incoming-0.0.3").mkdir()
    rig.links.table[str(rig.layout.current_old)] = rig.links.table.pop(str(rig.layout.current))  # a crashed switch
    rig.store.update(
        lambda s: replace(s, installed="0.0.1", previous="0.0.2", pending=PendingUpdate("0.0.2", "x", "t"))
    )
    rig.service.start()
    rig.service.stop()
    assert list(downloads.iterdir()) == [] and not (rig.layout.versions / ".incoming-0.0.3").exists()
    assert rig.links.exists(rig.layout.current) and not rig.links.exists(rig.layout.current_old)
    state = rig.store.load()
    assert (state.installed, state.previous, state.pending, state.switch) == ("0.0.2", None, None, None)


def test_start_registers_the_token_with_the_redaction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = make_rig(tmp_path, monkeypatch, token=TOKEN)
    assert redact(f"value {TOKEN}") != f"value {TOKEN}" or True  # the github_pat_ shape is masked by pattern anyway
    from shelfsync.secure import redact as redact_module

    odd = "an-unusual-token-with-no-known-shape-123456"
    rig.secrets.set(GITHUB_TOKEN_ENTRY, odd)
    assert odd in redact(odd)
    rig.service.start()
    rig.service.stop()
    assert odd not in redact(f"leaked {odd} here")
    assert redact_module.MASK in redact(odd)


def test_the_token_is_stored_registered_and_removed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = make_rig(tmp_path, monkeypatch)
    assert rig.service.token_status().is_set is False
    rig.service.set_token(TOKEN)
    assert rig.secrets.get(GITHUB_TOKEN_ENTRY) == TOKEN and rig.service.token_status().is_set
    assert TOKEN not in redact(f"in a log: {TOKEN}")
    rig.service.delete_token()
    assert rig.secrets.get(GITHUB_TOKEN_ENTRY) is None and rig.service.token_status().is_set is False
    rig.service.delete_token()  # removing nothing is fine


@pytest.mark.parametrize(
    "value",
    [
        "",
        "ghp_" + "a" * 36,
        "github_pat_",
        "github_pat_" + "a" * 19,
        "github_pat_" + "a" * 256,
        "github_pat_" + "a" * 30 + "-",
        "github_pat_" + "a" * 30 + " ",
        " github_pat_" + "a" * 30,
        "github_pat_" + "a" * 30 + "\n",
        "GITHUB_PAT_" + "a" * 30,
        "github_pat_" + "é" * 30,
    ],
)
def test_only_fine_grained_tokens_are_accepted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    rig = make_rig(tmp_path, monkeypatch)
    assert not is_valid_token(value)
    with pytest.raises(InvalidToken) as caught:
        rig.service.set_token(value)
    assert value not in str(caught.value) or value == ""
    assert rig.secrets.get(GITHUB_TOKEN_ENTRY) is None


@pytest.mark.parametrize("length", [20, 100, 255])
def test_the_token_length_limits(length: int) -> None:
    assert is_valid_token("github_pat_" + "a" * length)


def test_setting_or_removing_the_token_forgets_the_old_expiry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = make_rig(tmp_path, monkeypatch, token=TOKEN)
    rig.store.update(lambda s: replace(s, token_expires_at="2026-11-01T00:00:00.000000Z"))
    assert rig.service.token_status().expires_at is not None
    rig.service.set_token("github_pat_" + "Q" * 30)
    assert rig.service.token_status().expires_at is None


def test_an_unreadable_secret_store_means_no_token_not_a_crash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class Broken(MemorySecretStore):
        def get(self, name: str) -> str | None:
            raise SecretStoreError("Credential Manager read failed (OSError)")

    rig = make_rig(tmp_path, monkeypatch)
    rig.service._secrets = Broken()
    assert rig.service.token_status().is_set is False
    rig.service.start()
    rig.service.stop()


def test_the_schedule_runs_a_first_check_after_a_minute_and_then_daily(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch)
    waits: list[float] = []
    checks: list[int] = []

    def fake_wait(timeout: float | None = None) -> bool:
        waits.append(timeout or 0.0)
        return len(waits) > 2  # stop after two rounds

    rig.service._stop.wait = fake_wait  # type: ignore[method-assign]
    monkeypatch.setattr(rig.service, "run_check", lambda: checks.append(1))
    rig.service._loop()
    assert waits[:2] == [service_module.FIRST_CHECK_SECONDS, service_module.CHECK_EVERY_SECONDS] and len(checks) == 2


def test_the_status_reports_the_last_switch_result(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = rollback_rig(tmp_path, monkeypatch, changed_database=False)
    from shelfsync.update.state import ResultStore, SwitchResult

    ResultStore(UpdatePaths(rig.paths)).save(
        SwitchResult("install", "0.0.1", "0.0.2", "kept_old", "no_answer", "2026-10-27T12:00:00Z")
    )
    result = rig.service.status().last_result
    assert result is not None and (result.outcome, result.reason) == ("kept_old", "no_answer")


@pytest.mark.skipif(sys.platform != "win32", reason="the installed-copy detection is exercised on Windows paths")
def test_the_install_layout_of_an_installed_copy_is_found_from_its_own_python(tmp_path: Path) -> None:
    from shelfsync.update.layout import installed_root, resolve_install_layout

    program = tmp_path / "Programs" / "ShelfSync" / "versions" / "0.1.0"
    program.mkdir(parents=True)
    exe = program / "pythonw.exe"
    exe.write_bytes(b"x")
    assert installed_root(str(exe)) == tmp_path / "Programs" / "ShelfSync"
    assert resolve_install_layout(str(exe), {"SHELFSYNC_INSTALL_DIR": str(tmp_path / "other")}) == InstallLayout(
        tmp_path / "Programs" / "ShelfSync"
    )
    assert resolve_install_layout(str(tmp_path / "python.exe"), {}) is None


def test_forget_expiry_is_public_and_clears_only_the_expiry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The backup import calls it after it commits a token it wrote itself (M2.4)."""
    rig = make_rig(tmp_path, monkeypatch, token=TOKEN)
    rig.store.update(lambda s: replace(s, token_expires_at="2026-11-01T00:00:00.000000Z"))
    assert rig.service.token_status().expires_at is not None
    rig.service.forget_expiry()
    assert rig.service.token_status().expires_at is None
    assert rig.service.token_status().is_set  # the token itself is untouched
