"""SYNC-01, SYNC-03, SYNC-04, APL-12: when the scheduled reads run (`catalog/schedule.py`, `catalog/scheduler.py`) on a
fake clock: the night's snapshot at 02:00 local, across a daylight-saving change both ways, caught up at a start and
at a wake, one catch-up after a sleep across several nights, a stalled store retried later the same night without
holding up the other, the auto-pause rule for snapshot attempts, paused and auto-paused stores skipped, the
incremental's cadence, and never two runs at once."""

import threading
from contextlib import closing
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from shelfsync.catalog.schedule import (
    ATTEMPTS_MAX,
    NOT_RETRIED,
    RETRY_AFTER,
    SnapshotTime,
    incremental_due,
    latest_slot,
    next_slot,
    night_due,
    night_of,
    retry_at,
)
from tests.store_support import PRODUCTS, SYSTEM_STATUS
from tests.sync_support import FAKE_BERLIN, FAKE_NEW_YORK, UTC_ZONE, SyncRig, make_sync_rig, row

TWO = SnapshotTime(2, 0)


def utc(day: int, hour: int = 2, minute: int = 0, second: int = 30, month: int = 11) -> datetime:
    return datetime(2026, month, day, hour, minute, second, tzinfo=UTC)


def built(rig: SyncRig, *codes: str) -> dict[str, int]:
    """Stores with a full read that worked (a catalog, a watermark)."""
    ids = {code: rig.add_store(code, [row(1), row(2)]) for code in codes}
    assert rig.run("full") == "full"
    return ids


def nights(rig: SyncRig) -> list[tuple[str, int, str, int]]:
    return [
        (night, store, state, attempts)
        for night, store, state, attempts in rig.rows(
            "SELECT night, store_id, state, attempts FROM snapshot_night ORDER BY night, store_id"
        )
    ]


def failing(request: httpx.Request) -> httpx.Response | None:
    return httpx.Response(500)


# ---- the pure rules ------------------------------------------------------------------------------------------------


def test_the_slot_and_the_night_follow_local_time() -> None:
    assert latest_slot(utc(18, 1, 59, 59), UTC_ZONE, TWO) == utc(17, 2, 0, 0)
    assert latest_slot(utc(18, 2, 0, 0), UTC_ZONE, TWO) == utc(18, 2, 0, 0)
    assert next_slot(utc(18, 2, 0, 0), UTC_ZONE, TWO) == utc(19, 2, 0, 0)
    assert night_of(utc(18, 1, 59, 59), UTC_ZONE, TWO) == "2026-11-17"
    assert night_of(utc(18, 2, 0, 0), UTC_ZONE, TWO) == "2026-11-18"
    assert night_of(utc(18, 23, 30), UTC_ZONE, SnapshotTime(23, 45)) == "2026-11-17"


def test_the_slot_moves_with_the_clocks_going_back() -> None:
    """02:00 local is 06:00 UTC before New York's clocks go back and 07:00 UTC after."""
    assert latest_slot(utc(31, 12, month=10), FAKE_NEW_YORK, TWO) == datetime(2026, 10, 31, 6, 0, tzinfo=UTC)
    assert next_slot(utc(31, 12, month=10), FAKE_NEW_YORK, TWO) == datetime(2026, 11, 1, 7, 0, tzinfo=UTC)
    assert night_of(datetime(2026, 11, 1, 6, 59, tzinfo=UTC), FAKE_NEW_YORK, TWO) == "2026-10-31"
    assert night_of(datetime(2026, 11, 1, 7, 0, tzinfo=UTC), FAKE_NEW_YORK, TWO) == "2026-11-01"


@pytest.mark.parametrize(
    ("state", "next_try_at", "due"),
    [
        (None, None, True),  # no row yet
        ("running", None, True),  # an attempt the app's end cut off
        ("retry", "2026-11-18T02:30:00.000000Z", False),
        ("retry", "2026-11-18T02:00:00.000000Z", True),
        ("ok", None, False),
        ("failed", None, False),
        ("skipped", None, False),
    ],
)
def test_which_nights_are_due(state: str | None, next_try_at: str | None, due: bool) -> None:
    assert night_due(state, next_try_at, "2026-11-18T02:10:00.000000Z") is due


def test_the_same_night_retry_rule() -> None:
    """Lead (proposed): 30 minutes later, at most 3 attempts; none for a reason waiting can't change or an auto-paused
    store; an attempt the shutdown stopped is due at the next start."""
    moment = utc(18)
    assert retry_at("timeout", 1, moment, auto_paused=False) == moment + RETRY_AFTER
    assert retry_at("server_error", 2, moment, auto_paused=False) == moment + timedelta(minutes=30)
    assert retry_at("timeout", ATTEMPTS_MAX, moment, auto_paused=False) is None
    assert retry_at("timeout", 1, moment, auto_paused=True) is None
    assert retry_at("stopped", 1, moment, auto_paused=False) == moment
    for reason in NOT_RETRIED:
        assert retry_at(reason, 1, moment, auto_paused=False) is None, reason


def test_the_incremental_comes_one_interval_after_the_last_one_started() -> None:
    since = utc(18, 10)
    assert incremental_due(since, None, 15) == utc(18, 10, 15)
    assert incremental_due(since, utc(18, 10, 20), 15) == utc(18, 10, 35)
    assert incremental_due(since, utc(17, 23), 15) == utc(18, 10, 15)  # one from before the scheduler started


# ---- the scheduler on a fake clock ---------------------------------------------------------------------------------


def test_a_missed_night_is_caught_up_at_start_and_the_next_one_runs_at_02_00() -> None:
    """SYNC-03: the PC was off at 02:00: the first check after the start takes the night; the next night waits
    for 02:00 local."""
    rig = make_sync_rig(utc(18, 9))
    ids = built(rig, "GF", "PW")
    plan = rig.tick()
    assert plan is not None and (plan.kind, plan.night, plan.stores) == (
        "snapshot",
        "2026-11-18",
        frozenset(ids.values()),
    )
    assert nights(rig) == [("2026-11-18", ids["GF"], "ok", 1), ("2026-11-18", ids["PW"], "ok", 1)]
    rig.at(utc(19, 1, 59, 0))
    plan = rig.tick()
    assert plan is not None and plan.kind == "incremental"  # no snapshot before 02:00
    rig.at(utc(19, 2, 0, 5))
    plan = rig.tick()
    assert plan is not None and (plan.kind, plan.night) == ("snapshot", "2026-11-19")
    assert rig.service.scheduler.snapshot_plan(rig.time.wall()) is None  # once it has worked, not again


def test_a_wake_after_02_00_catches_the_night_up() -> None:
    rig = make_sync_rig(utc(18, 1, 0))
    built(rig, "GF")
    plan = rig.tick()
    assert plan is not None and plan.night == "2026-11-17"  # the start caught up the night before
    rig.at(utc(18, 9, 0))  # asleep from 01:00 to 09:00
    plan = rig.tick()
    assert plan is not None and (plan.kind, plan.night) == ("snapshot", "2026-11-18")


def test_a_sleep_across_several_nights_catches_up_one_night_not_several() -> None:
    rig = make_sync_rig(utc(17, 3))
    built(rig, "GF")
    rig.tick()
    rig.at(utc(20, 9))  # asleep through the 18th, 19th and 20th
    plan = rig.tick()
    assert plan is not None and plan.night == "2026-11-20"
    assert rig.service.scheduler.snapshot_plan(rig.time.wall()) is None
    assert [night for night, *_ in nights(rig)] == ["2026-11-17", "2026-11-20"]


def test_each_night_runs_once_when_the_clocks_go_back() -> None:
    """SYNC-03 across a daylight-saving change (a fake New York): the repeated hour neither repeats nor skips one."""
    rig = make_sync_rig(datetime(2026, 10, 31, 6, 0, 10, tzinfo=UTC), FAKE_NEW_YORK)
    built(rig, "GF")
    assert rig.tick() is not None  # 02:00:10 EDT, night 2026-10-31
    rig.at(datetime(2026, 11, 1, 6, 59, 0, tzinfo=UTC))  # 01:59 EST, the repeated hour: still the 31st's night
    assert rig.service.scheduler.snapshot_plan(rig.time.wall()) is None
    rig.at(datetime(2026, 11, 1, 7, 0, 5, tzinfo=UTC))  # 02:00 EST
    plan = rig.tick()
    assert plan is not None and plan.night == "2026-11-01"
    rig.at(datetime(2026, 11, 2, 6, 59, 0, tzinfo=UTC))
    assert rig.service.scheduler.snapshot_plan(rig.time.wall()) is None
    rig.at(datetime(2026, 11, 2, 7, 0, 5, tzinfo=UTC))
    plan = rig.tick()
    assert plan is not None and plan.night == "2026-11-02"


def test_each_night_runs_once_when_the_clocks_go_forward() -> None:
    """A fake Berlin, 2026-03-29: 02:00 local doesn't exist that night. Checked every 20 minutes for three days,
    each night is taken exactly once."""
    rig = make_sync_rig(datetime(2026, 3, 28, 0, 0, tzinfo=UTC), FAKE_BERLIN)
    built(rig, "GF")
    taken: list[str] = []
    moment = datetime(2026, 3, 28, 0, 0, tzinfo=UTC)
    while moment < datetime(2026, 3, 30, 23, 0, tzinfo=UTC):  # 01:00 local on the 31st
        moment += timedelta(minutes=20)
        rig.at(moment)
        plan = rig.tick()
        if plan is not None and plan.kind == "snapshot" and plan.night is not None:
            taken.append(plan.night)
    assert taken == ["2026-03-27", "2026-03-28", "2026-03-29", "2026-03-30"]


def test_a_stalled_store_is_tried_again_later_the_same_night_without_holding_up_the_other() -> None:
    """L1's lesson: GF fails at 02:00 (its retries spent), PW's snapshot still works; GF is tried again at 02:30
    alone, and works."""
    rig = make_sync_rig(utc(18, 2, 0, 5))
    ids = built(rig, "GF", "PW")
    rig.store("GF").fail = lambda request: httpx.Response(524) if request.url.path.endswith(PRODUCTS) else None
    plan = rig.tick()
    assert plan is not None and plan.kind == "snapshot"
    assert nights(rig) == [("2026-11-18", ids["GF"], "retry", 1), ("2026-11-18", ids["PW"], "ok", 1)]
    [(next_try,)] = rig.rows("SELECT next_try_at FROM snapshot_night WHERE store_id = ?", ids["GF"])
    assert next_try.startswith("2026-11-18T02:30")
    rig.at(utc(18, 2, 20))
    assert rig.service.scheduler.snapshot_plan(rig.time.wall()) is None  # not yet
    rig.store("GF").fail = None
    rig.at(utc(18, 2, 31))
    plan = rig.tick()
    assert plan is not None and (plan.kind, plan.stores) == ("snapshot", frozenset({ids["GF"]}))
    assert nights(rig) == [("2026-11-18", ids["GF"], "ok", 2), ("2026-11-18", ids["PW"], "ok", 1)]


def test_a_store_down_all_night_isnt_auto_paused_by_the_nights_attempts_but_is_by_the_next_read() -> None:
    """The auto-pause rule (Lead (proposed), `catalog/schedule.py`): 3 attempts of 4 failed requests each stop at
    nine, scheduled incrementals skip the store while it waits for its retry, and the first failed request after the
    night's last attempt pauses it."""
    rig = make_sync_rig(utc(18, 2, 0, 5))
    ids = built(rig, "GF", "PW")
    gf, pw = ids["GF"], ids["PW"]
    rig.store("GF").fail = failing
    rig.tick()
    assert rig.rows("SELECT failures_in_row, auto_paused_at FROM sync_state WHERE store_id = ?", gf) == [(4, None)]
    rig.at(utc(18, 2, 16))
    plan = rig.tick()
    assert plan is not None and plan.kind == "incremental"
    assert rig.service.runner.state().outcomes == {gf: "snapshot_retry", pw: None}  # GF skipped, PW read
    for minute in (31, 62):
        rig.at(utc(18, 2, 0) + timedelta(minutes=minute))
        plan = rig.tick()
        assert plan is not None and plan.kind == "snapshot"
    assert nights(rig)[0] == ("2026-11-18", gf, "failed", 3)
    assert rig.rows("SELECT failures_in_row, auto_paused_at FROM sync_state WHERE store_id = ?", gf) == [(9, None)]
    rig.at(utc(18, 3, 20))
    plan = rig.tick()
    assert plan is not None and plan.kind == "incremental"
    [(count, paused_at)] = rig.rows("SELECT failures_in_row, auto_paused_at FROM sync_state WHERE store_id = ?", gf)
    assert count == 10 and paused_at is not None  # really down: paused by its next read


def test_a_store_slow_for_the_first_two_attempts_ends_the_night_with_its_count_back_at_zero() -> None:
    rig = make_sync_rig(utc(18, 2, 0, 5))
    ids = built(rig, "GF")
    with closing(rig.db.connect()) as connection:
        connection.execute("UPDATE sync_state SET failures_in_row = 6 WHERE store_id = ?", (ids["GF"],))
    rig.store("GF").fail = failing
    rig.tick()
    rig.at(utc(18, 2, 31))
    rig.tick()
    assert rig.rows("SELECT failures_in_row, auto_paused_at FROM sync_state") == [(9, None)]  # never past nine
    rig.store("GF").fail = None
    rig.at(utc(18, 3, 2))
    rig.tick()
    assert rig.rows("SELECT failures_in_row, auto_paused_at FROM sync_state") == [(0, None)]
    assert nights(rig) == [("2026-11-18", ids["GF"], "ok", 3)]


def test_paused_auto_paused_and_unread_stores_are_skipped_and_the_night_says_why() -> None:
    rig = make_sync_rig(utc(18, 2, 0, 5))
    ids = built(rig, "GF", "PW", "TS")
    with closing(rig.db.connect()) as connection:
        connection.execute("UPDATE store SET state = 'paused' WHERE id = ?", (ids["GF"],))
        connection.execute(
            "UPDATE sync_state SET auto_paused_at = 'x', auto_pause_reason = 'timeout' WHERE store_id = ?",
            (ids["PW"],),
        )
    new = rig.add_store("NW", [row(1)])  # no full read yet
    sent = len(rig.sites.requests)
    rig.tick()
    assert rig.rows("SELECT store_id, state, reason FROM snapshot_night ORDER BY store_id") == [
        (ids["GF"], "skipped", "paused"),
        (ids["PW"], "skipped", "auto_paused"),
        (ids["TS"], "ok", None),
        (new, "skipped", "no_catalog"),
    ]
    assert {request.url.host for request in rig.sites.requests[sent:]} == {"store-ts.example"}
    assert rig.service.scheduler.snapshot_plan(rig.time.wall()) is None  # a skipped night is done


def test_the_incremental_runs_every_interval_and_sync_now_moves_the_next_one() -> None:
    """SYNC-01: every `sync_interval_minutes` (a setting, read at each check), counted from the last incremental
    that started, Sync now's included."""
    start = utc(18, 10)
    rig = make_sync_rig(start)
    built(rig, "GF")
    assert rig.tick() is not None  # the night's catch-up
    rig.at(start + timedelta(minutes=14))
    assert rig.tick() is None
    rig.at(start + timedelta(minutes=15, seconds=30))  # the full read before took a few fake seconds
    plan = rig.tick()
    assert plan is not None and plan.kind == "incremental"
    rig.at(start + timedelta(minutes=20))
    assert rig.run() == "incremental"  # Sync now
    rig.at(start + timedelta(minutes=34))
    assert rig.tick() is None
    rig.at(start + timedelta(minutes=35, seconds=1))
    assert rig.tick() is not None
    rig.set("sync_interval_minutes", "60")
    rig.at(start + timedelta(minutes=80))
    assert rig.tick() is None
    rig.at(start + timedelta(minutes=96))
    assert rig.tick() is not None


def test_no_incremental_is_scheduled_before_any_store_has_a_full_read() -> None:
    rig = make_sync_rig(utc(18, 10))
    rig.add_store("GF", [row(1)])
    rig.tick()  # records the night as skipped (no catalog)
    rig.at(utc(18, 12))
    assert rig.tick() is None
    assert rig.service.scheduler.incremental_at(rig.time.wall()) is None
    assert rig.rows("SELECT inc_started_at FROM sync_state") == []


def test_the_scheduler_never_starts_a_run_while_another_runs() -> None:
    rig = make_sync_rig(utc(18, 10))
    built(rig, "GF")
    gate = threading.Event()
    rig.sites.gate = gate
    try:
        assert rig.service.start_sync("full") == "full"
        assert rig.service.scheduler.tick() is None  # due, but a run is going
    finally:
        gate.set()
        rig.service.runner.join(30.0)
    rig.sites.gate = None
    plan = rig.tick()
    assert plan is not None and plan.kind == "snapshot"


def test_a_night_whose_last_attempt_was_cut_off_is_closed_not_run_again() -> None:
    rig = make_sync_rig(utc(18, 2, 5))
    ids = built(rig, "GF")
    with closing(rig.db.connect()) as connection:
        connection.execute(
            "INSERT INTO snapshot_night (store_id, night, state, attempts) VALUES (?, '2026-11-18', 'running', 3)",
            (ids["GF"],),
        )
    sent = len(rig.sites.requests)
    rig.tick()
    assert rig.rows("SELECT state, reason FROM snapshot_night") == [("failed", "interrupted")]
    assert len(rig.sites.requests) == sent
    assert rig.service.scheduler.snapshot_plan(rig.time.wall()) is None


def test_a_snapshot_never_sends_anything_but_gets() -> None:
    rig = make_sync_rig(utc(18, 2, 5))
    built(rig, "GF", "PW")
    rig.tick()
    rig.at(utc(18, 2, 30))
    rig.tick()
    assert rig.sites.requests and {request.method for request in rig.sites.requests} == {"GET"}
    assert any(request.url.path.endswith(SYSTEM_STATUS) for request in rig.sites.requests)
