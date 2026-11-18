"""m3.2 review 2 (SYNC-01, SYNC-03): a night re-run when `snapshot_time` moves later the same day; a `running` row a
crash left, deferred on `busy`; impossible store dates refused at run time and in 0004's seeding; a night earlier than
the store's latest `ok` night refused."""

import shutil
from contextlib import closing
from datetime import UTC, datetime, timedelta
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


def test_moving_snapshot_time_later_the_same_day_runs_that_nights_snapshot_again() -> None:
    """Saved at 02:00, the time moved to 23:00 the same day: a snapshot runs that day at 23:00, replacing the
    night's first save (one state row per product, not two)."""
    rig = make_sync_rig(datetime(2026, 11, 18, 2, 0, 5, tzinfo=UTC))
    gf = rig.add_store("GF", [row(1)])
    rig.run("full")
    assert rig.tick() is not None
    rig.set("snapshot_time", '"23:00"')
    rig.at(datetime(2026, 11, 18, 22, 59, tzinfo=UTC))
    assert rig.service.scheduler.snapshot_plan(rig.time.wall()) is None
    rig.store("GF").find(1)["slug"] = "renamed"
    rig.at(datetime(2026, 11, 18, 23, 0, 5, tzinfo=UTC))
    plan = rig.tick()
    assert plan is not None and (plan.kind, plan.night) == ("snapshot", "2026-11-18")
    [(state, attempts, started)] = rig.rows(
        "SELECT state, attempts, started_at FROM snapshot_night WHERE store_id = ?", gf
    )
    assert (state, attempts) == ("ok", 1) and started.startswith("2026-11-18T23:00")
    assert rig.rows("SELECT slug, first_night, last_night FROM snapshot_state") == [
        ("renamed", "2026-11-18", "2026-11-18")
    ]
    assert rig.service.scheduler.snapshot_plan(rig.time.wall()) is None


def test_a_running_row_a_crash_left_is_deferred_on_busy_not_failed() -> None:
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
    [(state, attempts, reason, next_try, finished)] = rig.rows(
        "SELECT state, attempts, reason, next_try_at, finished_at FROM snapshot_night"
    )
    assert (state, attempts, reason) == ("retry", 3, "busy")
    assert datetime.fromisoformat(next_try) - datetime.fromisoformat(finished) == timedelta(minutes=5)


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
