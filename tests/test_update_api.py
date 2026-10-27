"""SET-04, SYS-03: the Updates API and the github-token setting, behind the deny-by-default guard."""

import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from shelfsync.platform.secrets import MemorySecretStore
from shelfsync.secure.redact import redact
from shelfsync.update.service import GITHUB_TOKEN_ENTRY, UpdateService
from tests.support import ORIGIN, WRITE_HEADERS, Harness, make_harness
from tests.test_update_service import Rig, make_rig, rollback_rig
from tests.update_support import FakeGitHub

TOKEN = "github_pat_" + "Mn5Pq6Rs7T" * 4
UPDATE_ROUTES = [
    ("GET", "/api/updates"),
    ("POST", "/api/updates/check"),
    ("POST", "/api/updates/install"),
    ("POST", "/api/updates/rollback"),
    ("GET", "/api/secrets/github-token"),
    ("PUT", "/api/secrets/github-token"),
    ("DELETE", "/api/secrets/github-token"),
]


def development_harness() -> tuple[Harness, MemorySecretStore, FakeGitHub]:
    secrets = MemorySecretStore()
    service = UpdateService.development(secrets)
    return make_harness(updates=service), secrets, FakeGitHub()


def with_quit(harness: Harness, rig: Rig) -> Harness:
    """What the launcher does: publish `request_quit` on the app's state (the rig counts its calls)."""
    harness.app.state.request_quit = lambda: rig.quits.append(1) is None
    return harness


def real_harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Harness, Rig]:
    rig = make_rig(tmp_path, monkeypatch)
    return with_quit(make_harness(updates=rig.service), rig), rig


# ---- the guard ------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("method", "path"), UPDATE_ROUTES)
def test_every_updates_route_needs_a_session(method: str, path: str) -> None:
    harness, _, _ = development_harness()
    headers = {} if method == "GET" else WRITE_HEADERS
    response = harness.client().request(method, path, headers=headers)
    assert response.status_code == 401 and response.json() == {"error": "signed_out"}


@pytest.mark.parametrize(("method", "path"), [r for r in UPDATE_ROUTES if r[0] != "GET"])
def test_a_write_needs_shelfsyncs_origin_and_the_csrf_header(method: str, path: str) -> None:
    harness, secrets, _ = development_harness()
    client = harness.signed_in_client()
    for headers in (
        {},
        {"X-ShelfSync": "1"},
        {"Origin": ORIGIN},
        {"Origin": "http://evil.example", "X-ShelfSync": "1"},
    ):
        response = client.request(method, path, headers=headers, json={"value": TOKEN})
        assert response.status_code == 403
    assert secrets.get(GITHUB_TOKEN_ENTRY) is None  # a refused request changed nothing


def test_the_routes_are_in_the_route_table() -> None:
    from tests.test_guard import _api_routes

    harness, _, _ = development_harness()
    found = set(_api_routes(harness.app))
    assert set(UPDATE_ROUTES) <= found


def test_the_schema_describes_the_new_routes_with_typed_models() -> None:
    harness, _, _ = development_harness()
    schema = harness.app.openapi()
    assert {
        "/api/updates",
        "/api/updates/check",
        "/api/updates/install",
        "/api/updates/rollback",
        "/api/secrets/github-token",
    } <= set(schema["paths"])
    assert "UpdatesResponse" in schema["components"]["schemas"]
    body = schema["components"]["schemas"]["GithubTokenStatus"]
    assert set(body["properties"]) == {"set", "expires_at"}  # no field that could hold the token


# ---- the picture ----------------------------------------------------------------------------------------------------


def test_a_development_copy_says_so_and_refuses_the_actions() -> None:
    harness, _, _ = development_harness()
    client = harness.signed_in_client()
    body = client.get("/api/updates").json()
    assert body["development"] is True and body["can_roll_back"] is False and body["available"] is None
    assert body["token"] == {"set": False, "expires_at": None, "notice": False}
    assert set(body) == {
        "development", "key_available", "installed", "previous", "can_roll_back", "database_changed", "backup_at",
        "backup_available", "checking", "busy", "last_check", "available", "token", "last_result",
    }  # fmt: skip
    for path in ("check", "install", "rollback"):
        response = client.post(f"/api/updates/{path}", headers=WRITE_HEADERS)
        assert (response.status_code, response.json()) == (409, {"error": "development_build"})


def test_a_check_then_the_picture_then_an_install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    harness, rig = real_harness(tmp_path, monkeypatch)
    client = harness.signed_in_client()
    assert client.post("/api/updates/check", headers=WRITE_HEADERS).status_code == 202
    body = client.get("/api/updates").json()
    assert body["available"] == {"version": "0.0.2", "ready": True}
    assert body["last_check"]["outcome"] == "ok" and body["installed"] == "0.0.1" and body["key_available"] is True
    assert client.post("/api/updates/check", headers=WRITE_HEADERS).json() == {"error": "too_soon"}
    assert client.post("/api/updates/install", headers=WRITE_HEADERS).json() == {"accepted": True}
    assert client.get("/api/updates").json()["busy"] is True
    again = client.post("/api/updates/install", headers=WRITE_HEADERS)
    assert (again.status_code, again.json()) == (409, {"error": "busy"})
    assert len(rig.procs.spawned) == 1


def test_a_check_within_a_minute_of_the_last_is_429(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    harness, rig = real_harness(tmp_path, monkeypatch)
    client = harness.signed_in_client()
    client.post("/api/updates/check", headers=WRITE_HEADERS)
    response = client.post("/api/updates/check", headers=WRITE_HEADERS)
    assert response.status_code == 429
    rig.clock[0] += 61
    assert client.post("/api/updates/check", headers=WRITE_HEADERS).status_code == 202


def test_an_install_with_nothing_downloaded_is_409_with_its_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness, _ = real_harness(tmp_path, monkeypatch)
    response = harness.signed_in_client().post("/api/updates/install", headers=WRITE_HEADERS)
    assert (response.status_code, response.json()) == (409, {"error": "nothing_to_install"})


def test_a_rollback_after_a_database_change_is_422_until_confirmed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = rollback_rig(tmp_path, monkeypatch, changed_database=True)
    client = with_quit(make_harness(updates=rig.service), rig).signed_in_client()
    body = client.get("/api/updates").json()
    assert body["can_roll_back"] and body["database_changed"] and body["backup_at"] and body["previous"] == "0.0.1"
    for sent in (None, {}, {"confirm_data_loss": False}):
        response = client.post("/api/updates/rollback", headers=WRITE_HEADERS, json=sent)
        assert (response.status_code, response.json()) == (422, {"error": "confirm_required"})
    assert rig.procs.spawned == []
    accepted = client.post("/api/updates/rollback", headers=WRITE_HEADERS, json={"confirm_data_loss": True})
    assert (accepted.status_code, accepted.json()) == (202, {"accepted": True})


def test_a_rollback_with_no_database_change_needs_no_body(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = rollback_rig(tmp_path, monkeypatch, changed_database=False)
    client = with_quit(make_harness(updates=rig.service), rig).signed_in_client()
    assert client.post("/api/updates/rollback", headers=WRITE_HEADERS).status_code == 202


@pytest.mark.parametrize("sent", [{"confirm_data_loss": "maybe"}, {"confirm_data_loss": True, "extra": 1}, [1], "yes"])
def test_a_malformed_rollback_body_is_a_fixed_422_that_echoes_nothing(sent: object) -> None:
    harness, _, _ = development_harness()
    response = harness.signed_in_client().post("/api/updates/rollback", headers=WRITE_HEADERS, json=sent)
    assert (response.status_code, response.json()) == (422, {"error": "invalid_request"})


# ---- the token -----------------------------------------------------------------------------------------------------


def everything_said(client: TestClient, responses: list[object]) -> str:
    return " ".join(f"{r.status_code} {r.text} {dict(r.headers)}" for r in responses)  # type: ignore[attr-defined]


def test_the_token_is_write_only_and_never_in_any_response() -> None:
    harness, secrets, _ = development_harness()
    client = harness.signed_in_client()
    put = client.put("/api/secrets/github-token", headers=WRITE_HEADERS, json={"value": TOKEN})
    assert put.status_code == 204 and put.content == b""
    assert secrets.get(GITHUB_TOKEN_ENTRY) == TOKEN
    seen = [put]
    seen.append(client.get("/api/secrets/github-token"))
    assert seen[-1].json() == {"set": True, "expires_at": None}
    seen.append(client.get("/api/updates"))
    assert seen[-1].json()["token"]["set"] is True
    seen.append(client.put("/api/secrets/github-token", headers=WRITE_HEADERS, json={"value": TOKEN[:-5]}))  # refused
    seen.append(client.put("/api/secrets/github-token", headers=WRITE_HEADERS, json={"nope": TOKEN}))
    seen.append(client.put("/api/secrets/github-token", headers=WRITE_HEADERS, content=TOKEN))  # not JSON
    seen.append(client.post("/api/updates/rollback", headers=WRITE_HEADERS, json={"confirm_data_loss": TOKEN}))
    delete = client.delete("/api/secrets/github-token", headers=WRITE_HEADERS)
    seen.append(delete)
    assert delete.status_code == 204 and secrets.get(GITHUB_TOKEN_ENTRY) is None
    seen.append(client.get("/api/secrets/github-token"))
    assert seen[-1].json() == {"set": False, "expires_at": None}
    said = everything_said(client, seen)
    assert TOKEN not in said and TOKEN[11:] not in said and "github_pat_" not in said


@pytest.mark.parametrize(
    "value",
    [
        "",
        "ghp_" + "a" * 36,
        "github_pat_short",
        "github_pat_" + "a" * 300,
        "github_pat_" + "a" * 30 + "!",
        None,
        5,
        ["github_pat_" + "a" * 30],
    ],
)
def test_a_value_that_is_not_a_fine_grained_token_is_a_fixed_422(value: object) -> None:
    harness, secrets, _ = development_harness()
    response = harness.signed_in_client().put("/api/secrets/github-token", headers=WRITE_HEADERS, json={"value": value})
    assert (response.status_code, response.json()) == (422, {"error": "invalid_request"})
    assert secrets.get(GITHUB_TOKEN_ENTRY) is None


def test_a_token_set_through_the_api_is_registered_with_the_redaction_and_not_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    harness, _, _ = development_harness()
    caplog.set_level(logging.DEBUG)
    client = harness.signed_in_client()
    client.put("/api/secrets/github-token", headers=WRITE_HEADERS, json={"value": TOKEN})
    client.put("/api/secrets/github-token", headers=WRITE_HEADERS, json={"value": TOKEN + "!"})
    assert TOKEN not in caplog.text
    assert TOKEN not in redact(f"later: {TOKEN}")


def test_a_failing_secret_store_is_a_500_that_says_nothing(caplog: pytest.LogCaptureFixture) -> None:
    from shelfsync.platform.secrets import SecretStoreError

    class Broken(MemorySecretStore):
        def set(self, name: str, value: str) -> None:
            raise SecretStoreError("Credential Manager write failed (OSError)")

    service = UpdateService.development(Broken())
    harness = make_harness(updates=service)
    client = harness.signed_in_client(raise_server_exceptions=False)
    response = client.put("/api/secrets/github-token", headers=WRITE_HEADERS, json={"value": TOKEN})
    assert (response.status_code, response.json()) == (500, {"error": "internal"})
    assert TOKEN not in response.text and TOKEN not in caplog.text


def test_the_app_starts_and_stops_the_service_with_the_server(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    service = UpdateService.development()
    monkeypatch.setattr(service, "start", lambda: events.append("start"))
    monkeypatch.setattr(service, "stop", lambda: events.append("stop"))
    harness = make_harness(updates=service)
    with TestClient(harness.app, base_url=f"http://127.0.0.1:{harness.port}"):
        assert events == ["start"]
    assert events == ["start", "stop"]


def test_the_default_service_of_an_app_is_the_development_one_and_makes_no_call() -> None:
    harness = make_harness()
    assert harness.app.state.updates.is_development


def test_the_quit_function_is_looked_up_when_needed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`request_quit` is published on app.state after the app is built (the launcher does it); the service finds it."""
    rig = make_rig(tmp_path, monkeypatch, quit_result=None)
    harness = make_harness(updates=rig.service)
    client = harness.signed_in_client()
    client.post("/api/updates/check", headers=WRITE_HEADERS)
    assert client.post("/api/updates/install", headers=WRITE_HEADERS).json() == {"error": "cannot_restart"}  # none yet
    calls: list[int] = []
    harness.app.state.request_quit = lambda: calls.append(1) is None
    assert client.post("/api/updates/install", headers=WRITE_HEADERS).status_code == 202
    assert calls == [1]
