"""SET-05, M2.4 review fixes R2 to R9: the parse slot, the downgrade refusal, the left-out header, the token's expiry,
failures during the derivation or the database, the shared secrets-write lock, and the cap on stores."""

import inspect
import json
import logging
import threading
from pathlib import Path
from typing import Any

import pytest

from shelfsync import server
from shelfsync.api import backup as api_backup
from shelfsync.api.backup import IMPORT_BODY_MAX, ExportService
from shelfsync.paths import DataPaths
from shelfsync.platform.notify import FakeNotifier
from shelfsync.platform.secrets import MemorySecretStore
from shelfsync.secure import backup_crypto
from shelfsync.secure.backup_crypto import MAX_FILE_CHARS
from shelfsync.secure.credentials import SECRETS_WRITE_LOCK
from shelfsync.store_service import MAX_STORES
from tests.backup_support import (
    EXPORT,
    FAST_N,
    GITHUB_TOKEN,
    IMPORT,
    PASSPHRASE,
    CommitFails,
    Install,
    ReadsFail,
    cant_open,
    entries,
    export_text,
    file_for,
    good_payload,
    good_secrets,
    import_response,
    make_install,
    populate,
    rows,
    snapshot_of,
)
from tests.storage_support import RW_ID, RW_SECRET
from tests.store_support import KEY, KEY_2, SECRET, SECRET_2, FailingSecretStore, new_store_body
from tests.support import WRITE_HEADERS
from tests.test_server import RecordingServe

LEFT_OUT = "x-shelfsync-left-out"


@pytest.fixture(autouse=True)
def fast_kdf(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(backup_crypto, "SCRYPT_N", FAST_N)


@pytest.fixture
def source(tmp_path: Path) -> Install:
    install = make_install(tmp_path, "source")
    populate(install)
    return install


@pytest.fixture
def target(tmp_path: Path) -> Install:
    return make_install(tmp_path, "target")


class BlockingStore(FailingSecretStore):
    """Writes the named entry, then waits for the test to let the write finish (the entry is "half way": written, with
    the caller still inside its operation). Armed once."""

    def __init__(self) -> None:
        super().__init__()
        self.block_after: str | None = None
        self.entered = threading.Event()
        self.release = threading.Event()

    def set(self, name: str, value: str) -> None:
        super().set(name, value)
        if self.block_after == name:
            self.block_after = None
            self.entered.set()
            assert self.release.wait(10), "the test never let the write finish"


def in_thread(work: Any) -> tuple[threading.Thread, dict[str, Any]]:
    result: dict[str, Any] = {}

    def run() -> None:
        result["value"] = work()

    thread = threading.Thread(target=run)
    thread.start()
    return thread, result


# ---- R2: one parse or derivation at a time, plain files included ----


def test_a_plain_import_is_busy_while_another_file_is_being_parsed(
    source: Install, target: Install, monkeypatch: pytest.MonkeyPatch
) -> None:
    plain = export_text(source)
    entered, release = threading.Event(), threading.Event()
    real = api_backup.parse_envelope

    def slow(text: str) -> dict[str, Any]:
        entered.set()
        assert release.wait(10)
        return real(text)

    monkeypatch.setattr(api_backup, "parse_envelope", slow)
    first, result = in_thread(lambda: import_response(target, plain))
    try:
        assert entered.wait(10)
        second = import_response(make_install(target.path.parent, "other"), plain)
        assert (second.status_code, second.json()) == (409, {"error": "busy"})
    finally:
        release.set()
        first.join(10)
    assert result["value"].status_code == 200
    assert import_response(make_install(target.path.parent, "third"), plain).status_code == 200  # the slot is free


# ---- R4: what an export left out ----


def left_out(install: Install) -> str | None:
    response = install.client.post(EXPORT, headers=WRITE_HEADERS, json={"passphrase": PASSPHRASE})
    assert response.status_code == 200
    return response.headers.get(LEFT_OUT)


def test_the_left_out_header_names_the_kinds_and_the_store_codes_and_never_a_value(source: Install) -> None:
    source.secrets.set("s3-rw-secret", "short")  # a pair that isn't in the shape an import accepts
    source.secrets.set("github-token", "not-a-token-at-all-but-long-enough")
    source.secrets.delete("store-2-secret")  # half a pair
    response = source.client.post(EXPORT, headers=WRITE_HEADERS, json={"passphrase": PASSPHRASE})
    header = response.headers[LEFT_OUT]
    assert header == "stores:SB;s3:rw;github"
    for value in (KEY, SECRET, KEY_2, SECRET_2, RW_ID, RW_SECRET, GITHUB_TOKEN, "not-a-token", "short"):
        assert value not in header


def test_every_kind_can_be_listed_with_several_codes(source: Install) -> None:
    source.secrets.set("store-1-key", "ck_nope")
    source.secrets.set("s3-ro-key-id", "bad")
    assert left_out(source) == "stores:SA;s3:ro"
    source.secrets.set("store-2-key", "ck_nope")
    source.secrets.set("s3-rw-key-id", "bad")
    assert left_out(source) == "stores:SA,SB;s3:rw,ro"


def test_no_header_when_nothing_was_left_out_or_nothing_was_there(source: Install, target: Install) -> None:
    assert left_out(source) is None
    plain = source.client.post(EXPORT, headers=WRITE_HEADERS, json={"passphrase": None})
    assert LEFT_OUT not in plain.headers
    source.secrets.delete("s3-ro-key-id")  # a pair that isn't there at all isn't "left out"
    source.secrets.delete("s3-ro-secret")
    source.secrets.delete("github-token")
    assert left_out(source) is None
    assert left_out(target) is None  # an install with no secrets


def test_a_half_s3_pair_is_left_out(source: Install) -> None:
    source.secrets.delete("s3-ro-secret")
    assert left_out(source) == "s3:ro"


# ---- R5: the token's cached expiry ----


def test_an_import_that_commits_a_token_resets_the_cached_expiry_once(source: Install, target: Install) -> None:
    assert import_response(target, export_text(source, PASSPHRASE), PASSPHRASE).status_code == 200
    assert target.expiry_resets == [1]


def test_it_isnt_reset_when_the_file_has_no_token_or_isnt_encrypted(source: Install, tmp_path: Path) -> None:
    no_token = make_install(tmp_path, "no-token")
    secrets = good_secrets(github_token=None)
    assert import_response(no_token, file_for(good_payload(secrets=secrets), PASSPHRASE), PASSPHRASE).status_code == 200
    plain = make_install(tmp_path, "plain")
    assert import_response(plain, export_text(source)).status_code == 200
    assert no_token.expiry_resets == [] and plain.expiry_resets == []


def test_it_isnt_reset_when_the_import_fails(source: Install, tmp_path: Path) -> None:
    text = export_text(source, PASSPHRASE)
    failing = make_install(tmp_path, "failing-write")
    failing.secrets.fail_set_on = failing.secrets.sets + 9  # the token is the ninth write
    assert import_response(failing, text, PASSPHRASE).status_code == 503
    commit = make_install(tmp_path, "failing-commit")
    commit.exports._connect = lambda: CommitFails(commit.open_db())
    assert import_response(commit, text, PASSPHRASE).status_code == 503
    wrong = make_install(tmp_path, "wrong")
    assert import_response(wrong, text, "another passphrase!").status_code == 422
    assert failing.expiry_resets == [] and commit.expiry_resets == [] and wrong.expiry_resets == []


def test_a_hook_that_fails_doesnt_undo_a_committed_import(
    source: Install, target: Install, caplog: pytest.LogCaptureFixture
) -> None:
    def broken() -> None:
        raise OSError("the state file is locked")

    target.exports._forget_expiry = broken
    with caplog.at_level(logging.WARNING):
        response = import_response(target, export_text(source, PASSPHRASE), PASSPHRASE)
    assert response.status_code == 200 and len(rows(target, "store")) == 2
    assert "expiry couldn't be reset (OSError)" in caplog.text and "locked" not in caplog.text


def test_the_running_app_hands_the_import_the_update_services_reset(data_paths: DataPaths) -> None:
    serve = RecordingServe()
    assert server.run(data_paths, FakeNotifier(), serve, 0.0, MemorySecretStore()) == server.EXIT_OK
    assert serve.app is not None
    endpoint = next(
        context.endpoint  # type: ignore[attr-defined]
        for context in api_backup_routes(serve.app)
        if getattr(context, "path", None) == IMPORT
    )
    service = inspect.getclosurevars(endpoint).nonlocals["service"]
    assert isinstance(service, ExportService)
    assert service._forget_expiry == serve.app.state.updates.forget_expiry


def api_backup_routes(app: Any) -> list[Any]:
    from fastapi.routing import iter_route_contexts

    return list(iter_route_contexts(app.routes))


# ---- R6: a failing derivation or database ----


@pytest.mark.parametrize("error", [ValueError("memory limit exceeded"), MemoryError(), OverflowError()])
def test_a_failing_scrypt_is_503_backup_failed_and_the_slot_stays_free(
    source: Install,
    target: Install,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
) -> None:
    text = export_text(source, PASSPHRASE)
    before = snapshot_of(target)

    def boom(*args: object, **kwargs: object) -> bytes:
        raise error

    with monkeypatch.context() as patch, caplog.at_level(logging.DEBUG):
        patch.setattr(backup_crypto.hashlib, "scrypt", boom)
        exported = source.client.post(EXPORT, headers=WRITE_HEADERS, json={"passphrase": PASSPHRASE})
        imported = import_response(target, text, PASSPHRASE)
    for response in (exported, imported):
        assert (response.status_code, response.json()) == (503, {"error": "backup_failed"})
    assert snapshot_of(target) == before
    assert f"({type(error).__name__})" in caplog.text
    assert "memory limit" not in caplog.text and PASSPHRASE not in caplog.text
    assert export_text(source, PASSPHRASE)  # the slot was released: the next export works
    assert import_response(target, text, PASSPHRASE).status_code == 200


def test_a_database_that_cant_begin_or_commit_is_503_backup_failed_and_nothing_is_left(
    source: Install, target: Install
) -> None:
    text = export_text(source, PASSPHRASE)
    target.secrets.set("github-token", "github_pat_" + "old" * 10)
    before = snapshot_of(target)
    for statement in ("BEGIN IMMEDIATE", "COMMIT"):
        target.exports._connect = lambda s=statement: CommitFails(target.open_db(), s)  # type: ignore[misc]
        response = import_response(target, text, PASSPHRASE)
        assert (response.status_code, response.json()) == (503, {"error": "backup_failed"}), statement
        assert snapshot_of(target) == before, statement
    source.exports._connect = lambda: CommitFails(source.open_db(), "BEGIN")
    response = source.client.post(EXPORT, headers=WRITE_HEADERS, json={"passphrase": PASSPHRASE})
    assert (response.status_code, response.json()) == (503, {"error": "backup_failed"})


def test_the_failure_is_logged_with_its_type_only(
    source: Install, target: Install, caplog: pytest.LogCaptureFixture
) -> None:
    target.exports._connect = lambda: CommitFails(target.open_db())
    with caplog.at_level(logging.WARNING):
        import_response(target, export_text(source, PASSPHRASE), PASSPHRASE)
    assert "couldn't use the database (OperationalError)" in caplog.text
    assert "disk I/O" not in caplog.text


# ---- R7: one lock for every secrets write ----


def test_the_storage_service_and_the_stores_and_the_token_share_the_one_lock(source: Install) -> None:
    assert source.storage.lock is SECRETS_WRITE_LOCK


def test_an_export_cant_read_a_store_pair_halfway_through_a_save_keys(tmp_path: Path) -> None:
    store = BlockingStore()
    install = make_install(tmp_path, "blocking", secrets=store)
    populate(install)
    store.block_after = "store-1-key"  # the new key is written, the new secret isn't yet
    save, _ = in_thread(
        lambda: install.client.put(
            "/api/stores/1/keys", headers=WRITE_HEADERS, json={"consumer_key": KEY_2, "consumer_secret": SECRET_2}
        )
    )
    reader = install.harness.signed_in_client()
    done = threading.Event()
    exported: dict[str, Any] = {}

    def export() -> None:
        exported["text"] = reader.post(EXPORT, headers=WRITE_HEADERS, json={"passphrase": PASSPHRASE}).text
        done.set()

    try:
        assert store.entered.wait(10)
        assert store.get("store-1-key") == KEY_2 and store.get("store-1-secret") == SECRET  # half way, indeed
        thread = threading.Thread(target=export)
        thread.start()
        assert not done.wait(0.5)  # the export waits for the save to finish
    finally:
        store.release.set()
        save.join(10)
    thread.join(10)
    pair = json.loads(backup_crypto.open_envelope(json.loads(exported["text"]), PASSPHRASE))["secrets"]["stores"]["SA"]
    assert pair == {"consumer_key": KEY_2, "consumer_secret": SECRET_2}  # whole, never new key with old secret


def test_a_token_saved_while_an_import_fails_is_not_overwritten_by_its_undo(source: Install, tmp_path: Path) -> None:
    text = export_text(source, PASSPHRASE)
    store = BlockingStore()
    target = make_install(tmp_path, "racing", secrets=store)
    assert target.updates is not None
    target.exports._connect = lambda: CommitFails(target.open_db())  # the import will fail at the commit and undo
    store.block_after = "github-token"  # the import's own token write is the last one before the commit
    importing, result = in_thread(lambda: import_response(target, text, PASSPHRASE))
    updates = target.updates
    new_token = "github_pat_" + "N" * 30
    saved = threading.Event()

    def save_token() -> None:
        updates.set_token(new_token)
        saved.set()

    try:
        assert store.entered.wait(10)
        saver = threading.Thread(target=save_token)
        saver.start()
        assert not saved.wait(0.5)  # the owner's save waits: the import holds the lock
    finally:
        store.release.set()
        importing.join(10)
    saver.join(10)
    assert result["value"].status_code == 503
    assert saved.is_set() and store.get("github-token") == new_token  # the undo came first, then the save
    assert rows(target, "store") == []


def test_stores_storage_token_export_and_import_at_once_neither_deadlock_nor_corrupt(
    source: Install, tmp_path: Path
) -> None:
    """The lock-order check: all five kinds of writer run together, many times; they all finish (a deadlock would hang
    the joins) and what is stored is whole."""
    text = export_text(source, PASSPHRASE)
    problems: list[BaseException] = []

    def guarded(work: Any) -> Any:
        def run() -> None:
            try:
                for _ in range(12):
                    work()
            except BaseException as error:
                problems.append(error)

        return run

    clients = [source.harness.signed_in_client() for _ in range(5)]
    other = make_install(tmp_path, "concurrent-import")
    assert source.updates is not None
    updates = source.updates
    work = [
        lambda: clients[0].put(
            "/api/stores/1/keys", headers=WRITE_HEADERS, json={"consumer_key": KEY_2, "consumer_secret": SECRET_2}
        ),
        lambda: clients[1].put(
            "/api/secrets/s3-rw", headers=WRITE_HEADERS, json={"access_key_id": RW_ID, "secret_access_key": RW_SECRET}
        ),
        lambda: updates.set_token(GITHUB_TOKEN),
        lambda: clients[2].post(EXPORT, headers=WRITE_HEADERS, json={"passphrase": PASSPHRASE}),
        lambda: import_response(other, text, PASSPHRASE),
        lambda: clients[3].patch("/api/stores/2", headers=WRITE_HEADERS, json={"spacing_ms": 300}),
    ]
    threads = [threading.Thread(target=guarded(item)) for item in work]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(60)
    assert not any(thread.is_alive() for thread in threads), "a writer hung: a lock-order deadlock"
    assert problems == []
    assert source.secrets.get("store-1-key") in (KEY, KEY_2) and source.secrets.get("github-token") == GITHUB_TOKEN


# ---- R8: the cap on stores ----


def create_store(install: Install, index: int) -> None:
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    install.stores.create(
        name=f"Store {index}",
        url=f"https://s{index}.example",
        code=letters[index // 26] + letters[index % 26],
        shape="circle",
        color="indigo",
        spacing_ms=150,
        main_button="Download",
        consumer_key=KEY,
        consumer_secret=SECRET,
    )


def test_the_51st_live_store_is_409_too_many_stores_and_leaves_nothing(tmp_path: Path) -> None:
    install = make_install(tmp_path, "full")
    for index in range(MAX_STORES):
        create_store(install, index)
    before = (rows(install, "store"), entries(install))
    body = new_store_body(code="ZZ", url="https://one-more.example")
    response = install.client.post("/api/stores", headers=WRITE_HEADERS, json=body)
    assert (response.status_code, response.json()) == (409, {"error": "too_many_stores"})
    assert (rows(install, "store"), entries(install)) == before
    assert "store-51-key" not in entries(install)
    assert (
        install.client.delete("/api/stores/1", headers=WRITE_HEADERS).status_code == 204
    )  # a removed one doesn't count
    assert install.client.post("/api/stores", headers=WRITE_HEADERS, json=body).status_code == 201


def test_the_import_and_the_stores_api_use_the_same_number() -> None:
    assert api_backup.MAX_STORES is MAX_STORES == 50


def test_a_file_with_exactly_the_most_stores_imports(target: Install) -> None:
    payload = good_payload()
    many = [
        {**payload["stores"][0], "code": chr(65 + i // 26) + chr(65 + i % 26), "url": f"https://s{i}.example"}
        for i in range(MAX_STORES)
    ]
    response = import_response(target, file_for({**payload, "stores": many}))
    assert response.status_code == 200 and response.json()["stores"] == MAX_STORES


# ---- re-review S1: the text cap is the limit that binds ----


def test_a_just_under_1_mib_file_full_of_quotes_passes_the_body_limit_and_is_judged_by_the_text_cap(
    target: Install, monkeypatch: pytest.MonkeyPatch
) -> None:
    text = '"' * (MAX_FILE_CHARS - 100)  # every quote is two bytes in the JSON body
    body = json.dumps({"file": text, "passphrase": None})
    assert len(body) > MAX_FILE_CHARS + 64 * 1024  # more than the old limit allowed: the fix matters
    assert len(body) <= IMPORT_BODY_MAX and IMPORT_BODY_MAX == 2 * MAX_FILE_CHARS + 64 * 1024
    reached: list[int] = []
    real = api_backup.parse_envelope

    def watching(candidate: str) -> dict[str, Any]:
        reached.append(len(candidate))
        return real(candidate)

    monkeypatch.setattr(api_backup, "parse_envelope", watching)
    response = target.client.post(
        IMPORT, headers={**WRITE_HEADERS, "Content-Type": "application/json"}, content=body.encode()
    )
    assert reached == [MAX_FILE_CHARS - 100]  # the body limit let it through; the text reached the parser
    assert (response.status_code, response.json()) == (
        422,
        {"error": "export_invalid"},
    )  # not a file: the parser's word
    assert rows(target, "store") == []


# ---- re-review S2: a database that can't be opened or read is 503 backup_failed ----


def test_an_export_whose_reads_fail_after_begin_is_503_backup_failed(
    source: Install, caplog: pytest.LogCaptureFixture
) -> None:
    source.exports._connect = lambda: ReadsFail(source.open_db())
    with caplog.at_level(logging.WARNING):
        response = source.client.post(EXPORT, headers=WRITE_HEADERS, json={"passphrase": None})
    assert (response.status_code, response.json()) == (503, {"error": "backup_failed"})
    assert "couldn't read the database (OperationalError)" in caplog.text and "malformed" not in caplog.text
    source.exports._connect = source.open_db
    assert source.client.post(EXPORT, headers=WRITE_HEADERS, json={"passphrase": PASSPHRASE}).status_code == 200


def test_an_export_that_cant_open_the_database_is_503_backup_failed(source: Install) -> None:
    source.exports._connect = cant_open
    for passphrase in (None, PASSPHRASE):
        response = source.client.post(EXPORT, headers=WRITE_HEADERS, json={"passphrase": passphrase})
        assert (response.status_code, response.json()) == (503, {"error": "backup_failed"})
    source.exports._connect = source.open_db
    assert source.client.post(EXPORT, headers=WRITE_HEADERS, json={"passphrase": None}).status_code == 200


def test_an_import_that_cant_open_the_database_is_503_backup_failed_and_leaves_nothing(
    source: Install, target: Install
) -> None:
    text = export_text(source, PASSPHRASE)
    target.secrets.set("github-token", "github_pat_" + "old" * 10)
    before = snapshot_of(target)
    target.exports._connect = cant_open
    response = import_response(target, text, PASSPHRASE)
    assert (response.status_code, response.json()) == (503, {"error": "backup_failed"})
    assert snapshot_of(target) == before and target.expiry_resets == []
    target.exports._connect = target.open_db
    assert import_response(target, text, PASSPHRASE).status_code == 200  # nothing was left half done
