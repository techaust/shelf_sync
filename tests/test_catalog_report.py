"""CAT-01, CAT-02, CAT-03, CAT-05, APL-12, ERR-02: `python -m shelfsync.catalog.report`, L1's dry read, against fakes
only (never the live stores): it opens the database read-only and never migrates, asks before any request, keeps the
spacing at 1,000 ms or more, saves nothing, and prints counts only (no host, key, slug, title or file name)."""

import base64
import hashlib
import io
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from collections.abc import Iterator
from contextlib import closing
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from shelfsync.apply import catalog_read
from shelfsync.apply.catalog_read import Attempt, CatalogRead, FactsTransport, ResponseFacts, Wire
from shelfsync.apply.woocommerce import WooClient
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
from tests.store_support import KEY, SECRET, STORE_URL, FailingSecretStore

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
    clock = options.get("clock") or FakeTime()
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


# ---- the diagnostics (t9) -------------------------------------------------------------------------------------------

TRACE_LINE = re.compile(r"\d{2}:\d{2}:\d{2} (GF|PW) #\d+ ")


def test_the_trace_and_summary_in_a_fresh_process_hold_no_host_key_cookie_query_slug_title_or_file_name(
    data_paths: DataPaths,
) -> None:
    """Item 4 (t9): with `--trace` and every option, the output holds fixed words and numbers only, though the
    answers carry cookie values, a `cf-ray`, a server text and the marker, and the trace events' `info` holds the
    request, an address with the keys in its query, and the `Authorization` header."""
    make_database(data_paths)
    before = snapshot(data_paths.root)
    done = run_harness(data_paths, "--yes", "--trace", "--no-meta", "--per-page", "50", "--read-seconds", "90")
    assert done.returncode == 0, done.stderr
    output = done.stdout + done.stderr
    assert snapshot(data_paths.root) == before
    authorization = "Basic " + base64.b64encode(f"{KEY}:{SECRET}".encode()).decode()
    for forbidden in (
        MARK,
        "store-gf.example",
        "store-pw.example",
        KEY,
        SECRET,
        KEY[3:],
        authorization,
        authorization[6:],
        "consumer_key",
        "consumer_secret",
        "Authorization",
        "LHR",
        "cookie-value",
        "amazon_s3",
        *(slug for pair in NEAR_MISS_PAIRS for slug in pair[:2]),
    ):
        assert forbidden not in output, forbidden
    traces = [line for line in done.stdout.splitlines() if TRACE_LINE.match(line)]
    assert len(traces) == 4  # each store: system_status and its one page of 50
    for line in traces:
        assert not set("?=/@&") & set(line), line  # no address, query or header text
    assert re.fullmatch(
        r"\d{2}:\d{2}:\d{2} GF #2 products page 1 try 1: ok HTTP 200 \(stage done\); new connection, headers 0 ms, "
        r"first byte 0 ms, longest gap 0 ms, [\d,]+ of [\d,]+ bytes, took 0\.0 s, waited 1,000 ms; server other, "
        r"cf-ray yes, cf-cache other, content none, cf-mitigated no, retry-after no, hints x-cache, cookies __cf_bm "
        r"wordpress_logged_in, other cookies 1",
        traces[1],
    ), traces[1]
    out = done.stdout
    assert re.search(
        r"Settings: 50 products a page, at most 80 pages; fields id,slug,name,type,status,date_modified_gmt,downloads; "
        r"at most 1,200 s for each store's read and 120 s for one request, each plus up to the read timeout after the "
        r"last byte; read timeout 90 s; times are local, [^;]+; one line per request \(--trace\)",
        out,
    )
    assert "  meta not asked (--no-meta)" in out and "meta latest_version" not in out
    assert "Timing, store GF: read ok; requests 2, median 0.0 s, slowest 0.0 s; largest page " in out
    assert "  timeouts 0: after the headers 0, before them or not known 0; first stall at request none" in out
    assert "  timeouts by stage: none; by what ended them: none" in out and "  by error: none" in out


@pytest.mark.parametrize(
    "options", [[], ["--no-meta"], ["--per-page", "25"], ["--per-page", "50", "--no-meta"]], ids=str
)
def test_the_request_list_shown_is_what_is_sent_with_every_option(data_paths: DataPaths, options: list[str]) -> None:
    """Item 3: `--no-meta` and `--per-page` change the list shown and the requests sent identically."""
    make_database(data_paths)
    code, out, _, sites = in_process(data_paths, "--yes", "--store", "GF", *options)
    shown = [line.strip().removeprefix("GET ") for line in out.splitlines() if line.strip().startswith("GET ")]
    sent = [request for request in sites.requests if request.url.host == "store-gf.example"]
    assert code == 0 and len(shown) == 2 and len(sent) == 2
    path, _, query = shown[1].partition("?")
    params = dict(pair.split("=", 1) for pair in query.split("&"))
    assert path == sent[1].url.path and params == {**dict(sent[1].url.params), "page": "1..N"}
    per_page = options[options.index("--per-page") + 1] if "--per-page" in options else "100"
    assert params["per_page"] == per_page
    assert params["_fields"].endswith(",downloads") == ("--no-meta" in options)


@pytest.mark.parametrize(
    ("options", "store_seconds", "max_pages", "per_page", "meta", "read"),
    [
        ([], 600.0, 40, 100, True, 30.0),
        (["--per-page", "50"], 1200.0, 80, 50, True, 30.0),
        (["--per-page", "25", "--no-meta", "--read-seconds", "90"], 2400.0, 160, 25, False, 90.0),
    ],
    ids=["defaults", "50", "25 no meta 90 s"],
)
def test_each_store_is_read_with_the_runs_settings(
    data_paths: DataPaths,
    monkeypatch: pytest.MonkeyPatch,
    options: list[str],
    store_seconds: float,
    max_pages: int,
    per_page: int,
    meta: bool,
    read: float,
) -> None:
    """The lead's decisions: the store's time limit scales to 600 s x 100 / per page, the most pages to the 4,000-row
    cap; every attempt is bounded at 120 s; the read timeout is `--read-seconds`; the reader gets the facts transport
    and an observer."""
    make_database(data_paths)
    calls: list[dict[str, Any]] = []
    real = catalog_read.read_store_catalog

    def spy(client: WooClient, code: str, **settings: Any) -> CatalogRead:
        calls.append(settings)
        return real(client, code, **settings)

    monkeypatch.setattr(report, "read_store_catalog", spy)
    code, _, _, sites = in_process(data_paths, "--yes", "--store", "GF", *options)
    assert code == 0 and len(calls) == 1
    used = calls[0]
    assert (used["store_seconds"], used["max_pages"], used["per_page"], used["meta"]) == (
        store_seconds,
        max_pages,
        per_page,
        meta,
    )
    assert used["attempt_seconds"] == report.ATTEMPT_SECONDS == 120.0 and isinstance(used["facts"], FactsTransport)
    assert callable(used["observe"])
    assert {request.extensions["timeout"]["read"] for request in sites.requests} == {read}


@pytest.mark.parametrize("value", ["30", "0", "200", "lots"])
def test_per_page_is_only_25_50_or_100(value: str) -> None:
    with pytest.raises(SystemExit) as exit_info:
        report.parse_args(["--per-page", value])
    assert exit_info.value.code == 2
    assert [report.parse_args(["--per-page", n]).per_page for n in ("25", "50", "100")] == [25, 50, 100]
    assert report.parse_args([]).per_page == 100


@pytest.mark.parametrize("value", ["29", "121", "0", "ninety", "45.5"])
def test_the_read_timeout_is_30_to_120_seconds(value: str) -> None:
    with pytest.raises(SystemExit) as exit_info:
        report.parse_args(["--read-seconds", value])
    assert exit_info.value.code == 2
    assert [report.parse_args(["--read-seconds", n]).read_seconds for n in ("30", "90", "120")] == [30, 90, 120]
    assert report.parse_args([]).read_seconds == 30


def test_trace_prints_a_line_per_attempt_as_it_ends_with_its_request_number(data_paths: DataPaths) -> None:
    make_database(data_paths)
    gf = FakeCatalogStore(rows=[raw_product(1)], answers=[httpx.Response(429, headers={"Retry-After": "3"})])
    stores = {"GF": gf, "PW": FakeCatalogStore(rows=[raw_product(2)])}
    code, out, _, _ = in_process(data_paths, "--yes", "--trace", "--store", "GF", stores=stores)
    traces = [line for line in out.splitlines() if TRACE_LINE.match(line)]
    assert code == 0 and len(traces) == 3
    assert [line[9:].split(";")[0] for line in traces] == [
        "GF #1 system_status try 1: ok HTTP 200 (stage unknown)",
        "GF #2 products page 1 try 1: rate_limited HTTP 429 (stage unknown)",
        "GF #3 products page 1 try 2: ok HTTP 200 (stage unknown)",
    ]
    assert "connection unknown" in traces[0] and "waited 3,000 ms" in traces[2] and "retry-after yes" in traces[1]
    assert out.index(traces[-1]) < out.index("Store GF: WooCommerce")  # printed as the read goes
    assert "Timing, store GF: read ok; requests 3," in out


def test_without_trace_no_attempt_line_is_printed_but_the_summary_is(data_paths: DataPaths) -> None:
    make_database(data_paths)
    code, out, _, _ = in_process(data_paths, "--yes")
    assert code == 0 and not [line for line in out.splitlines() if TRACE_LINE.match(line)]
    assert "Timing, store GF: read ok; requests 2" in out and "Timing, store PW: read ok; requests 2" in out


def test_a_store_without_keys_has_no_timing_line(data_paths: DataPaths) -> None:
    make_database(data_paths)
    code, out, _, _ = in_process(data_paths, "--yes", secrets=MemorySecretStore())
    assert code == 1 and "Timing, store" not in out


def _attempt(**changes: Any) -> Attempt:
    base = Attempt(
        page=13,
        attempt=1,
        outcome="timeout",
        http_status=200,
        elapsed_ms=30_960,
        body_bytes=118_400,
        headers=True,
        wire=Wire(
            facts=ResponseFacts(True, "cloudflare", "dynamic", ("__cf_bm",), 2, "json", False, True, ("x-cache",)),
            stage="body",
            new_connection=False,
            headers_ms=840,
            first_byte_ms=900,
            longest_gap_ms=30_000,
            received=118_400,
            declared_bytes=250_000,
            error="read_timeout",
        ),
        waited_ms=1_000,
        ended="read_timeout",
    )
    return replace(base, **changes)


def test_one_trace_line_holds_fixed_words_and_numbers_only() -> None:
    local = datetime(2026, 11, 18, 9, 5, 7)
    assert report.trace_line("PW", 13, _attempt(), local) == (
        "09:05:07 PW #13 products page 13 try 1: timeout HTTP 200 (ended read_timeout, stage body, error "
        "read_timeout); connection reused, headers 840 ms, first byte 900 ms, longest gap 30,000 ms, "
        "118,400 of 250,000 bytes, took 31.0 s, waited 1,000 ms; server cloudflare, cf-ray yes, cf-cache dynamic, "
        "content json, cf-mitigated no, retry-after yes, hints x-cache, cookies __cf_bm, other cookies 2"
    )
    nothing = _attempt(
        page=None, outcome="unreachable", http_status=None, body_bytes=None, headers=None, wire=None, ended=None,
        waited_ms=0,
    )  # fmt: skip
    assert (nothing.what, nothing.facts) == ("system_status", None)  # both follow from `page` and `wire`
    assert report.trace_line("GF", 1, nothing, local) == (
        "09:05:07 GF #1 system_status try 1: unreachable (stage unknown); connection unknown, headers none, "
        "first byte none, longest gap none, bytes unknown, took 31.0 s, waited 0 ms; no answer"
    )
    wire = _attempt().wire
    assert wire is not None
    chunked = _attempt(wire=replace(wire, new_connection=True, declared_bytes=None))
    assert "new connection," in report.trace_line("GF", 2, chunked, local)
    assert "118,400 bytes, no length given" in report.trace_line("GF", 2, chunked, local)


def test_the_timing_summary_counts_timeouts_by_stage_by_what_ended_them_and_by_error() -> None:
    wire = _attempt().wire
    assert wire is not None
    clean = replace(wire, error=None)
    attempts = [
        _attempt(outcome="ok", elapsed_ms=400, ended=None, headers=True, wire=clean),
        _attempt(outcome="ok", elapsed_ms=600, ended=None, headers=True, body_bytes=250_000, wire=clean),
        _attempt(),  # a read timeout during the body, 30,960 ms
        _attempt(elapsed_ms=120_000, ended="attempt_bound", headers=True, wire=clean),  # WooClient's own check
        _attempt(
            elapsed_ms=10_000,
            ended="connect_timeout",
            headers=False,
            wire=Wire(stage="connect", error="connect_timeout"),
        ),
        _attempt(outcome="rate_limited", elapsed_ms=200, ended=None, body_bytes=900_000, wire=clean),  # not a page
        _attempt(outcome="unreachable", elapsed_ms=1_500, ended=None, wire=Wire(stage="body", error="read_error")),
    ]
    assert report.timing_lines("PW", attempts, CatalogRead("server_error")) == [
        "Timing, store PW: read server_error; requests 7, median 1.5 s, slowest 120.0 s; largest page 250,000 bytes",
        "  timeouts 3: after the headers 2, before them or not known 1; first stall at request 3",
        "  timeouts by stage: body 2, connect 1; by what ended them: attempt_bound 1, connect_timeout 1, "
        "read_timeout 1",
        "  by error: connect_timeout 1, read_error 1, read_timeout 1",
    ]
    assert report.timing_lines("GF", [], CatalogRead("stopped")) == ["Timing, store GF: read stopped; no requests sent"]
    connect = report.trace_line("PW", 5, attempts[4], datetime(2026, 11, 18, 9, 5, 7))
    assert "timeout HTTP 200 (ended connect_timeout, stage connect, error connect_timeout);" in connect


class _Interrupting(httpx.SyncByteStream):
    """A body that sends a little, then the owner presses Ctrl+C while it trickles."""

    def __init__(self, time: FakeTime) -> None:
        self.time = time

    def __iter__(self) -> Iterator[bytes]:
        self.time.now += 0.5
        yield b"[" * 300
        self.time.now += 4.0
        yield b" " * 20
        self.time.now += 6.0
        raise KeyboardInterrupt


def test_ctrl_c_inside_a_body_prints_the_request_in_flight(data_paths: DataPaths) -> None:
    """Review 2, finding 3: the attempt Ctrl+C interrupted gets one line (stage, bytes, longest gap, how long so far)
    before the store's partial summary."""
    make_database(data_paths)
    gf = FakeCatalogStore(rows=[raw_product(1)])
    gf.answers = [
        lambda request: httpx.Response(200, headers={"Content-Length": "9000"}, stream=_Interrupting(gf.time))
    ]
    stores = {"GF": gf, "PW": FakeCatalogStore(rows=[raw_product(2)])}
    code, out, err, _ = in_process(data_paths, "--yes", "--store", "GF", stores=stores, clock=gf.time)
    assert code == 1 and "Stopped. Nothing was saved." in err
    lines = out.splitlines()
    flight = lines.index(
        "GF #2 in flight when stopped: stage unknown, 320 of 9,000 bytes, longest gap 4,000 ms, 10.5 s so far"
    )
    assert lines[flight + 1].startswith("Timing, store GF: read stopped by Ctrl+C; requests 1,")


@pytest.mark.parametrize(
    ("last", "result", "words"),
    [
        (_attempt(outcome="ok", ended=None), CatalogRead(None), "ok"),
        (_attempt(outcome="ok", ended=None), CatalogRead("count_mismatch"), "count_mismatch"),
        (_attempt(outcome="ok", ended=None), CatalogRead("timeout"), "timeout, between requests at the store's bound"),
        (_attempt(attempt=2), CatalogRead("timeout"), "timeout, between requests at the store's bound"),
        (_attempt(attempt=4), CatalogRead("timeout"), "timeout"),
        (_attempt(attempt=2), CatalogRead("timeout", auto_paused=True), "timeout"),
        (None, CatalogRead("timeout"), "timeout, between requests at the store's bound"),
        (_attempt(outcome="ok", ended=None), None, "stopped by Ctrl+C"),
    ],
    ids=["ok", "other reason", "after a page", "retry wait", "fourth try", "auto-paused", "no request", "ctrl+c"],
)
def test_how_the_read_ended_names_a_timeout_between_requests(
    last: Attempt | None, result: CatalogRead | None, words: str
) -> None:
    """Review 1, finding 3: the reader's own bound checks (the wait before a request, the deadline check before one)
    end a read with `timeout` without an attempt `observe` sees; the summary says so."""
    assert report.read_ended([] if last is None else [last], result) == words


def test_a_read_ended_by_the_wait_before_a_request_is_reported_between_requests() -> None:
    """The reader itself: a spacing wait that would pass the store's bound ends the read with no attempt to see."""
    store = FakeCatalogStore(rows=[raw_product(1)])
    seen: list[Attempt] = []
    with WooClient(STORE_URL, KEY, SECRET, transport=store.transport, monotonic=store.time.monotonic) as client:
        result = catalog_read.read_catalog(
            client,
            spacing_ms=1000,
            stop=store.time,
            failures=catalog_read.MemoryFailureCount(),
            monotonic=store.time.monotonic,
            now=store.time.wall,
            store_seconds=0.5,
            observe=seen.append,
        )
    assert result.reason == "timeout" and [a.outcome for a in seen] == ["ok"]
    assert report.timing_lines("GF", seen, result)[0].startswith(
        "Timing, store GF: read timeout, between requests at the store's bound; requests 1,"
    )


def test_each_stores_summary_follows_its_counts_before_the_next_store(data_paths: DataPaths) -> None:
    """Review 1, finding 2: a store's summary is printed with its counts, so a later failure can't lose it."""
    make_database(data_paths)
    code, out, _, _ = in_process(data_paths, "--yes")
    assert code == 0
    assert out.index("Store GF: WooCommerce") < out.index("Timing, store GF:") < out.index("Store PW: WooCommerce")
    assert out.index("Timing, store PW:") < out.index("Across 2 stores:")


def test_ctrl_c_during_a_store_prints_what_was_gathered_so_far(data_paths: DataPaths) -> None:
    """Review 1, finding 2: Ctrl+C in the middle of PW's read: GF's summary is already out, PW's attempts so far are
    summed up, the trace lines already printed stay, and the command stops as before."""
    make_database(data_paths)
    pw = FakeCatalogStore(rows=[raw_product(2)])

    def interrupt(page: int) -> None:
        raise KeyboardInterrupt

    pw.before_page = interrupt
    stores = {"GF": FakeCatalogStore(rows=[raw_product(1)]), "PW": pw}
    code, out, err, _ = in_process(data_paths, "--yes", "--trace", stores=stores)
    assert code == 1 and "Stopped. Nothing was saved." in err
    assert "Timing, store GF: read ok; requests 2," in out
    assert "Timing, store PW: read stopped by Ctrl+C; requests 1," in out  # system_status; page 1 never answered
    assert [line[9:].split(":")[0] for line in out.splitlines() if TRACE_LINE.match(line)] == [
        "GF #1 system_status try 1",
        "GF #2 products page 1 try 1",
        "PW #1 system_status try 1",
    ]
    assert "Store PW: WooCommerce" not in out and "Across" not in out


def test_the_settings_line_names_the_local_zone_and_the_bounds_truthfully(data_paths: DataPaths) -> None:
    """Review 1, findings 1 and 4: the bounds hold plus up to the read timeout after the last byte; the trace's times
    are local, and the zone is named once."""
    make_database(data_paths)
    _, out, _, _ = in_process(data_paths, "--yes", "--store", "GF")
    zone = FakeTime().wall().astimezone().tzname()
    assert (
        "at most 600 s for each store's read and 120 s for one request, each plus up to the read timeout after the "
        f"last byte; read timeout 30 s; times are local, {zone}"
    ) in out
    settings = report.Settings(1000, catalog_read.ListingShape(), 600.0, 30, 120.0, False, "India Standard Time")
    assert "times are local, India Standard Time" in report.plan_lines([], settings)[1]


class _Closing(httpx.MockTransport):
    def __init__(self) -> None:
        super().__init__(lambda request: httpx.Response(200))
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_the_transport_is_closed_when_the_client_refuses_its_arguments() -> None:
    """Review 1, finding 5: an address that isn't https is refused by `WooClient`; the transport built for it is
    closed, not left open."""
    made: list[_Closing] = []

    def factory(store: report.StoreRef) -> httpx.BaseTransport:
        made.append(_Closing())
        return made[-1]

    store = report.StoreRef(1, "GF", "http://store-gf.example", 150, "Download", "active")
    settings = report.Settings(1000, catalog_read.ListingShape(), 600.0, 30, 120.0, False, "UTC")
    time = FakeTime()
    with pytest.raises(ValueError, match="https"):
        report._read_one(store, KEY, SECRET, settings, [], factory, print, time, time.monotonic, time.wall)
    assert len(made) == 1 and made[0].closed
