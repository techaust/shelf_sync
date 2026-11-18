"""APL-12 (the owner, 11 2026-11-18; m3.2 F1): failed **reads** in a row, not failed requests. Which reasons count (an
explicit never-counting list; every other reason counts), a read that was stopped or hit a database error neither
counts nor resets, and Test connection never touches the count."""

import sqlite3
from contextlib import closing
from datetime import UTC, datetime

import httpx
import pytest

from shelfsync.apply.catalog_read import READ_REASONS, SNAPSHOT_REASONS
from shelfsync.apply.woocommerce import REFUSED_REASONS, UNREACHABLE_REASONS
from shelfsync.catalog import runner as runner_module
from shelfsync.db import catalog as db
from tests.catalog_support import make_db
from tests.sync_support import make_sync_rig, row

START = datetime(2026, 11, 18, 10, 0, tzinfo=UTC)

# The coordinator's list (m3.2 F1), word for word: these never count.
NEVER = {
    "stopped",
    "busy",
    "paused",
    "auto_paused",
    "store_removed",
    "address_changed",
    "keys_missing",
    "secrets_unavailable",
    "no_full_read",
    "no_catalog",
    "database_error",
    "internal",
    "snapshot_too_large",
    "night_done",
    "interrupted",
}
# Every reason a read can end with: the store client's, the reader's, the snapshot's and the runner's own.
EVERY_REASON = sorted(UNREACHABLE_REASONS | REFUSED_REASONS | READ_REASONS | SNAPSHOT_REASONS | NEVER)


def test_the_never_counting_list_is_exactly_the_decided_one() -> None:
    assert db.NOT_COUNTED == NEVER
    assert {"too_many_missing", "count_mismatch", "no_products", "bad_response", "timeout"} <= set(EVERY_REASON)


@pytest.mark.parametrize("reason", EVERY_REASON)
def test_each_reason_counts_once_unless_it_is_on_the_never_counting_list(reason: str) -> None:
    """Deny by default: a reason not on the list counts."""
    rig = make_db()
    store_id = rig.add_store("GF")
    with closing(rig.connect()) as connection:
        db.record_read_failed(connection, store_id, reason=reason, http_status=None, pages=0, total=None, at="t")
        db.record_incremental_failed(connection, store_id, reason=reason, http_status=None, at="t")
    expected = 0 if reason in NEVER else 2
    assert rig.rows("SELECT failures_in_row, auto_paused_at FROM sync_state") == [(expected, None)]


def test_a_reason_never_seen_before_counts() -> None:
    assert db.counts("some_new_reason") and not db.counts("stopped")


def test_a_stopped_read_neither_counts_nor_resets() -> None:
    rig = make_sync_rig(START)
    gf = rig.add_store("GF", [row(1)])
    rig.run("full")
    with closing(rig.db.connect()) as connection:
        connection.execute("UPDATE sync_state SET failures_in_row = 5 WHERE store_id = ?", (gf,))
    rig.time.stop_after = len(rig.time.waits) + 1
    assert rig.service.start_sync("full") == "full"
    rig.service.runner.join(30.0)
    assert rig.service.runner.state().outcomes == {gf: "stopped"}
    assert rig.rows("SELECT failures_in_row, read_reason FROM sync_state") == [(5, "stopped")]


def test_a_database_error_while_saving_leaves_the_count_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    rig = make_sync_rig(START)
    gf = rig.add_store("GF", [row(1)])
    rig.run("full")
    with closing(rig.db.connect()) as connection:
        connection.execute("UPDATE sync_state SET failures_in_row = 3 WHERE store_id = ?", (gf,))

    def broken(*args: object, **kwargs: object) -> None:
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(runner_module, "save_store_read", broken)
    rig.run("full")
    assert rig.service.runner.state().outcomes == {gf: "database_error"}
    assert rig.rows("SELECT failures_in_row, read_reason FROM sync_state") == [(3, "database_error")]


def test_a_read_that_retried_and_then_worked_resets_the_count_in_its_save() -> None:
    rig = make_sync_rig(START)
    gf = rig.add_store("GF", [row(1)])
    rig.run("full")
    with closing(rig.db.connect()) as connection:
        connection.execute("UPDATE sync_state SET failures_in_row = 7 WHERE store_id = ?", (gf,))
    sent = {"n": 0}

    def flaky(request: httpx.Request) -> httpx.Response | None:
        sent["n"] += 1
        return httpx.Response(524) if sent["n"] <= 2 else None

    rig.store("GF").fail = flaky
    rig.run("incremental")
    assert rig.rows("SELECT failures_in_row FROM sync_state") == [(0,)]


def test_test_connection_never_touches_the_count() -> None:
    """Settings' Test connection is not a read: the count and the pause stay as they are."""
    rig = make_sync_rig(START)
    gf = rig.add_store("GF", [row(1)])
    rig.run("full")
    with closing(rig.db.connect()) as connection:
        connection.execute("UPDATE sync_state SET failures_in_row = 4 WHERE store_id = ?", (gf,))
    rig.store("GF").fail = lambda request: httpx.Response(500)
    rig.stores.test(gf)
    assert rig.rows("SELECT failures_in_row, auto_paused_at FROM sync_state") == [(4, None)]
