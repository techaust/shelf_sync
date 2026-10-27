"""BAK-01, SET-05: the Settings > Backup API."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from shelfsync.api.backup_settings import BACKUP_SETTINGS_PATH, BackupSettingsService
from shelfsync.db.connection import connect
from shelfsync.db.daily import DailyBackups, LocalTime, daily_name
from shelfsync.db.migrate import migrate
from shelfsync.db.settings import DEFAULTS, get_setting
from tests.support import ORIGIN, WRITE_HEADERS, Harness, make_harness
from tests.update_support import data_paths

UTC_ZONE = LocalTime(
    to_local=lambda moment: moment.replace(tzinfo=None), to_utc=lambda naive: naive.replace(tzinfo=UTC)
)
NOW = datetime(2026, 3, 10, 14, 0, 0, tzinfo=UTC)
GOOD: dict[str, Any] = {"db_backups_kept": 5, "snapshot_retention_days": 90}
DEFAULT_BODY = {key: DEFAULTS[key] for key in GOOD}


class Rig:
    def __init__(self, tmp_path: Path) -> None:
        self.paths = data_paths(tmp_path)
        setup = connect(self.paths.database)
        migrate(setup)
        setup.close()
        self.daily = DailyBackups(self.paths, lambda: connect(self.paths.database), lambda: NOW, UTC_ZONE)
        self.service = BackupSettingsService(lambda: connect(self.paths.database), self.daily)
        self.harness: Harness = make_harness(backups=self.service)
        self.client: TestClient = self.harness.signed_in_client()

    def stored(self) -> dict[str, Any]:
        connection = connect(self.paths.database)
        try:
            return {key: get_setting(connection, key) for key in GOOD}
        finally:
            connection.close()


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    return Rig(tmp_path)


def put(rig: Rig, body: Any, headers: dict[str, str] | None = None) -> Any:
    return rig.client.put(BACKUP_SETTINGS_PATH, json=body, headers=WRITE_HEADERS if headers is None else headers)


def test_get_before_any_backup_gives_the_defaults_and_the_next_run(rig: Rig) -> None:
    response = rig.client.get(BACKUP_SETTINGS_PATH)
    assert response.status_code == 200
    assert response.json() == {
        **DEFAULT_BODY,
        "last_backup_at": None,
        "last_backup_bytes": None,
        "next_backup_at": "2026-03-10T14:00:00.000000Z",  # nothing yet: due at once
        "daily_count": 0,
    }


def test_get_after_a_backup_names_the_newest_its_size_and_the_next_02_00(rig: Rig) -> None:
    assert rig.daily.run_once()
    body = rig.client.get(BACKUP_SETTINGS_PATH).json()
    newest = rig.paths.backups / daily_name(NOW)
    assert body["last_backup_at"] == "2026-03-10T14:00:00.000000Z"
    assert body["last_backup_bytes"] == newest.stat().st_size > 0
    assert body["next_backup_at"] == "2026-03-11T02:00:00.000000Z"
    assert body["daily_count"] == 1


def test_put_saves_both_and_answers_what_was_saved(rig: Rig) -> None:
    response = put(rig, GOOD)
    assert response.status_code == 200
    assert response.json() == GOOD
    assert rig.stored() == GOOD
    assert rig.client.get(BACKUP_SETTINGS_PATH).json()["db_backups_kept"] == 5


def test_lowering_the_number_kept_prunes_at_once(rig: Rig) -> None:
    for day in range(1, 7):
        (rig.paths.backups / daily_name(datetime(2026, 3, day, 2, 0, 0, tzinfo=UTC))).write_bytes(b"x")
    assert put(rig, {**GOOD, "db_backups_kept": 2}).status_code == 200
    assert len(list(rig.paths.backups.glob("daily-*"))) == 2
    assert put(rig, {**GOOD, "db_backups_kept": 30}).status_code == 200  # raising removes nothing
    assert len(list(rig.paths.backups.glob("daily-*"))) == 2


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("db_backups_kept", 0),
        ("db_backups_kept", 31),
        ("db_backups_kept", -1),
        ("db_backups_kept", True),
        ("db_backups_kept", "7"),
        ("db_backups_kept", 7.0),
        ("db_backups_kept", None),
        ("snapshot_retention_days", 0),
        ("snapshot_retention_days", 366),
        ("snapshot_retention_days", -5),
        ("snapshot_retention_days", True),
        ("snapshot_retention_days", "30"),
        ("snapshot_retention_days", None),
    ],
)
def test_every_field_refuses_what_is_outside_its_limits(rig: Rig, field: str, value: object) -> None:
    response = put(rig, {**GOOD, field: value})
    assert response.status_code == 422
    assert response.json() == {"error": "invalid_request"}
    assert rig.stored() == DEFAULT_BODY


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("db_backups_kept", 1),
        ("db_backups_kept", 30),
        ("snapshot_retention_days", 1),
        ("snapshot_retention_days", 365),
    ],
)
def test_the_limits_themselves_are_accepted(rig: Rig, field: str, value: int) -> None:
    assert put(rig, {**GOOD, field: value}).status_code == 200
    assert rig.stored()[field] == value


@pytest.mark.parametrize("missing", list(GOOD))
def test_every_field_is_required(rig: Rig, missing: str) -> None:
    assert put(rig, {key: value for key, value in GOOD.items() if key != missing}).status_code == 422
    assert rig.stored() == DEFAULT_BODY


def test_unknown_fields_are_refused_the_read_only_ones_included(rig: Rig) -> None:
    assert put(rig, {**GOOD, "extra": 1}).status_code == 422
    assert put(rig, {**GOOD, "daily_count": 3}).status_code == 422
    assert put(rig, {**GOOD, "last_backup_at": "x"}).status_code == 422
    assert rig.stored() == DEFAULT_BODY


@pytest.mark.parametrize("body", [[], "text", 5, None])
def test_a_body_that_is_not_an_object_is_refused(rig: Rig, body: object) -> None:
    assert put(rig, body).status_code == 422


def test_a_save_is_all_or_nothing(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    import shelfsync.api.backup_settings as module

    real = module.set_setting
    calls = {"n": 0}

    def flaky(connection: sqlite3.Connection, key: str, value: Any) -> None:
        calls["n"] += 1
        if calls["n"] == 2:
            raise sqlite3.OperationalError("disk full")
        real(connection, key, value)

    monkeypatch.setattr(module, "set_setting", flaky)
    client = rig.harness.signed_in_client(raise_server_exceptions=False)
    assert client.put(BACKUP_SETTINGS_PATH, json=GOOD, headers=WRITE_HEADERS).status_code == 500
    assert rig.stored() == DEFAULT_BODY


def test_a_stored_value_that_is_not_valid_reads_as_the_default(rig: Rig, caplog: pytest.LogCaptureFixture) -> None:
    connection = connect(rig.paths.database)
    connection.execute("INSERT INTO setting (key, value_json) VALUES ('db_backups_kept', '99')")
    connection.close()
    with caplog.at_level("WARNING", logger="shelfsync.api.settings"):
        assert rig.client.get(BACKUP_SETTINGS_PATH).json()["db_backups_kept"] == 7
    assert "db_backups_kept" in caplog.text


# ---- the guard ----------------------------------------------------------------------------------------------------


def test_without_a_session_both_routes_are_401(rig: Rig) -> None:
    client = rig.harness.client()
    assert client.get(BACKUP_SETTINGS_PATH).status_code == 401
    assert client.put(BACKUP_SETTINGS_PATH, json=GOOD, headers=WRITE_HEADERS).status_code == 401
    assert rig.stored() == DEFAULT_BODY


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Origin": ORIGIN},
        {"X-ShelfSync": "1"},
        {"Origin": "http://evil.example", "X-ShelfSync": "1"},
    ],
)
def test_a_put_needs_the_origin_and_the_csrf_header(rig: Rig, headers: dict[str, str]) -> None:
    assert put(rig, GOOD, headers).status_code == 403
    assert rig.stored() == DEFAULT_BODY


def test_a_wrong_host_is_refused(rig: Rig) -> None:
    assert rig.harness.client(host="evil.example").get(BACKUP_SETTINGS_PATH).status_code == 403


def test_the_route_walk_sees_both_routes(rig: Rig) -> None:
    from tests.test_guard import _api_routes

    assert {("GET", BACKUP_SETTINGS_PATH), ("PUT", BACKUP_SETTINGS_PATH)} <= set(_api_routes(rig.harness.app))


def test_the_default_service_keeps_settings_in_memory_and_runs_no_schedule() -> None:
    harness = make_harness()
    client = harness.signed_in_client()
    assert client.get(BACKUP_SETTINGS_PATH).json() == {
        **DEFAULT_BODY,
        "last_backup_at": None,
        "last_backup_bytes": None,
        "next_backup_at": None,
        "daily_count": 0,
    }
    assert client.put(BACKUP_SETTINGS_PATH, json=GOOD, headers=WRITE_HEADERS).json() == GOOD
    assert client.get(BACKUP_SETTINGS_PATH).json()["db_backups_kept"] == 5


def test_the_app_starts_and_stops_the_scheduler_with_the_server(rig: Rig) -> None:
    started: list[str] = []
    rig.daily.start = lambda: started.append("start")  # type: ignore[method-assign]
    rig.daily.stop = lambda: started.append("stop")  # type: ignore[method-assign]
    with TestClient(rig.harness.app):
        assert started == ["start"]
    assert started == ["start", "stop"]
