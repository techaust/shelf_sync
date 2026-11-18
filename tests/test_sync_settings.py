"""SYNC-01, SYNC-03, SYS-07: the two sync settings (`db/settings.py`, `GET`/`PUT /api/settings/app`) and migration 0004
(the incremental watermark, carried over from a full read made before it, and the snapshot tables' checks)."""

import shutil
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest

from shelfsync.api.app_settings import APP_SETTINGS_PATH, AppSettingsService, AppSettingsValues
from shelfsync.db.connection import connect
from shelfsync.db.migrate import DEFAULT_MIGRATIONS_DIR, migrate
from shelfsync.db.settings import get_setting, set_setting, snapshot_hour_minute
from shelfsync.platform.autostart import FakeRunKey
from shelfsync.ports import DEFAULT_PORT
from tests.catalog_support import make_db
from tests.support import WRITE_HEADERS, make_harness

FIVE: dict[str, Any] = {
    "port": DEFAULT_PORT,
    "theme": "system",
    "start_with_windows": True,
    "notifications": True,
    "log_retention_days": 30,
}


def _client(tmp_path: Path) -> tuple[Any, Path]:
    database = tmp_path / "shelfsync.db"
    with closing(connect(database)) as setup:
        migrate(setup)
    service = AppSettingsService(lambda: connect(database), DEFAULT_PORT, None, FakeRunKey(), lambda: False)
    return make_harness(app_settings=service).signed_in_client(), database


def test_the_defaults_are_15_minutes_and_02_00(tmp_path: Path) -> None:
    """SYNC-01, SYNC-03: the PRD's defaults, shown by GET beside the five."""
    client, _ = _client(tmp_path)
    body = client.get(APP_SETTINGS_PATH).json()
    assert (body["sync_interval_minutes"], body["snapshot_time"]) == (15, "02:00")


def test_a_put_saves_the_sync_settings_and_one_without_them_keeps_them(tmp_path: Path) -> None:
    """Lead (proposed): the two are optional in the PUT, so the m2 screen's body (the five) keeps them."""
    client, database = _client(tmp_path)
    saved = client.put(
        APP_SETTINGS_PATH, json={**FIVE, "sync_interval_minutes": 30, "snapshot_time": "03:45"}, headers=WRITE_HEADERS
    )
    assert saved.status_code == 200
    assert (saved.json()["sync_interval_minutes"], saved.json()["snapshot_time"]) == (30, "03:45")
    again = client.put(APP_SETTINGS_PATH, json=FIVE, headers=WRITE_HEADERS)
    assert (again.json()["sync_interval_minutes"], again.json()["snapshot_time"]) == (30, "03:45")
    nulls = client.put(
        APP_SETTINGS_PATH, json={**FIVE, "sync_interval_minutes": None, "snapshot_time": None}, headers=WRITE_HEADERS
    )
    assert nulls.status_code == 200 and nulls.json()["snapshot_time"] == "03:45"
    with closing(connect(database)) as connection:
        assert get_setting(connection, "sync_interval_minutes") == 30
        assert get_setting(connection, "snapshot_time") == "03:45"


@pytest.mark.parametrize(
    "change",
    [
        {"sync_interval_minutes": 4},
        {"sync_interval_minutes": 241},
        {"sync_interval_minutes": "15"},
        {"sync_interval_minutes": True},
        {"snapshot_time": "2:00"},
        {"snapshot_time": "24:00"},
        {"snapshot_time": "02:60"},
        {"snapshot_time": "02:00\n"},
        {"snapshot_time": 200},
    ],
)
def test_a_value_outside_the_rules_is_the_fixed_422(tmp_path: Path, change: dict[str, Any]) -> None:
    client, _ = _client(tmp_path)
    response = client.put(APP_SETTINGS_PATH, json={**FIVE, **change}, headers=WRITE_HEADERS)
    assert (response.status_code, response.json()) == (422, {"error": "invalid_request"})


def test_the_database_rules_match_the_api_rules() -> None:
    db = make_db()
    with closing(db.connect()) as connection:
        for good in (5, 240):
            set_setting(connection, "sync_interval_minutes", good)
        for bad in (4, 241):
            with pytest.raises(ValueError):
                set_setting(connection, "sync_interval_minutes", bad)
        for good_time in ("00:00", "23:59", "02:00"):
            set_setting(connection, "snapshot_time", good_time)
        for bad_time in ("24:00", "2:00", "02:5", "ab:cd", "02:00 "):
            with pytest.raises(ValueError):
                set_setting(connection, "snapshot_time", bad_time)
    assert snapshot_hour_minute("07:05") == (7, 5)


def test_a_hand_edited_stored_value_reads_as_its_default(tmp_path: Path) -> None:
    client, database = _client(tmp_path)
    with closing(connect(database)) as connection:
        connection.execute("INSERT INTO setting (key, value_json) VALUES ('snapshot_time', '\"25:00\"')")
        connection.execute("INSERT INTO setting (key, value_json) VALUES ('sync_interval_minutes', '1')")
    body = client.get(APP_SETTINGS_PATH).json()
    assert (body["sync_interval_minutes"], body["snapshot_time"]) == (15, "02:00")


def test_the_put_answer_always_reports_both_as_stored_never_null(tmp_path: Path) -> None:
    """The contract the screens type against: the request may leave the two out or null; the answer (like GET) has
    both, never null."""
    client, _ = _client(tmp_path)
    schemas = client.app.openapi()["components"]["schemas"]  # type: ignore[attr-defined]
    for name in ("AppSettingsSaved", "AppSettingsResponse"):
        assert {"sync_interval_minutes", "snapshot_time"} <= set(schemas[name]["required"]), name
        for key in ("sync_interval_minutes", "snapshot_time"):
            assert "anyOf" not in schemas[name]["properties"][key] and "type" in schemas[name]["properties"][key]
    assert not {"sync_interval_minutes", "snapshot_time"} & set(schemas["AppSettingsValues"]["required"])
    answer = client.put(
        APP_SETTINGS_PATH, json={**FIVE, "sync_interval_minutes": None, "snapshot_time": None}, headers=WRITE_HEADERS
    ).json()
    assert (answer["sync_interval_minutes"], answer["snapshot_time"]) == (15, "02:00")


def test_the_put_body_names_the_two_optional_settings() -> None:
    """The backup import writes the two only when a file has them (`AppSettingsValues.OPTIONAL`, choice 9)."""
    body = AppSettingsValues(**FIVE, sync_interval_minutes=30, snapshot_time="03:00")
    assert AppSettingsValues.OPTIONAL == ("sync_interval_minutes", "snapshot_time")
    assert body.model_dump(exclude=set(AppSettingsValues.OPTIONAL)) == FIVE
    assert AppSettingsValues(**FIVE).sync_interval_minutes is None


def test_0004_starts_the_watermark_from_a_full_read_saved_before_it(tmp_path: Path) -> None:
    """SYNC-01: a store whose full read worked under 0003 gets the largest `modified_gmt` it saved; one without a
    full read that worked gets none."""
    folder = tmp_path / "m"
    folder.mkdir()
    for name in ("0001_base.sql", "0002_store.sql", "0003_catalog.sql"):
        shutil.copy(DEFAULT_MIGRATIONS_DIR / name, folder / name)
    with closing(connect(tmp_path / "old.db")) as connection:
        migrate(connection, folder)
        for store_id in (1, 2):
            connection.execute(
                "INSERT INTO store (name, url, code, shape, color, spacing_ms, main_button, created_at) "
                "VALUES (?, ?, ?, 'circle', 'indigo', 150, 'Download', '2026-11-01T00:00:00.000000Z')",
                (f"S{store_id}", f"https://s{store_id}.example", ("GF", "PW")[store_id - 1]),
            )
            seeded = (
                (1, "2026-11-10T08:00:00"),
                (2, "2026-11-12T09:30:00"),
                (3, None),
                (4, "٢٠٢٦-12-31T09:30:00"),  # F7: not ASCII digits: never the watermark
                (5, "2999-01-01T00:00:00"),  # F7: more than a day ahead of the clock: never the watermark
            )
            for wc_id, modified in seeded:
                connection.execute(
                    "INSERT INTO store_product (store_id, wc_id, slug, title, type, status, modified_gmt, "
                    "downloads_json, meta_json, seen_at) VALUES (?, ?, 's', 't', 'simple', 'publish', ?, '[]', '[]', "
                    "'2026-11-12T10:00:00.000000Z')",
                    (store_id, wc_id, modified),
                )
        connection.execute("INSERT INTO sync_state (store_id, last_ok_at) VALUES (1, '2026-11-12T10:00:00.000000Z')")
        connection.execute("INSERT INTO sync_state (store_id) VALUES (2)")
        assert migrate(connection) == [4]
        rows = connection.execute("SELECT store_id, watermark_gmt FROM sync_state ORDER BY store_id").fetchall()
    assert rows == [(1, "2026-11-12T09:30:00"), (2, None)]


def test_the_snapshot_tables_refuse_what_no_snapshot_writes() -> None:
    db = make_db()
    store_id = db.add_store("GF")
    with closing(db.connect()) as connection:
        for bad in (
            ("2026-11-18", "done", 0),  # not a state
            ("2026-11-18", "ok", 4),  # past the three attempts
            ("18-11-2026", "ok", 1),  # not a date
        ):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO snapshot_night (store_id, night, state, attempts) VALUES (?, ?, ?, ?)",
                    (store_id, *bad),
                )
        with pytest.raises(sqlite3.IntegrityError):  # the last night before the first
            connection.execute(
                "INSERT INTO snapshot_state (store_id, wc_id, status, slug, type, downloads_json, meta_json, "
                "variations_json, state_sha256, first_night, last_night) VALUES (?, 1, 'publish', 's', 'simple', "
                "'[]', '[]', '[]', ?, '2026-11-18', '2026-11-17')",
                (store_id, "0" * 64),
            )
        with pytest.raises(sqlite3.IntegrityError):  # watermark not a store date
            connection.execute("INSERT INTO sync_state (store_id, watermark_gmt) VALUES (?, 'yesterday')", (store_id,))
