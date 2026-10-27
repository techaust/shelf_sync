"""SET-06, LOG-01: the Settings > App API."""

import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from shelfsync.api.app_settings import APP_SETTINGS_PATH, AppSettingsService, AppSettingsValues
from shelfsync.db.connection import connect
from shelfsync.db.migrate import migrate
from shelfsync.db.settings import DEFAULTS, get_all_settings
from shelfsync.logs import configure_logging, remove_logging
from shelfsync.platform.autostart import AutostartError, FakeRunKey
from shelfsync.ports import DEFAULT_PORT
from tests.support import ORIGIN, WRITE_HEADERS, Harness, make_harness

GOOD: dict[str, Any] = {
    "port": 47616,
    "theme": "dark",
    "start_with_windows": False,
    "notifications": False,
    "log_retention_days": 14,
}


class Rig:
    def __init__(self, tmp_path: Path, installed: bool = True, run_key: Any = None) -> None:
        self.database = tmp_path / "shelfsync.db"
        setup = connect(self.database)
        migrate(setup)
        setup.close()
        self.run_key = run_key if run_key is not None else FakeRunKey()
        logs = tmp_path / "logs"
        logs.mkdir()
        self.logs = logs
        self.handler = configure_logging(logs, 30)
        self.service = AppSettingsService(
            lambda: connect(self.database), DEFAULT_PORT, self.handler, self.run_key, lambda: installed
        )
        self.harness: Harness = make_harness(app_settings=self.service)
        self.client: TestClient = self.harness.signed_in_client()

    def close(self) -> None:
        remove_logging(self.handler)

    def stored(self) -> dict[str, Any]:
        connection = connect(self.database)
        try:
            return get_all_settings(connection)
        finally:
            connection.close()


@pytest.fixture
def rig(tmp_path: Path) -> Any:
    made = Rig(tmp_path)
    yield made
    made.close()


def put(rig: Rig, body: Any, headers: dict[str, str] | None = None) -> Any:
    return rig.client.put(APP_SETTINGS_PATH, json=body, headers=WRITE_HEADERS if headers is None else headers)


def test_get_gives_the_defaults_and_whether_this_is_the_installed_copy(rig: Rig) -> None:
    """SET-06."""
    response = rig.client.get(APP_SETTINGS_PATH)
    assert response.status_code == 200
    assert response.json() == {**DEFAULTS, "installed": True}


def test_put_saves_all_five_and_says_what_it_did(rig: Rig) -> None:
    """SET-06: returns what was saved, `restart_needed` (the port changed) and the Run value's result."""
    response = put(rig, GOOD)
    assert response.status_code == 200
    assert response.json() == {**GOOD, "restart_needed": True, "start_with_windows_result": "applied"}
    assert rig.stored() == GOOD
    assert rig.client.get(APP_SETTINGS_PATH).json() == {**GOOD, "installed": True}


def test_the_same_port_needs_no_restart(rig: Rig) -> None:
    """SET-06."""
    body = {**GOOD, "port": DEFAULTS["port"]}
    assert put(rig, body).json()["restart_needed"] is False


def test_start_with_windows_writes_and_removes_the_run_value_now(rig: Rig) -> None:
    """SET-06, SYS-04: an installed copy applies it at once."""
    assert put(rig, {**GOOD, "start_with_windows": True}).status_code == 200
    assert "ShelfSync" in rig.run_key.values
    assert rig.run_key.values["ShelfSync"].endswith("--background")
    assert put(rig, {**GOOD, "start_with_windows": False}).status_code == 200
    assert "ShelfSync" not in rig.run_key.values


def test_a_copy_that_isnt_installed_never_touches_the_run_key(tmp_path: Path) -> None:
    """SET-06, SYS-04."""
    rig = Rig(tmp_path, installed=False)
    try:
        response = put(rig, {**GOOD, "start_with_windows": True})
        assert response.status_code == 200
        assert response.json()["start_with_windows_result"] == "not_installed"
        assert rig.run_key.values == {}
        assert rig.client.get(APP_SETTINGS_PATH).json()["installed"] is False
    finally:
        rig.close()


class BrokenRunKey(FakeRunKey):
    def get(self, name: str) -> str | None:
        raise AutostartError("Reading the Run key failed (PermissionError)")


def test_a_run_key_failure_is_reported_not_raised_and_the_rest_is_saved(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """SET-06: 200 with `start_with_windows_result: "failed"`, never a 500."""
    rig = Rig(tmp_path, run_key=BrokenRunKey())
    try:
        with caplog.at_level(logging.WARNING, logger="shelfsync.api.settings"):
            response = put(rig, GOOD)
        assert response.status_code == 200
        assert response.json()["start_with_windows_result"] == "failed"
        assert rig.stored() == GOOD
        assert "couldn't be applied" in caplog.text
    finally:
        rig.close()


def test_the_log_retention_reaches_the_running_handler_and_prunes(rig: Rig) -> None:
    """LOG-01: backupCount follows the setting, and a file past it goes at once."""
    old = rig.logs / "shelfsync.log.2000-01-01"
    old.write_text("x", encoding="utf-8")
    assert put(rig, {**GOOD, "log_retention_days": 7}).status_code == 200
    assert rig.handler.backupCount == 7
    assert not old.exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("port", 47614),
        ("port", 47625),
        ("port", 0),
        ("port", True),
        ("port", "47616"),
        ("port", 47616.0),
        ("port", None),
        ("theme", "blue"),
        ("theme", "System"),
        ("theme", 1),
        ("start_with_windows", "yes"),
        ("start_with_windows", 1),
        ("notifications", 0),
        ("notifications", None),
        ("log_retention_days", 0),
        ("log_retention_days", 366),
        ("log_retention_days", -1),
        ("log_retention_days", "30"),
        ("log_retention_days", True),
    ],
)
def test_every_field_refuses_what_is_outside_its_limits(rig: Rig, field: str, value: object) -> None:
    """SET-06: the fixed 422, nothing saved, and the value is not echoed."""
    response = put(rig, {**GOOD, field: value})
    assert response.status_code == 422
    assert response.json() == {"error": "invalid_request"}
    assert rig.stored() == dict(DEFAULTS)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("port", 47615),
        ("port", 47624),
        ("theme", "system"),
        ("theme", "light"),
        ("log_retention_days", 1),
        ("log_retention_days", 365),
    ],
)
def test_the_limits_themselves_are_accepted(rig: Rig, field: str, value: object) -> None:
    """SET-06."""
    assert put(rig, {**GOOD, field: value}).status_code == 200


@pytest.mark.parametrize("missing", list(GOOD))
def test_every_field_is_required(rig: Rig, missing: str) -> None:
    """SET-06."""
    body = {key: value for key, value in GOOD.items() if key != missing}
    assert put(rig, body).status_code == 422
    assert rig.stored() == dict(DEFAULTS)


def test_unknown_fields_are_refused_installed_included(rig: Rig) -> None:
    """SET-06: `installed` is read-only."""
    assert put(rig, {**GOOD, "extra": 1}).status_code == 422
    assert put(rig, {**GOOD, "installed": True}).status_code == 422
    assert rig.stored() == dict(DEFAULTS)


@pytest.mark.parametrize("body", [[], "text", 5, None])
def test_a_body_that_is_not_an_object_is_refused(rig: Rig, body: object) -> None:
    """SET-06."""
    assert put(rig, body).status_code == 422


def test_a_save_is_all_or_nothing(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    """SET-06: one transaction: a failure part-way leaves the old values."""
    import shelfsync.api.app_settings as module

    real = module.set_setting
    calls = {"n": 0}

    def flaky(connection: sqlite3.Connection, key: str, value: Any) -> None:
        calls["n"] += 1
        if calls["n"] == 3:
            raise sqlite3.OperationalError("disk full")
        real(connection, key, value)

    monkeypatch.setattr(module, "set_setting", flaky)
    client = rig.harness.signed_in_client(raise_server_exceptions=False)
    assert client.put(APP_SETTINGS_PATH, json=GOOD, headers=WRITE_HEADERS).status_code == 500
    assert rig.stored() == dict(DEFAULTS)


# ---- the guard ----------------------------------------------------------------------------------------------------


def test_without_a_session_both_routes_are_401(rig: Rig) -> None:
    """SYS-03."""
    client = rig.harness.client()
    assert client.get(APP_SETTINGS_PATH).status_code == 401
    assert client.put(APP_SETTINGS_PATH, json=GOOD, headers=WRITE_HEADERS).status_code == 401
    assert rig.stored() == dict(DEFAULTS)


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Origin": ORIGIN},
        {"X-ShelfSync": "1"},
        {"Origin": "http://evil.example", "X-ShelfSync": "1"},
        {"Origin": ORIGIN, "X-ShelfSync": "true"},
    ],
)
def test_a_put_needs_the_origin_and_the_csrf_header(rig: Rig, headers: dict[str, str]) -> None:
    """SYS-03: a signed-in PUT without both is 403 and saves nothing."""
    assert put(rig, GOOD, headers).status_code == 403
    assert rig.stored() == dict(DEFAULTS)


def test_a_wrong_host_is_refused(rig: Rig) -> None:
    """SYS-03."""
    client = rig.harness.client(host="evil.example")
    assert client.get(APP_SETTINGS_PATH).status_code == 403


def test_the_default_service_keeps_settings_in_memory_and_never_the_real_run_key() -> None:
    """SET-06: what `create_app` uses when no service is passed."""
    client = make_harness().signed_in_client()
    saved = client.put(APP_SETTINGS_PATH, json=GOOD, headers=WRITE_HEADERS).json()
    assert saved["start_with_windows_result"] == "not_installed"
    assert client.get(APP_SETTINGS_PATH).json() == {**GOOD, "installed": False}


# ---- review fixes ---------------------------------------------------------------------------------------------------


def test_restart_needed_compares_with_the_port_the_server_is_bound_to(rig: Rig) -> None:
    """SET-06: bound to 47615; saving 47616 needs a restart, going back doesn't, a theme-only save keeps it."""
    assert put(rig, {**GOOD, "port": 47616}).json()["restart_needed"] is True
    assert put(rig, {**GOOD, "port": 47615}).json()["restart_needed"] is False
    assert put(rig, {**GOOD, "port": 47616}).json()["restart_needed"] is True
    assert put(rig, {**GOOD, "port": 47616, "theme": "light"}).json()["restart_needed"] is True


def test_the_default_service_uses_the_port_create_app_gets() -> None:
    """SET-06."""
    harness = make_harness()
    client = harness.signed_in_client()
    same = client.put(APP_SETTINGS_PATH, json={**GOOD, "port": harness.port}, headers=WRITE_HEADERS)
    assert same.json()["restart_needed"] is False
    other = client.put(APP_SETTINGS_PATH, json={**GOOD, "port": harness.port + 1}, headers=WRITE_HEADERS)
    assert other.json()["restart_needed"] is True


class CountingRunKey(FakeRunKey):
    def __init__(self) -> None:
        super().__init__()
        self.gets = 0

    def get(self, name: str) -> str | None:
        self.gets += 1
        return super().get(name)


def test_the_run_key_is_touched_once_per_start_and_then_only_when_it_changes(tmp_path: Path) -> None:
    """SET-06: a theme-only save leaves the Run key alone (and still says "applied")."""
    key = CountingRunKey()
    rig = Rig(tmp_path, run_key=key)
    try:
        assert put(rig, {**GOOD, "start_with_windows": True}).json()["start_with_windows_result"] == "applied"
        assert key.gets == 1
        again = put(rig, {**GOOD, "start_with_windows": True, "theme": "light"})
        assert again.json()["start_with_windows_result"] == "applied"
        assert key.gets == 1
        put(rig, {**GOOD, "start_with_windows": False})
        assert key.gets == 2
    finally:
        rig.close()


def test_a_failed_run_key_is_tried_again_at_the_next_save(tmp_path: Path) -> None:
    """SET-06."""
    rig = Rig(tmp_path, run_key=BrokenRunKey())
    try:
        assert put(rig, GOOD).json()["start_with_windows_result"] == "failed"
        assert put(rig, GOOD).json()["start_with_windows_result"] == "failed"
    finally:
        rig.close()


class SwitchableRunKey(FakeRunKey):
    """Works until `broken` is set, then refuses like a locked registry."""

    broken = False

    def get(self, name: str) -> str | None:
        if self.broken:
            raise AutostartError("Reading the Run key failed (PermissionError)")
        return super().get(name)


def test_a_failure_after_an_earlier_success_is_tried_again_at_the_next_save(tmp_path: Path) -> None:
    """SET-06: once a save failed, an unchanged setting is applied again, not reported as applied."""
    key = SwitchableRunKey()
    rig = Rig(tmp_path, run_key=key)
    try:
        assert put(rig, {**GOOD, "start_with_windows": True}).json()["start_with_windows_result"] == "applied"
        key.broken = True
        assert put(rig, GOOD).json()["start_with_windows_result"] == "failed"
        key.broken = False
        assert put(rig, GOOD).json()["start_with_windows_result"] == "applied"
        assert key.get("ShelfSync") is None  # the retry removed the value the failed save left behind
    finally:
        rig.close()


def test_the_log_retention_is_applied_only_when_it_changes(rig: Rig) -> None:
    """LOG-01: a save with the same retention doesn't prune."""
    assert put(rig, {**GOOD, "log_retention_days": 30}).status_code == 200  # same as the handler's 30
    old = rig.logs / "shelfsync.log.2000-01-01"
    old.write_text("x", encoding="utf-8")
    assert put(rig, {**GOOD, "log_retention_days": 30, "theme": "light"}).status_code == 200
    assert old.exists()
    assert put(rig, {**GOOD, "log_retention_days": 29}).status_code == 200
    assert not old.exists()


def test_get_falls_back_to_the_default_on_a_stored_value_that_is_not_valid(
    rig: Rig, caplog: pytest.LogCaptureFixture
) -> None:
    """SET-06: a hand-edited database never makes GET a 500; the warning names the key only."""
    connection = connect(rig.database)
    connection.execute("INSERT INTO setting (key, value_json) VALUES ('log_retention_days', '9999')")
    connection.execute("INSERT INTO setting (key, value_json) VALUES ('theme', '\"purple\"')")
    connection.execute("INSERT INTO setting (key, value_json) VALUES ('notifications', '{bad')")
    connection.close()
    with caplog.at_level(logging.WARNING, logger="shelfsync.api.settings"):
        response = rig.client.get(APP_SETTINGS_PATH)
    assert response.status_code == 200
    body = response.json()
    assert body["log_retention_days"] == DEFAULTS["log_retention_days"]
    assert body["theme"] == DEFAULTS["theme"]
    assert body["notifications"] == DEFAULTS["notifications"]
    assert "'log_retention_days'" in caplog.text
    assert "9999" not in caplog.text
    assert "purple" not in caplog.text


def test_two_saves_at_once_are_applied_in_the_order_they_commit(tmp_path: Path) -> None:
    """SET-06: the whole save is one critical section."""
    state = {"inside": 0, "overlap": False}

    class SlowRunKey(FakeRunKey):
        def get(self, name: str) -> str | None:
            state["inside"] += 1
            state["overlap"] = state["overlap"] or state["inside"] > 1
            threading.Event().wait(0.05)
            try:
                return super().get(name)
            finally:
                state["inside"] -= 1

    rig = Rig(tmp_path, run_key=SlowRunKey())
    try:
        threads = [
            threading.Thread(target=rig.service.save, args=(AppSettingsValues(**{**GOOD, "start_with_windows": flag}),))
            for flag in (True, False)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert state["overlap"] is False
        assert ("ShelfSync" in rig.run_key.values) is rig.stored()["start_with_windows"]
    finally:
        rig.close()
