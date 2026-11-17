"""CAT-01, CAT-02, CAT-03, CAT-05, APL-12, ERR-02: `python -m shelfsync.catalog.report`, L1's dry read, against fakes
only (never the live stores): it opens the database read-only and never migrates, asks before any request, keeps the
spacing at 1,000 ms or more, saves nothing, and prints counts only (no host, key, slug, title or file name)."""

import hashlib
import io
import logging
import os
import shutil
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from typing import Any

import httpx
import pytest

from shelfsync.catalog import report
from shelfsync.db.connection import connect
from shelfsync.db.migrate import DEFAULT_MIGRATIONS_DIR, applied_versions, migrate
from shelfsync.db.stores import insert_store
from shelfsync.logs import QUIET_LOGGERS
from shelfsync.paths import DataPaths
from shelfsync.platform.secrets import MemorySecretStore
from shelfsync.secure.credentials import StoreCredentials
from shelfsync.tray.instance import CombinedInstanceLock, FakeInstanceLock
from tests.catalog_support import NEAR_MISS_PAIRS, FakeCatalogStore, FakeTime, Sites, raw_product
from tests.report_harness import MARK
from tests.store_support import KEY, SECRET, FailingSecretStore

REPO = Path(__file__).resolve().parents[1]
AT = "2026-11-17T12:00:00.000000Z"


def make_database(paths: DataPaths, migrations: Path = DEFAULT_MIGRATIONS_DIR, paused: bool = True) -> None:
    paths.root.mkdir(parents=True, exist_ok=True)
    with closing(connect(paths.database)) as connection:
        migrate(connection, migrations)
        for code in ("GF", "PW"):
            insert_store(
                connection,
                name=f"Store {code}",
                url=f"https://store-{code.lower()}.example",
                code=code,
                shape="circle",
                color="indigo",
                spacing_ms=150,
                main_button="Download",
                created_at=AT,
            )
        if paused:
            insert_store(
                connection,
                name="Store TS",
                url="https://store-ts.example",
                code="TS",
                shape="circle",
                color="teal",
                spacing_ms=150,
                main_button="Download",
                created_at=AT,
            )
            connection.execute("UPDATE store SET state = 'paused' WHERE code = 'TS'")


def snapshot(folder: Path) -> dict[str, str]:
    """Every file under the data folder with its SHA-256: a dry read must leave all of it as it was."""
    return {
        str(path.relative_to(folder)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(folder.rglob("*"))
        if path.is_file()
    }


def run_harness(paths: DataPaths, *arguments: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "SHELFSYNC_DATA_DIR": str(paths.root), "PYTHONPATH": os.pathsep.join(["backend", "."])}
    return subprocess.run(  # the test's own interpreter and module, fixed arguments
        [sys.executable, "-B", "-m", "tests.report_harness", *arguments],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )


# ---- in a fresh process: the whole command -------------------------------------------------------------------------


def test_the_dry_read_prints_counts_only_and_changes_nothing(data_paths: DataPaths) -> None:
    make_database(data_paths)
    before = snapshot(data_paths.root)
    done = run_harness(data_paths, "--yes")
    assert done.returncode == 0, done.stderr
    output = done.stdout + done.stderr
    assert snapshot(data_paths.root) == before  # no database write, no file, no log file
    assert not data_paths.logs.exists()
    for forbidden in (
        MARK,
        "store-gf.example",
        "store-pw.example",
        KEY,
        SECRET,
        KEY[3:],
        "amazon_s3",
        *(slug for pair in NEAR_MISS_PAIRS for slug in pair[:2]),
        "stale-thing",
    ):
        assert forbidden not in output, forbidden
    out = done.stdout
    assert "Store TS: skipped (paused in Settings)" in out
    assert "  GET /wp-json/wc/v3/system_status?_fields=environment" in out
    assert "Store GF, at least 1,000 ms between requests:" in out
    assert "Store GF: WooCommerce 11.2.1" in out
    assert "  rows read 6, X-WP-Total 6" in out
    assert "  statuses: draft 1, publish 5" in out and "  types: simple 6" in out
    assert "  products with 0 downloads 0, 1 download 5, 2 or more 1" in out
    assert "  titles with HTML entities 1" in out
    assert "  meta latest_version 1; latest_version_<x> matching a file stem 1, matching none 1" in out
    assert "  slugs outside the canonical pattern 1, of them empty 1 and trashed 0" in out
    assert "  main download named like the store's main button 6; found by the one-download rule 0" in out
    assert "found by the one-download rule 1" in out  # PW's "Get it" with one download and main button Download
    assert "  slugs on every store 1, on one store only 7" in out  # GF 4 (the draft has none), PW 3
    assert "  near-miss pairs 3; the three of 01-A section 2: pair 1 yes, pair 2 yes, pair 3 yes" in out
    assert "  items that would have two present products on one store 0" in out
    # the read's own log lines reach the console (stderr), one per store
    assert "Store GF catalog read: ok" in done.stderr and "Store PW catalog read: ok" in done.stderr


def test_an_installed_app_still_at_schema_2_is_read_and_never_migrated(data_paths: DataPaths, tmp_path: Path) -> None:
    old = tmp_path / "schema2"
    old.mkdir()
    for name in ("0001_base.sql", "0002_store.sql"):
        shutil.copy(DEFAULT_MIGRATIONS_DIR / name, old / name)
    make_database(data_paths, old, paused=False)
    before = snapshot(data_paths.root)
    done = run_harness(data_paths, "--yes", "--store", "GF")
    assert done.returncode == 0, done.stderr
    assert "Store GF: WooCommerce 11.2.1" in done.stdout and "Store PW" not in done.stdout
    assert snapshot(data_paths.root) == before
    with closing(sqlite3.connect(data_paths.database)) as connection:
        assert applied_versions(connection) == {1, 2}


# ---- in process: the parts -----------------------------------------------------------------------------------------


def in_process(
    paths: DataPaths, *argv: str, stores: dict[str, FakeCatalogStore] | None = None, **options: Any
) -> tuple[int, str, str, Sites]:
    sites = Sites(
        stores
        if stores is not None
        else {"GF": FakeCatalogStore(rows=[raw_product(1)]), "PW": FakeCatalogStore(rows=[raw_product(2)])}
    )
    secrets = MemorySecretStore()
    with closing(sqlite3.connect(paths.database)) as connection:
        for (store_id,) in connection.execute("SELECT id FROM store WHERE code IN ('GF', 'PW')"):
            StoreCredentials(secrets).save(store_id, KEY, SECRET)
    clock = FakeTime()
    out, err = io.StringIO(), io.StringIO()
    code = report.main(
        list(argv),
        secrets_factory=lambda: options.get("secrets", secrets),
        transport_factory=lambda store: httpx.MockTransport(sites),
        confirm=options.get("confirm", lambda prompt: ""),
        out=out,
        err=err,
        make_stop=lambda: clock,
        monotonic=clock.monotonic,
        now=clock.wall,
        instance_lock=options.get("lock", lambda paths: FakeInstanceLock()),
    )
    return code, out.getvalue(), err.getvalue(), sites


@pytest.mark.parametrize("value", ["999", "150", "0", "-5", "fast"])
def test_a_spacing_below_one_second_is_a_usage_error(value: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        report.parse_args(["--spacing-ms", value])
    assert exit_info.value.code == 2
    assert report.parse_args(["--spacing-ms", "1500"]).spacing_ms == 1500


def test_nothing_is_sent_before_the_owner_presses_enter(data_paths: DataPaths) -> None:
    make_database(data_paths)

    def refuse(prompt: str) -> str:
        raise KeyboardInterrupt

    code, out, err, sites = in_process(data_paths, confirm=refuse)
    assert (code, sites.requests) == (1, [])
    assert "GET /wp-json/wc/v3/products?downloadable=true" in out and "Stopped. Nothing was saved." in err


def test_a_larger_spacing_and_one_store(data_paths: DataPaths) -> None:
    make_database(data_paths)
    code, out, _, sites = in_process(data_paths, "--yes", "--store", "PW", "--spacing-ms", "2500")
    assert code == 0 and {request.url.host for request in sites.requests} == {"store-pw.example"}
    assert "Store PW, at least 2,500 ms between requests:" in out
    assert "Across stores: needs two stores read without a failure." in out


def test_an_unknown_store_code_is_a_usage_error(data_paths: DataPaths) -> None:
    make_database(data_paths)
    code, _, err, sites = in_process(data_paths, "--yes", "--store", "ZZ")
    assert (code, sites.requests) == (2, []) and "No live store has the code 'ZZ'." in err


def test_a_failed_store_names_its_reason_field_and_page_and_the_exit_code_is_one(data_paths: DataPaths) -> None:
    make_database(data_paths)
    bad = FakeCatalogStore(rows=[raw_product(1, "a\x00b")])
    code, out, _, _ = in_process(data_paths, "--yes", stores={"GF": bad, "PW": FakeCatalogStore(rows=[raw_product(2)])})
    assert code == 1
    assert "Store GF: FAILED, bad_response; field slug on page 1" in out
    assert "Store PW: WooCommerce 11.2.1" in out


def test_a_store_without_keys_is_reported_and_the_others_still_read(data_paths: DataPaths) -> None:
    make_database(data_paths)
    secrets = MemorySecretStore()
    code, out, _, sites = in_process(data_paths, "--yes", secrets=secrets)
    assert code == 1 and sites.requests == []
    assert "Store GF: FAILED, keys_missing" in out and "Store PW: FAILED, keys_missing" in out


def test_while_shelfsync_runs_nothing_is_read_and_the_owner_is_told_to_quit_it(data_paths: DataPaths) -> None:
    """Review 1, finding 5: the app's instance lock is taken (ShelfSync runs): refused before the database is opened,
    with the plain way to quit it."""
    make_database(data_paths)
    before = snapshot(data_paths.root)
    taken = {"ShelfSync"}
    code, out, err, sites = in_process(data_paths, "--yes", lock=lambda paths: FakeInstanceLock(taken))
    assert (code, out, sites.requests) == (1, "", [])
    assert "ShelfSync is running. Quit it first" in err
    assert snapshot(data_paths.root) == before


def test_the_lock_is_held_for_the_whole_read_and_given_back(data_paths: DataPaths) -> None:
    make_database(data_paths)
    taken: set[str] = set()
    seen: list[set[str]] = []
    stores = {"GF": FakeCatalogStore(rows=[raw_product(1)]), "PW": FakeCatalogStore(rows=[raw_product(2)])}
    stores["GF"].before_page = lambda page: seen.append(set(taken))
    code, _, _, _ = in_process(data_paths, "--yes", stores=stores, lock=lambda paths: FakeInstanceLock(taken))
    assert code == 0 and seen == [{"ShelfSync"}] and taken == set()


def test_a_wal_file_left_by_a_shelfsync_that_did_not_close_cleanly_is_refused(data_paths: DataPaths) -> None:
    """`immutable=1` would read past the WAL's commits, so a `-wal` file with nothing running is refused."""
    make_database(data_paths)
    with closing(connect(data_paths.database)) as app:
        app.execute("PRAGMA wal_autocheckpoint = 0")
        app.execute("UPDATE store SET name = 'Renamed' WHERE code = 'GF'")
        main_file = hashlib.sha256(data_paths.database.read_bytes()).hexdigest()
        code, _, err, sites = in_process(data_paths, "--yes")
        assert (code, sites.requests) == (1, [])
        assert "didn't close cleanly" in err
        assert hashlib.sha256(data_paths.database.read_bytes()).hexdigest() == main_file


def test_a_credential_manager_failure_stops_the_command_and_is_not_keys_missing(data_paths: DataPaths) -> None:
    """Review 1, finding 3."""
    make_database(data_paths)
    failing = FailingSecretStore()
    failing.fail_get = True
    code, out, err, sites = in_process(data_paths, "--yes", secrets=failing)
    assert (code, sites.requests) == (1, [])
    assert "keys_missing" not in out and "Credential Manager couldn't be read" in err


def test_the_request_list_shown_is_what_is_sent(data_paths: DataPaths) -> None:
    """Review 1, finding 7: the list is built from the reader's own parameters (`page` shown as `1..N`)."""
    make_database(data_paths)
    code, out, _, sites = in_process(data_paths, "--yes", "--store", "GF")
    shown = [line.strip().removeprefix("GET ") for line in out.splitlines() if line.strip().startswith("GET ")]
    sent = [request for request in sites.requests if request.url.host == "store-gf.example"]
    assert code == 0 and len(shown) == 2 and len(sent) == 2

    def parts(text: str) -> tuple[str, dict[str, str]]:
        path, _, query = text.partition("?")
        return path, dict(pair.split("=", 1) for pair in query.split("&"))

    assert parts(shown[0]) == (sent[0].url.path, dict(sent[0].url.params))
    path, params = parts(shown[1])
    assert path == sent[1].url.path and params == {**dict(sent[1].url.params), "page": "1..N"}


def test_the_apps_own_instance_lock_is_used_and_no_lock_file_is_made(
    data_paths: DataPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The lock a second launch meets (`tray/instance.py`): the per-user mutex, plus `instance.lock` only when that
    file exists. The Windows classes are faked here (the owner's own ShelfSync may hold the real mutex)."""
    made: list[str] = []

    def mutex() -> FakeInstanceLock:
        made.append("mutex")
        return FakeInstanceLock(name="m")

    def file_lock(path: Path) -> FakeInstanceLock:
        made.append("file")
        return FakeInstanceLock(name="f")

    monkeypatch.setattr(report, "WindowsInstanceLock", mutex)
    monkeypatch.setattr(report, "WindowsFileLock", file_lock)
    data_paths.root.mkdir(parents=True)
    assert isinstance(report.app_instance_lock(data_paths), FakeInstanceLock) and made == ["mutex"]
    assert not data_paths.instance_lock.exists()
    data_paths.instance_lock.write_bytes(b"")
    made.clear()
    assert isinstance(report.app_instance_lock(data_paths), CombinedInstanceLock) and made == ["mutex", "file"]


def test_no_database_is_a_clear_message(data_paths: DataPaths) -> None:
    code, _, err, _ = in_process_without_database(data_paths)
    assert code == 1 and "isn't in the data folder" in err
    assert not data_paths.root.exists()  # nothing was made


def in_process_without_database(paths: DataPaths) -> tuple[int, str, str, None]:
    out, err = io.StringIO(), io.StringIO()
    code = report.main(
        ["--yes"],
        secrets_factory=MemorySecretStore,
        out=out,
        err=err,
        instance_lock=lambda paths: FakeInstanceLock(),
    )
    return code, out.getvalue(), err.getvalue(), None


def test_the_command_holds_the_http_loggers_at_the_apps_quiet_levels_and_leaves_no_handler(
    data_paths: DataPaths,
) -> None:
    make_database(data_paths)
    for name in QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.DEBUG)
    handlers = list(logging.getLogger().handlers)
    in_process(data_paths, "--yes")
    assert {name: logging.getLogger(name).level for name in QUIET_LOGGERS} == QUIET_LOGGERS
    assert logging.getLogger().handlers == handlers
