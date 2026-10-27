"""LOG-01, SYS-03: no token, ticket or session value is ever written, even with redaction switched off.

With `redact` patched to do nothing, whatever reaches the log file or the process output is exactly what the code
wrote. These values must not be there, which proves they are never logged at all, not only masked.
"""

from pathlib import Path

import pytest

from shelfsync import logs, server
from shelfsync.paths import DataPaths
from shelfsync.platform.notify import FakeNotifier
from shelfsync.platform.secrets import MemorySecretStore
from shelfsync.secure.token import INSTALL_TOKEN_NAME
from tests.store_support import (
    KEY,
    KEY_2,
    SECRET,
    SECRET_2,
    FailingSecretStore,
    html,
    make_store_rig,
    new_store_body,
    wp_error,
)
from tests.support import ORIGIN, WRITE_HEADERS, make_harness
from tests.test_server import RecordingServe


def test_the_whole_sign_in_flow_writes_no_secret_value_anywhere(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """LOG-01: ticket, session and reset, with refusals along the way."""
    monkeypatch.setattr(logs, "redact", lambda text: text)
    handler = logs.configure_logging(tmp_path, retention_days=1)
    secret_values: list[str] = []
    try:
        harness = make_harness(store=MemorySecretStore())
        secret_values.append(harness.token)
        launcher = harness.client()

        # a ticket, a sign-in, and what the page does next
        ticket = harness.ticket(launcher)
        secret_values.append(ticket)
        page = harness.client()
        signed = page.post("/api/session", json={"ticket": ticket}, headers=WRITE_HEADERS)
        assert signed.status_code == 204
        session_id = page.cookies.get("shelfsync_session")
        assert session_id
        secret_values.append(session_id)

        # refusals, which are the requests that get logged
        page.post("/api/session", json={"ticket": ticket}, headers=WRITE_HEADERS)  # replay
        launcher.post("/api/session/ticket", headers={"Authorization": f"Bearer {harness.token}", "Origin": ORIGIN})
        launcher.post("/api/session/ticket", headers={"Authorization": "Bearer wrong-" + harness.token})
        launcher.get("/api/nope", headers={"Cookie": f"shelfsync_session={session_id}x"})
        launcher.get("/api/health", headers={"Host": "evil.example", "Authorization": f"Bearer {harness.token}"})
        page.post(
            "/api/session/reset-token",
            headers={"Origin": "http://evil.example", "X-ShelfSync": "1", "Cookie": f"shelfsync_session={session_id}"},
        )

        # the reset itself
        assert page.post("/api/session/reset-token", headers=WRITE_HEADERS).status_code == 204
        secret_values.append(harness.token)  # the new token
        assert (
            harness.client()
            .post("/api/session/ticket", headers={"Authorization": f"Bearer {harness.token}"})
            .status_code
            == 200
        )
        handler.flush()
    finally:
        logs.remove_logging(handler)

    log_text = (tmp_path / logs.LOG_FILE_NAME).read_text(encoding="utf-8")
    assert "refused by the" in log_text  # logging was on and did record the refusals
    captured = capfd.readouterr()
    everything = log_text + captured.out + captured.err
    assert len({value for value in secret_values}) == 4  # old token, ticket, session, new token
    for value in secret_values:
        assert value not in everything


def test_the_start_up_flow_writes_no_token_with_redaction_off(
    data_paths: DataPaths, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """LOG-01: a full start-up logs nothing that holds the token."""
    monkeypatch.setattr(logs, "redact", lambda text: text)
    store = MemorySecretStore()
    assert server.run(data_paths, FakeNotifier(), RecordingServe(), 0.0, store) == server.EXIT_OK
    token = store.get(INSTALL_TOKEN_NAME)
    assert token
    assert token not in (data_paths.logs / logs.LOG_FILE_NAME).read_text(encoding="utf-8")
    captured = capfd.readouterr()
    assert token not in captured.out + captured.err


def test_the_store_flows_write_no_key_or_secret_anywhere_even_with_redaction_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """LOG-01, SET-01: adding, testing (a good store, a refusing store whose answer echoes the keys, a blocked one),
    replacing, failing to save, and removing; and the start-up read. The values never reach the log or the output."""
    monkeypatch.setattr(logs, "redact", lambda text: text)
    handler = logs.configure_logging(tmp_path, retention_days=1)
    secrets = FailingSecretStore()
    values = [KEY, SECRET, KEY_2, SECRET_2]
    try:
        rig = make_store_rig(secrets)
        client = rig.harness.signed_in_client()
        body = new_store_body()
        assert client.post("/api/stores", headers=WRITE_HEADERS, json=body).status_code == 201
        assert client.post("/api/stores/1/test", headers=WRITE_HEADERS).json()["ok"] is True
        # a store that answers with the keys written into its error text (a plugin that echoes the Authorization header)
        rig.woo.status = lambda request: wp_error(
            401, f"woocommerce_rest_cannot_view {KEY}:{SECRET} {request.headers['Authorization']}"
        )
        assert client.post("/api/stores/1/test", headers=WRITE_HEADERS).json()["reason"] == "keys_refused"
        rig.woo.status = html(403)
        assert client.post("/api/stores/1/test", headers=WRITE_HEADERS).json()["reason"] == "blocked"
        rig.woo.status = None
        # refused and failed requests, which are the ones that get logged
        assert (
            client.post("/api/stores", headers=WRITE_HEADERS, json=new_store_body(consumer_key="ck_nope")).status_code
            == 422
        )
        assert client.post("/api/stores", headers=WRITE_HEADERS, json=body).status_code == 409
        secrets.fail_set_on = secrets.sets + 2
        replace = {"consumer_key": KEY_2, "consumer_secret": SECRET_2}
        assert client.put("/api/stores/1/keys", headers=WRITE_HEADERS, json=replace).status_code == 503
        secrets.fail_set_on = None
        assert client.put("/api/stores/1/keys", headers=WRITE_HEADERS, json=replace).status_code == 204
        secrets.fail_get = True
        assert client.post("/api/stores/1/test", headers=WRITE_HEADERS).status_code == 409
        rig.service.register_secrets()
        secrets.fail_get = False
        assert client.delete("/api/stores/1", headers=WRITE_HEADERS).status_code == 204
        handler.flush()
    finally:
        logs.remove_logging(handler)

    log_text = (tmp_path / logs.LOG_FILE_NAME).read_text(encoding="utf-8")
    assert "Store SA read test" in log_text  # logging was on and did record the tests
    captured = capfd.readouterr()
    everything = log_text + captured.out + captured.err
    for value in values:
        assert value not in everything
        assert value[3:] not in everything
    assert "store-a.example" not in everything  # a store is named by its code, never its address
    assert "Just a moment" not in everything and "woocommerce_rest_cannot_view" not in everything
