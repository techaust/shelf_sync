"""SET-01, ERR-01: the m2.1 early-check fixes. A busy slot per store (test, edit of the address or keys, key
replacement and removal can't overlap), the 60-second limit on a whole read test, the HTTP loggers held at WARNING, id
limits, the host-change order (old keys out before the new address goes in), and the smaller hardening items."""

import gc
import logging
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path

import httpx
import pytest

from shelfsync import logs, uninstall
from shelfsync.apply.woocommerce import MAX_BODY_BYTES, WooClient
from shelfsync.db.connection import connect
from shelfsync.db.migrate import migrate
from shelfsync.db.stores import update_store
from shelfsync.paths import DataPaths
from shelfsync.platform.secrets import MemorySecretStore
from shelfsync.secure.credentials import StoreCredentials
from shelfsync.secure.redact import MASK, redact
from shelfsync.store_service import StoreError
from tests.store_support import (
    KEY,
    KEY_2,
    OTHER_URL,
    SECRET,
    SECRET_2,
    STORE_URL,
    SYSTEM_STATUS,
    FailingSecretStore,
    FakeWoo,
    StoreRig,
    make_store_rig,
    new_store_body,
    system_status,
)
from tests.support import WRITE_HEADERS
from tests.test_uninstall import make_data

NEW_KEYS = {"consumer_key": KEY_2, "consumer_secret": SECRET_2}


def add_store(rig: StoreRig, **changes: object) -> None:
    client = rig.harness.signed_in_client()
    assert client.post("/api/stores", headers=WRITE_HEADERS, json=new_store_body(**changes)).status_code == 201


def busy(call: object) -> bool:
    """True if the call was refused with 409 busy."""
    try:
        call()  # type: ignore[operator]
    except StoreError as refused:
        return (refused.status, refused.code) == (409, "busy")
    return False


# ---- R1: one thing at a time per store ------------------------------------------------------------------------------


def test_while_a_test_runs_every_edit_of_the_address_or_keys_and_every_removal_is_busy() -> None:
    rig = make_store_rig()
    add_store(rig)
    seen: list[object] = []

    def during(request: httpx.Request) -> httpx.Response:
        service = rig.service
        if not seen:
            seen.append("started")
            seen.append(busy(lambda: service.test(1)))
            seen.append(busy(lambda: service.update(1, {"url": STORE_URL + "/shop"}, None)))
            seen.append(busy(lambda: service.update(1, {"url": OTHER_URL}, (KEY_2, SECRET_2))))
            seen.append(busy(lambda: service.update(1, {}, (KEY_2, SECRET_2))))
            seen.append(busy(lambda: service.set_keys(1, KEY_2, SECRET_2)))
            seen.append(busy(lambda: service.delete(1)))
            service.update(1, {"name": "Renamed"}, None)  # a rename touches neither: it goes through
        return system_status()

    rig.woo.status = during
    assert rig.service.test(1).outcome.ok
    assert seen == ["started", True, True, True, True, True, True]
    assert rig.service.get(1).row.name == "Renamed"
    assert rig.secrets.get("store-1-key") == KEY  # nothing the refused calls asked for happened
    rig.service.update(1, {"url": STORE_URL + "/shop"}, None)  # and the slot is free again afterwards


def test_the_slot_is_taken_before_anything_is_read_and_is_free_after_a_refusal() -> None:
    rig = make_store_rig()
    add_store(rig)
    rig.service._claim(1)
    with pytest.raises(StoreError) as refused:
        rig.service.test(1)
    assert (refused.value.status, refused.value.code) == (409, "busy")
    assert rig.woo.requests == []  # no keys were read, nothing was sent
    rig.service._release(1)
    with pytest.raises(StoreError) as missing:
        rig.service.test(99)
    assert missing.value.code == "not_found"
    for name in ("store-1-key", "store-1-secret"):
        rig.secrets.delete(name)
    with pytest.raises(StoreError) as no_keys:
        rig.service.test(1)
    assert no_keys.value.code == "keys_missing"
    rig.service._claim(1)  # a refusal of any kind released the slot, so it can be taken again
    rig.service._release(1)


def test_an_address_changed_under_a_running_test_leaves_the_result_unsaved() -> None:
    rig = make_store_rig()
    add_store(rig)

    def moved_meanwhile(request: httpx.Request) -> httpx.Response:
        with closing(rig.service._open()) as connection:  # forced through the repository, past the slot
            update_store(connection, 1, {"url": "https://store-moved.example"})
        return system_status()

    rig.woo.status = moved_meanwhile
    assert rig.service.test(1).outcome.ok  # the test itself ran
    row = rig.service.get(1).row
    assert row.url == "https://store-moved.example"
    assert (row.health, row.tested_at, row.wc_version) == ("unknown", None, None)  # but its result was not kept


# ---- R2: the 60-second limit on the whole test ----------------------------------------------------------------------


def test_a_test_that_hangs_answers_timeout_at_the_limit_and_keeps_the_slot_until_the_worker_ends() -> None:
    rig = make_store_rig()
    add_store(rig, spacing_ms=50)
    service = rig.service
    service._monotonic, service._sleep = time.monotonic, time.sleep  # real time for this one
    service._limit_seconds, service._grace_seconds = 0.1, 0.1  # the test seam: 0.2 s instead of 61
    gate = threading.Event()
    rig.woo.status = lambda request: (gate.wait(10.0), system_status())[1]
    client = rig.harness.signed_in_client()
    try:
        started = time.monotonic()
        response = client.post("/api/stores/1/test", headers=WRITE_HEADERS)
        elapsed = time.monotonic() - started
        body = response.json()
        assert response.status_code == 200 and elapsed < 3.0  # the worker is still blocked: the answer didn't wait
        assert (body["ok"], body["reason"], body["state"]) == (False, "timeout", "unreachable")
        assert client.get("/api/stores").json()["stores"][0]["health"]["reason"] == "timeout"  # saved like any result
        # the worker still holds the store: nothing overlaps it
        assert client.post("/api/stores/1/test", headers=WRITE_HEADERS).json() == {"error": "busy"}
        assert client.patch("/api/stores/1", headers=WRITE_HEADERS, json={"url": STORE_URL + "/x"}).json() == {
            "error": "busy"
        }
        assert client.put("/api/stores/1/keys", headers=WRITE_HEADERS, json=NEW_KEYS).json() == {"error": "busy"}
        assert client.delete("/api/stores/1", headers=WRITE_HEADERS).json() == {"error": "busy"}
        assert client.patch("/api/stores/1", headers=WRITE_HEADERS, json={"name": "Fine"}).status_code == 200
    finally:
        gate.set()
    deadline = time.monotonic() + 5.0
    while service._busy and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not service._busy  # the worker ended and let go
    assert service.get(1).row.health_reason == "timeout"  # its late answer wrote nothing
    service._limit_seconds = 60.0
    rig.woo.status = None
    assert client.post("/api/stores/1/test", headers=WRITE_HEADERS).json()["ok"] is True


def test_the_default_limit_is_sixty_seconds_with_a_short_grace() -> None:
    from shelfsync.apply.woocommerce import TOTAL_SECONDS

    service = make_store_rig().service
    assert (service._limit_seconds, service._grace_seconds) == (TOTAL_SECONDS, 1.0) and TOTAL_SECONDS == 60.0


def test_an_error_inside_the_worker_reaches_the_request_and_frees_the_store() -> None:
    rig = make_store_rig()
    add_store(rig)

    def explode(request: httpx.Request) -> httpx.Response:
        raise RuntimeError("boom")

    rig.woo.status = explode
    with pytest.raises(RuntimeError, match="boom"):
        rig.service.test(1)
    assert not rig.service._busy


# ---- R3: the HTTP libraries never log a store's address -------------------------------------------------------------


def _read_test_logs(rig: StoreRig, caplog: pytest.LogCaptureFixture) -> str:
    caplog.clear()
    caplog.set_level(logging.DEBUG)
    rig.service.test(1)
    return "\n".join(record.getMessage() for record in caplog.records)


@pytest.mark.parametrize("configure", [logs.configure_logging, None, logs.configure_append_logging])
def test_httpx_and_httpcore_never_log_a_store_host(
    configure: object, caplog: pytest.LogCaptureFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("httpx", "httpcore"):
        monkeypatch.setattr(logging.getLogger(name), "level", logging.NOTSET)  # undo any earlier setup
    rig = make_store_rig()
    add_store(rig)
    if configure is None:  # without the setup the libraries do log it: so the checks below mean something
        assert "store-a.example" in _read_test_logs(rig, caplog)
        return
    handler = configure(tmp_path, 1) if configure is logs.configure_logging else configure(tmp_path)  # type: ignore[operator]
    try:
        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("httpcore").level == logging.WARNING
        assert "store-a.example" not in _read_test_logs(rig, caplog)
    finally:
        logs.remove_logging(handler)


# ---- R4: the id in the path -----------------------------------------------------------------------------------------


@pytest.mark.parametrize("store_id", ["0", "-1", str(2**63), str(2**64), "9" * 40, "1.5", "abc"])
@pytest.mark.parametrize(
    ("method", "suffix", "body"),
    [("PATCH", "", {"name": "x"}), ("PUT", "/keys", NEW_KEYS), ("DELETE", "", None), ("POST", "/test", None)],
)
def test_an_id_out_of_range_is_a_422_never_a_500(store_id: str, method: str, suffix: str, body: object) -> None:
    rig = make_store_rig()
    client = rig.harness.signed_in_client(raise_server_exceptions=False)
    response = client.request(method, f"/api/stores/{store_id}{suffix}", headers=WRITE_HEADERS, json=body)
    assert (response.status_code, response.json()) == (422, {"error": "invalid_request"})


@pytest.mark.parametrize(
    ("method", "suffix", "body"),
    [("PATCH", "", {"name": "x"}), ("PUT", "/keys", NEW_KEYS), ("DELETE", "", None), ("POST", "/test", None)],
)
def test_the_largest_id_is_an_ordinary_404(method: str, suffix: str, body: object) -> None:
    client = make_store_rig().harness.signed_in_client(raise_server_exceptions=False)
    response = client.request(method, f"/api/stores/{2**63 - 1}{suffix}", headers=WRITE_HEADERS, json=body)
    assert (response.status_code, response.json()) == (404, {"error": "not_found"})


# ---- R5: a host change never leaves keys on the wrong host ----------------------------------------------------------


class CrashingStore(FailingSecretStore):
    """Raises a plain error (a crash, not a Credential Manager failure) at the n-th `set` or `delete`."""

    def __init__(self) -> None:
        super().__init__()
        self.crash_on_set: int | None = None
        self.crash_on_delete: int | None = None
        self.deletes = 0
        self.url_when_set: list[str] = []
        self.entries_when_set: list[tuple[str | None, str | None]] = []
        self.probe: StoreRig | None = None

    def set(self, name: str, value: str) -> None:
        if self.probe is not None and value in (KEY_2, SECRET_2):
            self.url_when_set.append(self.probe.service.get(1).row.url)
            self.entries_when_set.append((MemorySecretStore.get(self, "store-1-key"), None))
        if self.crash_on_set is not None and self.sets + 1 == self.crash_on_set:
            self.sets += 1
            raise RuntimeError("crash")
        super().set(name, value)

    def delete(self, name: str) -> None:
        self.deletes += 1
        if self.crash_on_delete is not None and self.deletes == self.crash_on_delete:
            raise RuntimeError("crash")
        super().delete(name)


def move_body(**extra: object) -> dict[str, object]:
    return {"url": OTHER_URL, **NEW_KEYS, **extra}


def test_a_host_change_deletes_the_old_keys_before_the_new_address_is_committed_and_writes_the_new_after() -> None:
    secrets = CrashingStore()
    rig = make_store_rig(secrets)
    add_store(rig)
    secrets.probe = rig
    client = rig.harness.signed_in_client()
    response = client.patch("/api/stores/1", headers=WRITE_HEADERS, json=move_body())
    assert response.status_code == 200 and response.json()["url"] == OTHER_URL
    # when the new keys were written the new address was already committed and the old keys were already gone
    assert secrets.url_when_set == [OTHER_URL, OTHER_URL] and secrets.entries_when_set[0][0] is None
    assert (secrets.get("store-1-key"), secrets.get("store-1-secret")) == (KEY_2, SECRET_2)
    assert response.json()["health"]["state"] == "unknown"


def test_a_failed_write_of_the_new_keys_puts_the_old_address_the_old_edits_and_the_old_keys_back() -> None:
    secrets = FailingSecretStore()
    rig = make_store_rig(secrets)
    add_store(rig)
    client = rig.harness.signed_in_client()
    before = client.get("/api/stores").json()["stores"][0]
    secrets.fail_set_on = secrets.sets + 1  # the first write after the old keys went
    response = client.patch("/api/stores/1", headers=WRITE_HEADERS, json=move_body(name="Moved", state="paused"))
    assert (response.status_code, response.json()) == (503, {"error": "secrets_unavailable"})
    assert client.get("/api/stores").json()["stores"] == [before]  # address, name and state are back
    assert (secrets.get("store-1-key"), secrets.get("store-1-secret")) == (KEY, SECRET)


def test_a_crash_after_the_address_was_committed_leaves_no_keys_never_old_keys_on_the_new_host() -> None:
    secrets = CrashingStore()
    rig = make_store_rig(secrets)
    add_store(rig)
    secrets.crash_on_set = secrets.sets + 1
    client = rig.harness.signed_in_client(raise_server_exceptions=False)
    assert client.patch("/api/stores/1", headers=WRITE_HEADERS, json=move_body()).status_code == 500
    assert rig.service.get(1).row.url == OTHER_URL
    assert (secrets.get("store-1-key"), secrets.get("store-1-secret")) == (None, None)


@pytest.mark.parametrize("crash_on", [1, 2])
def test_a_crash_while_the_old_keys_are_being_deleted_leaves_the_old_address(crash_on: int) -> None:
    secrets = CrashingStore()
    rig = make_store_rig(secrets)
    add_store(rig)
    secrets.crash_on_delete = secrets.deletes + crash_on
    client = rig.harness.signed_in_client(raise_server_exceptions=False)
    assert client.patch("/api/stores/1", headers=WRITE_HEADERS, json=move_body()).status_code == 500
    assert rig.service.get(1).row.url == STORE_URL  # the address was never committed: no key is on the wrong host


def test_old_keys_that_cannot_be_deleted_leave_everything_as_it_was() -> None:
    secrets = FailingSecretStore()
    rig = make_store_rig(secrets)
    add_store(rig)
    client = rig.harness.signed_in_client()
    before = client.get("/api/stores").json()["stores"][0]
    secrets.fail_delete = {"store-1-secret"}
    assert client.patch("/api/stores/1", headers=WRITE_HEADERS, json=move_body()).status_code == 503
    assert client.get("/api/stores").json()["stores"] == [before]
    assert (secrets.get("store-1-key"), secrets.get("store-1-secret")) == (KEY, SECRET)


def test_a_path_only_change_and_a_same_host_key_replacement_stay_one_transaction() -> None:
    secrets = CrashingStore()
    rig = make_store_rig(secrets)
    add_store(rig)
    client = rig.harness.signed_in_client()
    assert client.patch("/api/stores/1", headers=WRITE_HEADERS, json={"url": STORE_URL + "/shop"}).status_code == 200
    assert secrets.deletes == 0  # no key was ever taken out
    same_host = {"url": STORE_URL + "/shop2", **NEW_KEYS}
    assert client.patch("/api/stores/1", headers=WRITE_HEADERS, json=same_host).status_code == 200
    assert secrets.deletes == 0 and secrets.get("store-1-key") == KEY_2
    secrets.fail_set_on = secrets.sets + 2  # the second write fails: the single transaction is rolled back whole
    failed = client.patch(
        "/api/stores/1",
        headers=WRITE_HEADERS,
        json={"url": STORE_URL + "/shop3", **{"consumer_key": KEY, "consumer_secret": SECRET}},
    )
    assert failed.status_code == 503
    assert rig.service.get(1).row.url == STORE_URL + "/shop2" and secrets.get("store-1-key") == KEY_2


# ---- the cheap ones -------------------------------------------------------------------------------------------------


def test_o1_the_client_asks_for_no_compression_and_refuses_a_declared_size_over_the_cap() -> None:
    woo = FakeWoo()
    with WooClient(STORE_URL, KEY, SECRET, transport=woo.transport) as client:
        client.get(SYSTEM_STATUS, {}, deadline=time.monotonic() + 60)
    assert woo.requests[0].headers["Accept-Encoding"] == "identity"

    def declares(size: int) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Length": str(size)}, content=b"x" * 10)

    for size, refused in ((MAX_BODY_BYTES + 1, True), (10**12, True), (MAX_BODY_BYTES, False), (10, False)):
        rig = FakeWoo(status=declares(size))
        assert declares(size).headers["Content-Length"] == str(size)  # the fake really declares it
        with WooClient(STORE_URL, KEY, SECRET, transport=rig.transport) as client:
            from shelfsync.apply.woocommerce import ReadRefused

            if refused:
                with pytest.raises(ReadRefused, match="bad_response"):
                    client.get(SYSTEM_STATUS, {}, deadline=time.monotonic() + 60)
            else:
                client.get(SYSTEM_STATUS, {}, deadline=time.monotonic() + 60)


def test_o4_reading_the_pair_for_use_registers_it_for_redaction() -> None:
    secrets = MemorySecretStore()
    secrets.set("store-1-key", KEY)
    secrets.set("store-1-secret", SECRET)
    assert redact(KEY) != MASK  # not registered yet: stored by something else, before this run
    pair = StoreCredentials(secrets).pair(1)
    assert pair is not None
    assert redact(f"{KEY} {SECRET}") == f"{MASK} {MASK}"


def test_o6_a_wal_database_with_its_wal_file_present_gives_the_store_entry_names(tmp_path: Path) -> None:
    paths = make_data(tmp_path)
    paths.database.unlink()
    conn = connect(paths.database)  # WAL, as the app opens it
    try:
        migrate(conn)
        conn.execute(
            "INSERT INTO store (name, url, code, shape, color, created_at) "
            "VALUES ('S', 'https://a.example', 'SA', 'circle', 'indigo', 'x')"
        )
        assert (paths.database.parent / (paths.database.name + "-wal")).is_file()  # nothing checkpointed yet
        assert uninstall.store_secret_names(paths.database) == ["store-1-key", "store-1-secret"]
        secrets = MemorySecretStore()
        secrets.set("store-1-key", KEY)
        secrets.set("store-1-secret", SECRET)
        assert uninstall.remove_secrets(secrets, uninstall.store_secret_names(paths.database)) == []
    finally:
        conn.close()
    assert (secrets.get("store-1-key"), secrets.get("store-1-secret")) == (None, None)
    assert isinstance(paths, DataPaths) and isinstance(sqlite3.sqlite_version, str)


# ---- review fixes ---------------------------------------------------------------------------------------------------


class CommitFails:
    """A connection that refuses COMMIT while `armed`, and passes everything else to the real one."""

    armed = False

    def __init__(self, real: sqlite3.Connection) -> None:
        self._real = real

    def execute(self, sql: str, *args: object) -> sqlite3.Cursor:
        if sql == "COMMIT" and CommitFails.armed:
            raise sqlite3.OperationalError("disk I/O error")
        return self._real.execute(sql, *args)  # type: ignore[arg-type]

    def __getattr__(self, name: str) -> object:
        return getattr(self._real, name)


def test_m1_when_the_old_address_cannot_be_put_back_the_old_keys_are_not_put_under_the_new_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secrets = FailingSecretStore()
    rig = make_store_rig(secrets)
    add_store(rig)
    import shelfsync.store_service as module

    real_update, calls = module.update_store, []

    def failing_undo(connection: sqlite3.Connection, store_id: int, changes: object) -> bool:
        calls.append(1)
        if len(calls) == 2:  # the first call is the edit itself, the second is `_undo_edit`
            raise sqlite3.OperationalError("database is locked")
        return real_update(connection, store_id, changes)  # type: ignore[arg-type]

    monkeypatch.setattr(module, "update_store", failing_undo)
    secrets.fail_set_on = secrets.sets + 1  # writing the new keys fails
    client = rig.harness.signed_in_client()
    response = client.patch("/api/stores/1", headers=WRITE_HEADERS, json=move_body())
    assert (response.status_code, response.json()) == (503, {"error": "secrets_unavailable"})
    assert len(calls) == 2
    assert rig.service.get(1).row.url == OTHER_URL  # the address could not be put back ...
    assert (secrets.get("store-1-key"), secrets.get("store-1-secret")) == (None, None)  # ... so no keys anywhere


def test_m1_a_failed_commit_of_a_host_change_keeps_the_old_address_and_gives_the_old_keys_back() -> None:
    secrets = FailingSecretStore()
    rig = make_store_rig(secrets)
    add_store(rig)
    real_open = rig.service._open
    rig.service._open = lambda: CommitFails(real_open())  # type: ignore[assignment,return-value]
    CommitFails.armed = True
    try:
        client = rig.harness.signed_in_client(raise_server_exceptions=False)
        assert client.patch("/api/stores/1", headers=WRITE_HEADERS, json=move_body()).status_code == 500
    finally:
        CommitFails.armed = False
    assert rig.service.get(1).row.url == STORE_URL
    assert (secrets.get("store-1-key"), secrets.get("store-1-secret")) == (KEY, SECRET)


@pytest.mark.parametrize("body", [b"this is not gzip", None])
def test_m2_any_content_encoding_is_refused_not_decoded_and_never_a_500(body: bytes | None) -> None:
    import gzip

    payload = body if body is not None else gzip.compress(b'{"environment":{"version":"9.4.1","wp_version":"6.7"}}')
    for encoding in ("gzip", "br", "deflate", "gzip, br"):

        def answer(request: httpx.Request, encoding: str = encoding) -> httpx.Response:
            # built from a stream, so nothing decodes it before the client does (a real transport hands over raw bytes)
            return httpx.Response(200, headers={"Content-Encoding": encoding}, stream=httpx.ByteStream(payload))

        woo = FakeWoo(status=answer)
        outcome = run_read_test_for(woo)
        assert (outcome.reason, outcome.health) == ("bad_response", "unreachable")
        assert len(woo.requests) == 1


def test_m2_identity_encoding_is_fine_and_a_decoding_error_is_a_bad_response() -> None:
    answer = httpx.Response(
        200,
        headers={"Content-Encoding": "identity"},
        content=b'{"environment":{"version":"9.4.1","wp_version":"6.7"}}',
    )
    assert run_read_test_for(FakeWoo(status=answer)).ok

    def broken(request: httpx.Request) -> httpx.Response:
        raise httpx.DecodingError("bad gzip")

    assert run_read_test_for(FakeWoo(status=broken)).reason == "bad_response"


def run_read_test_for(woo: FakeWoo):  # type: ignore[no-untyped-def]
    from shelfsync.apply.woocommerce import run_read_test

    with WooClient(STORE_URL, KEY, SECRET, transport=woo.transport, monotonic=woo.time.monotonic) as client:
        return run_read_test(client, 150, "SA", sleep=woo.time.sleep, monotonic=woo.time.monotonic)


def test_l1_the_slot_is_still_held_while_the_result_is_saved_and_free_afterwards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import shelfsync.store_service as module

    rig = make_store_rig()
    add_store(rig)
    held: list[bool] = []
    real_save = module.save_test_result

    def watching(*args: object, **kwargs: object) -> bool:
        held.append(1 in rig.service._busy)
        return real_save(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(module, "save_test_result", watching)
    assert rig.service.test(1).outcome.ok
    assert held == [True]
    assert not rig.service._busy


def test_l2_the_in_memory_services_keeper_connection_is_closed_with_the_service() -> None:
    from shelfsync.store_service import StoreService

    service = StoreService.in_memory()
    keeper = service._keeper
    assert keeper is not None
    keeper.execute("SELECT 1")  # open now
    del service
    gc.collect()
    with pytest.raises(sqlite3.ProgrammingError):
        keeper.execute("SELECT 1")  # closed: nothing is left to warn about at exit


def test_l4_an_unknown_stored_colour_shows_the_default_with_a_warning_instead_of_failing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from dataclasses import replace

    from shelfsync.api.stores import DEFAULT_COLOR, to_model
    from shelfsync.store_service import StoreView

    rig = make_store_rig()
    add_store(rig)
    view = rig.service.list()[0]
    odd = StoreView(replace(view.row, color="violet"), view.consumer_key, view.consumer_secret)
    caplog.set_level(logging.WARNING)
    assert to_model(odd).color == DEFAULT_COLOR == "indigo"
    assert "unknown colour key" in caplog.text and "violet" not in caplog.text
    assert to_model(StoreView(replace(view.row, color="teal"), None, None)).color == "teal"
