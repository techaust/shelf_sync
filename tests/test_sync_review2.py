"""m3.2 review 2 (SYNC-01, SYNC-03): a night re-run when `snapshot_time` moves later the same day; a `running` row a
crash left, deferred on `busy`; impossible store dates refused at run time and in 0004's seeding; a night earlier than
the store's latest `ok` night refused."""

import shutil
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import pytest

from shelfsync.catalog.runner import RunPlan
from shelfsync.catalog.watermark import next_watermark
from shelfsync.db import snapshots
from shelfsync.db.connection import connect
from shelfsync.db.migrate import DEFAULT_MIGRATIONS_DIR, migrate
from tests.catalog_support import product
from tests.sync_support import FakeSyncStore, make_sync_rig, row
from tests.test_sync_read import incremental


def test_a_running_row_with_no_attempt_left_then_busy_is_closed_and_the_incrementals_run() -> None:
    """The re-check's finding A: killed during attempt 3, then `busy` at the next check: the row is closed `failed`,
    `interrupted` (not left `retry` with no attempt left), no snapshot is picked at the later checks, and the
    incrementals run again."""
    rig = make_sync_rig(datetime(2026, 11, 18, 10, 0, tzinfo=UTC))
    gf = rig.add_store("GF", [row(1)])
    rig.run("full")
    with closing(rig.db.connect()) as connection:
        connection.execute(
            "INSERT INTO snapshot_night (store_id, night, state, attempts, started_at) "
            "VALUES (?, '2026-11-18', 'running', 3, '2026-11-18T02:00:00.000000Z')",
            (gf,),
        )
    assert rig.stores.slots.claim(gf)
    try:
        assert rig.service.runner.start(RunPlan("snapshot", night="2026-11-18"))
        rig.service.runner.join(60.0)
    finally:
        rig.stores.slots.release(gf)
    assert rig.rows("SELECT state, attempts, reason, next_try_at FROM snapshot_night") == [
        ("failed", 3, "interrupted", None)
    ]
    kinds = []
    for minute in (3, 4, 18):  # (the busy wait took 70 s) the scheduler starts at its first check: 15 minutes on
        rig.at(datetime(2026, 11, 18, 10, minute, tzinfo=UTC))
        plan = rig.tick()
        kinds.append(plan.kind if plan is not None else None)
    assert kinds == [None, None, "incremental"]  # never the snapshot again


def test_a_retry_row_with_no_attempt_left_is_never_due_and_is_closed_when_met() -> None:
    """Finding A's second guard (`night_due`) and the runner's `ValueError` branch."""
    from shelfsync.catalog.schedule import night_due

    assert not night_due("retry", None, "2026-11-18T10:00:00.000000Z", attempts=3)
    assert night_due("retry", None, "2026-11-18T10:00:00.000000Z", attempts=2)
    rig = make_sync_rig(datetime(2026, 11, 18, 10, 0, tzinfo=UTC))
    gf = rig.add_store("GF", [row(1)])
    rig.run("full")
    with closing(rig.db.connect()) as connection:
        connection.execute(
            "INSERT INTO snapshot_night (store_id, night, state, attempts) VALUES (?, '2026-11-18', 'retry', 3)", (gf,)
        )
    assert rig.service.scheduler.snapshot_plan(rig.time.wall()) is None
    assert rig.service.runner.start(RunPlan("snapshot", night="2026-11-18"))
    rig.service.runner.join(60.0)
    assert rig.rows("SELECT state, reason FROM snapshot_night") == [("failed", "interrupted")]


def test_a_night_left_by_a_corrected_forward_clock_jump_doesnt_stop_the_real_nights() -> None:
    """The re-check's finding B: an `ok` night 2027-06-01 is on record (the clock had jumped and was put right); the
    real nights from 2026-11-21 still run and save, and `next_runs` agrees with the plan."""
    rig = make_sync_rig(datetime(2026, 11, 20, 12, 0, tzinfo=UTC))
    gf = rig.add_store("GF", [row(1)])
    rig.run("full")
    with closing(rig.db.connect()) as connection:
        connection.execute(
            "INSERT INTO snapshot_night (store_id, night, state, attempts, started_at, finished_at) VALUES "
            "(?, '2027-06-01', 'ok', 1, '2027-06-01T02:00:05.000000Z', '2027-06-01T02:01:00.000000Z')",
            (gf,),
        )
    for day in (21, 22):
        rig.at(datetime(2026, 11, day, 2, 0, 5, tzinfo=UTC))
        assert rig.service.scheduler.next_runs().snapshots[gf] == rig.time.wall()  # due now, as the plan says
        plan = rig.tick()
        assert plan is not None and (plan.kind, plan.night) == ("snapshot", f"2026-11-{day}")
    assert rig.rows("SELECT night, state FROM snapshot_night WHERE night LIKE '2026-%' ORDER BY night") == [
        ("2026-11-21", "ok"),
        ("2026-11-22", "ok"),
    ]


@pytest.mark.parametrize("bad", ["2026-11-31T10:00:00", "2026-11-10T25:00:00", "2026-13-01T00:00:00"])
def test_an_impossible_store_date_fails_the_read_closed_and_never_becomes_the_watermark(bad: str) -> None:
    result = incremental(FakeSyncStore(rows=[row(1, modified=bad)]))
    assert (result.reason, result.bad_field) == ("bad_response", "date_modified_gmt")
    now = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)
    from dataclasses import replace

    assert next_watermark("2026-11-01T00:00:00", [replace(product(1), modified_gmt=bad)], now) == "2026-11-01T00:00:00"


def test_0004_seeding_leaves_out_impossible_dates(tmp_path: Path) -> None:
    folder = tmp_path / "m"
    folder.mkdir()
    for name in ("0001_base.sql", "0002_store.sql", "0003_catalog.sql"):
        shutil.copy(DEFAULT_MIGRATIONS_DIR / name, folder / name)
    with closing(connect(tmp_path / "old.db")) as connection:
        migrate(connection, folder)
        connection.execute(
            "INSERT INTO store (name, url, code, shape, color, spacing_ms, main_button, created_at) "
            "VALUES ('S', 'https://s.example', 'GF', 'circle', 'indigo', 150, 'Download', 't')"
        )
        for wc_id, modified in ((1, "2026-11-10T08:00:00"), (2, "2026-02-30T10:00:00"), (3, "2026-11-10T25:00:00")):
            connection.execute(
                "INSERT INTO store_product (store_id, wc_id, slug, title, type, status, modified_gmt, downloads_json, "
                "meta_json, seen_at) VALUES (1, ?, 's', 't', 'simple', 'publish', ?, '[]', '[]', 't')",
                (wc_id, modified),
            )
        connection.execute("INSERT INTO sync_state (store_id, last_ok_at) VALUES (1, 't')")
        assert migrate(connection) == [4]
        assert connection.execute("SELECT watermark_gmt FROM sync_state").fetchall() == [("2026-11-10T08:00:00",)]


def test_a_night_earlier_than_the_stores_latest_ok_night_is_refused() -> None:
    """A clock moved back: the night is refused (`NightBehind`), and through the runner recorded as `internal`."""
    rig = make_sync_rig(datetime(2026, 11, 20, 10, 0, tzinfo=UTC))
    gf = rig.add_store("GF", [row(1)])
    rig.run("full")
    assert rig.service.runner.start(RunPlan("snapshot", night="2026-11-20"))
    rig.service.runner.join(60.0)
    with closing(rig.db.connect()) as connection:
        snapshots.start_attempt(connection, gf, "2026-11-19", "t")
        with pytest.raises(snapshots.NightBehind):
            snapshots.save_snapshot(
                connection,
                gf,
                "2026-11-19",
                [],
                {},
                listing="include_status",
                at="t",
                read_url="https://store-gf.example",
                retention_days=30,
            )
    assert rig.service.runner.start(RunPlan("snapshot", night="2026-11-18"))
    rig.service.runner.join(60.0)
    assert rig.rows("SELECT night, state, reason FROM snapshot_night ORDER BY night") == [
        ("2026-11-18", "retry", "internal"),
        ("2026-11-19", "running", None),
        ("2026-11-20", "ok", None),
    ]
