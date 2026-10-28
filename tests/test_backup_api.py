"""SET-05: the backup export and import API (`api/backup.py`, `db/export.py`).

The scrypt cost is lowered through the crypto module's own constant (`fast_kdf`); one test runs the real parameters
through the whole API.
"""

import json
import logging
import re
import threading
from pathlib import Path
from typing import Any

import pytest

from shelfsync.api import backup as api_backup
from shelfsync.api.backup import IMPORT_BODY_MAX, ExportService, Payload
from shelfsync.api.storage import StorageValues
from shelfsync.db.export import SETTINGS_KEYS, STORAGE_KEYS, STORE_FIELDS
from shelfsync.db.settings import DEFAULTS, get_setting, set_setting
from shelfsync.db.stores import live_store_count
from shelfsync.secure import backup_crypto
from shelfsync.secure.backup_crypto import MAX_FILE_CHARS, open_envelope, parse_envelope
from shelfsync.secure.credentials import S3Credentials, StoreCredentials
from shelfsync.secure.redact import clear_secrets, redact
from shelfsync.secure.token import INSTALL_TOKEN_NAME
from tests.backup_support import (
    EXPORT,
    FAST_N,
    GITHUB_TOKEN,
    IMPORT,
    NOW,
    PASSPHRASE,
    CommitFails,
    Install,
    entries,
    export_text,
    file_for,
    good_payload,
    good_secrets,
    import_response,
    make_install,
    populate,
    rows,
    tampered,
)
from tests.storage_support import RO_ID, RO_SECRET, RW_ID, RW_SECRET, api_routes
from tests.store_support import KEY, KEY_2, SECRET, SECRET_2, new_store_body
from tests.support import ORIGIN, WRITE_HEADERS, asgi_http, make_harness

REAL_N = backup_crypto.SCRYPT_N  # before any test lowers it


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


def secret_values() -> list[str]:
    return [KEY, SECRET, KEY_2, SECRET_2, RW_ID, RW_SECRET, RO_ID, RO_SECRET, GITHUB_TOKEN]


def decrypted(text: str, passphrase: str | None = PASSPHRASE) -> dict[str, Any]:
    result = json.loads(open_envelope(parse_envelope(text), passphrase))
    assert isinstance(result, dict)
    return result


def snapshot(install: Install) -> tuple[Any, ...]:
    """Everything an import may change in an install: the rows, the settings and every secret entry."""
    return (rows(install, "store"), rows(install, "setting"), entries(install))


# ---- export ----


def test_a_plain_export_holds_settings_stores_and_storage_and_no_secret(source: Install) -> None:
    response = source.client.post(EXPORT, headers=WRITE_HEADERS, json={"passphrase": None})
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    envelope = response.json()
    assert envelope["format"] == "shelfsync-export" and envelope["version"] == 1
    assert envelope["encryption"] is None and "ciphertext" not in envelope
    assert envelope["created_at"] == "2026-10-28T10:00:00.000000Z"
    assert envelope["schema"] == 2
    payload = envelope["payload"]
    assert set(payload) == {"settings", "stores", "storage", "catalog"}  # no `secrets` in a plain file
    assert payload["catalog"] is None
    assert payload["settings"] == {
        "port": 47615,
        "theme": "dark",
        "start_with_windows": True,
        "notifications": True,
        "log_retention_days": 45,
        "db_backups_kept": 12,
        "snapshot_retention_days": 30,
    }
    assert payload["storage"] == {
        "s3_endpoint": "",
        "s3_region": "ap-south-1",
        "s3_bucket": "example-bucket",
        "keep_previous_files": 2,
        "download_link_template": '[amazon_s3 object="{key}"]',
    }
    assert [store["code"] for store in payload["stores"]] == ["SA", "SB"]
    assert payload["stores"][1] == {
        "code": "SB",
        "name": "Store B",
        "url": "https://store-b.example/shop",
        "shape": "square",
        "color": "teal",
        "spacing_ms": 400,
        "main_button": "Get it",
        "state": "paused",
    }
    for value in secret_values():
        assert value not in response.text


def test_an_encrypted_export_holds_every_secret_only_inside_the_ciphertext(source: Install) -> None:
    text = export_text(source, PASSPHRASE)
    for value in secret_values():
        assert value not in text
    assert PASSPHRASE not in text
    envelope = json.loads(text)
    assert set(envelope) == {"format", "version", "created_at", "app_version", "schema", "encryption", "ciphertext"}
    assert envelope["encryption"]["n"] == FAST_N and envelope["encryption"]["r"] == 8
    payload = decrypted(text)
    assert set(payload) == {"settings", "stores", "storage", "catalog", "secrets"}
    assert payload["secrets"] == {
        "stores": {
            "SA": {"consumer_key": KEY, "consumer_secret": SECRET},
            "SB": {"consumer_key": KEY_2, "consumer_secret": SECRET_2},
        },
        "s3": {
            "rw": {"access_key_id": RW_ID, "secret_access_key": RW_SECRET},
            "ro": {"access_key_id": RO_ID, "secret_access_key": RO_SECRET},
        },
        "github_token": GITHUB_TOKEN,
    }


def test_the_install_token_is_never_exported(source: Install) -> None:
    token = source.secrets.get(INSTALL_TOKEN_NAME)
    assert token
    plain = export_text(source)
    encrypted = export_text(source, PASSPHRASE)
    assert token not in plain and token not in encrypted
    assert token not in json.dumps(decrypted(encrypted))
    assert INSTALL_TOKEN_NAME not in json.dumps(decrypted(encrypted)) and "install-token" not in plain


def test_the_filename_is_the_local_date_with_the_ssbak_extension(source: Install) -> None:
    response = source.client.post(EXPORT, headers=WRITE_HEADERS, json={"passphrase": None})
    expected = NOW.astimezone().strftime("%Y-%m-%d")
    assert response.headers["content-disposition"] == f'attachment; filename="shelfsync-export-{expected}.ssbak"'
    pattern = r'attachment; filename="shelfsync-export-\d{4}-\d{2}-\d{2}\.ssbak"'
    assert re.fullmatch(pattern, response.headers["content-disposition"])
    assert response.headers["cache-control"] == "no-store"


def test_an_export_of_an_empty_install_is_valid_and_imports_into_another(tmp_path: Path) -> None:
    empty, other = make_install(tmp_path, "empty"), make_install(tmp_path, "other")
    for passphrase in (None, PASSPHRASE):
        response = import_response(other, export_text(empty, passphrase), passphrase)
        assert response.status_code == 200
        assert response.json() == {"stores": 0, "settings": 12, "secrets": 0, "encrypted": passphrase is not None}


def test_every_export_of_the_same_install_differs_but_opens_the_same(source: Install) -> None:
    first, second = export_text(source, PASSPHRASE), export_text(source, PASSPHRASE)
    assert first != second
    assert decrypted(first) == decrypted(second)


def test_the_payload_covers_every_setting_once_and_the_stores_models_fields() -> None:
    assert set(SETTINGS_KEYS) | set(STORAGE_KEYS) == set(DEFAULTS)
    assert not set(SETTINGS_KEYS) & set(STORAGE_KEYS)
    assert set(Payload.model_fields["settings"].annotation.model_fields) == set(SETTINGS_KEYS)  # type: ignore[union-attr]
    assert set(StorageValues.model_fields) == set(STORAGE_KEYS)
    assert set(api_backup.StoreEntry.model_fields) == set(STORE_FIELDS)
    assert set(Payload.model_fields) == {"settings", "stores", "storage", "catalog", "secrets"}


def test_a_secret_in_a_shape_the_file_requires_otherwise_is_left_out_with_a_warning(
    source: Install, caplog: pytest.LogCaptureFixture
) -> None:
    source.secrets.set("s3-rw-secret", "short")  # not a valid S3 secret
    source.secrets.set("github-token", "not-a-token-at-all-but-long-enough")
    source.secrets.delete("store-2-secret")  # a store with one half of a pair
    with caplog.at_level(logging.DEBUG):
        payload = decrypted(export_text(source, PASSPHRASE))
    assert payload["secrets"]["s3"]["rw"] is None
    assert payload["secrets"]["s3"]["ro"] is not None
    assert payload["secrets"]["github_token"] is None
    assert list(payload["secrets"]["stores"]) == ["SA"]
    assert "in a shape that can be exported" in caplog.text


def test_a_plain_export_never_reads_credential_manager(source: Install) -> None:
    source.secrets.fail_get = True
    assert source.client.post(EXPORT, headers=WRITE_HEADERS, json={"passphrase": None}).status_code == 200


def test_an_encrypted_export_with_an_unreadable_credential_manager_is_503(source: Install) -> None:
    source.secrets.fail_get = True
    response = source.client.post(EXPORT, headers=WRITE_HEADERS, json={"passphrase": PASSPHRASE})
    assert response.status_code == 503 and response.json() == {"error": "secrets_unavailable"}


# ---- the request shapes ----


@pytest.mark.parametrize("passphrase", ["", "a" * 11, "a" * 1025, "é" * 5, 12345, True, ["a" * 12], {"a": 1}])
def test_a_bad_passphrase_is_refused_for_both_routes(source: Install, passphrase: object) -> None:
    export = source.client.post(EXPORT, headers=WRITE_HEADERS, json={"passphrase": passphrase})
    assert export.status_code == 422 and export.json() == {"error": "invalid_request"}
    imported = source.client.post(IMPORT, headers=WRITE_HEADERS, json={"file": "{}", "passphrase": passphrase})
    assert imported.status_code == 422 and imported.json() == {"error": "invalid_request"}


@pytest.mark.parametrize(
    "body",
    [{}, {"passphrase": None, "x": 1}, {"pass": "x" * 12}, [], "x", None],
)
def test_the_export_body_must_be_exactly_a_passphrase_or_null(source: Install, body: object) -> None:
    response = source.client.post(EXPORT, headers=WRITE_HEADERS, json=body)
    assert response.status_code == 422 and response.json() == {"error": "invalid_request"}


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"file": "{}"},
        {"passphrase": None},
        {"file": 5, "passphrase": None},
        {"file": "{}", "passphrase": None, "x": 1},
    ],
)
def test_the_import_body_must_be_exactly_a_file_and_a_passphrase_or_null(source: Install, body: object) -> None:
    response = source.client.post(IMPORT, headers=WRITE_HEADERS, json=body)
    assert response.status_code == 422 and response.json() == {"error": "invalid_request"}


def test_a_bad_request_never_echoes_the_passphrase(source: Install) -> None:
    response = source.client.post(EXPORT, headers=WRITE_HEADERS, json={"passphrase": "x" * 11})
    assert "x" * 11 not in response.text


# ---- round trips ----


def test_a_plain_file_round_trips_the_settings_and_the_stores_but_no_secret(source: Install, target: Install) -> None:
    response = import_response(target, export_text(source))
    assert response.status_code == 200
    assert response.json() == {"stores": 2, "settings": 12, "secrets": 0, "encrypted": False}
    listed = target.client.get("/api/stores").json()["stores"]
    assert [
        (s["code"], s["name"], s["url"], s["shape"], s["color"], s["spacing_ms"], s["main_button"], s["state"])
        for s in listed
    ] == [
        ("SA", "Store A", "https://store-a.example", "circle", "indigo", 150, "Download", "active"),
        ("SB", "Store B", "https://store-b.example/shop", "square", "teal", 400, "Get it", "paused"),
    ]
    assert all(s["keys"] == {"consumer_key": None, "consumer_secret": None} for s in listed)  # a plain file has none
    assert all(s["health"]["state"] == "unknown" for s in listed)
    storage = target.client.get("/api/settings/storage").json()
    assert storage["s3_bucket"] == "example-bucket" and storage["keep_previous_files"] == 2
    assert storage["rw"] == {"access_key_id": None, "secret_access_key": None}
    connection = target.open_db()
    try:
        assert get_setting(connection, "theme") == "dark"
        assert get_setting(connection, "log_retention_days") == 45
        assert get_setting(connection, "db_backups_kept") == 12
    finally:
        connection.close()
    assert set(entries(target)) == {INSTALL_TOKEN_NAME}


def test_an_encrypted_file_round_trips_every_secret(source: Install, target: Install) -> None:
    response = import_response(target, export_text(source, PASSPHRASE), PASSPHRASE)
    assert response.status_code == 200
    # 2 + 2 store keys, 2 + 2 S3, 1 token
    assert response.json() == {"stores": 2, "settings": 12, "secrets": 9, "encrypted": True}
    listed = target.client.get("/api/stores").json()["stores"]
    keys = StoreCredentials(target.secrets)
    assert [keys.read(s["id"]) for s in listed] == [(KEY, SECRET), (KEY_2, SECRET_2)]
    assert S3Credentials(target.secrets).read("rw") == (RW_ID, RW_SECRET)
    assert S3Credentials(target.secrets).read("ro") == (RO_ID, RO_SECRET)
    assert target.secrets.get("github-token") == GITHUB_TOKEN
    # shown masked, like any other key
    assert listed[0]["keys"]["consumer_key"] == "ck_••••" + KEY[-4:]
    assert target.client.get("/api/settings/storage").json()["rw"]["access_key_id"] == RW_ID[:4] + "••••" + RW_ID[-4:]


def test_the_imported_secrets_are_registered_with_the_log_redaction(source: Install, target: Install) -> None:
    text = export_text(source, PASSPHRASE)
    clear_secrets()
    assert import_response(target, text, PASSPHRASE).status_code == 200
    for value in secret_values():
        assert value not in redact(f"value {value} end")


def test_a_paused_store_stays_paused_and_ids_start_fresh(source: Install, target: Install) -> None:
    import_response(target, export_text(source))
    states = {s["code"]: s["state"] for s in target.client.get("/api/stores").json()["stores"]}
    assert states == {"SA": "active", "SB": "paused"}


def test_the_real_scrypt_parameters_round_trip_through_the_api(
    source: Install, target: Install, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(backup_crypto, "SCRYPT_N", REAL_N)
    text = export_text(source, PASSPHRASE)
    assert json.loads(text)["encryption"]["n"] == 131072
    assert import_response(target, text, PASSPHRASE).status_code == 200
    assert S3Credentials(target.secrets).read("rw") == (RW_ID, RW_SECRET)
    wrong = import_response(make_install(source.path.parent, "third"), text, PASSPHRASE + "!")
    assert wrong.status_code == 422 and wrong.json() == {"error": "wrong_passphrase"}


def test_a_file_without_a_secret_or_a_pair_leaves_the_existing_entries_alone(source: Install, target: Install) -> None:
    """An import adds what the file holds; a missing S3 pair or token doesn't delete the one that is there."""
    target.secrets.set("s3-ro-key-id", RO_ID)
    target.secrets.set("s3-ro-secret", RO_SECRET)
    target.secrets.set("github-token", "github_pat_" + "keepme" * 5)
    secrets = good_secrets()
    secrets["s3"]["ro"] = None
    secrets["github_token"] = None
    assert import_response(target, file_for(good_payload(secrets=secrets), PASSPHRASE), PASSPHRASE).status_code == 200
    assert S3Credentials(target.secrets).read("ro") == (RO_ID, RO_SECRET)
    assert target.secrets.get("github-token") == "github_pat_" + "keepme" * 5
    assert S3Credentials(target.secrets).read("rw") == (RW_ID, RW_SECRET)


def test_a_store_with_no_keys_in_the_file_is_imported_without_keys(target: Install) -> None:
    secrets = good_secrets()
    del secrets["stores"]["SB"]
    assert import_response(target, file_for(good_payload(secrets=secrets), PASSPHRASE), PASSPHRASE).status_code == 200
    ids = [s["id"] for s in target.client.get("/api/stores").json()["stores"]]
    keys = StoreCredentials(target.secrets)
    assert keys.read(ids[0]) == (KEY, SECRET) and keys.read(ids[1]) == (None, None)


def test_an_import_overwrites_the_settings_it_carries_with_the_files_values(source: Install, target: Install) -> None:
    connection = target.open_db()
    try:
        set_setting(connection, "theme", "light")
        set_setting(connection, "s3_bucket", "somebucketname")
    finally:
        connection.close()
    import_response(target, export_text(source))
    assert target.client.get("/api/settings/storage").json()["s3_bucket"] == "example-bucket"


# ---- refusals that change nothing ----


def test_a_wrong_passphrase_fails_cleanly_and_changes_nothing(source: Install, target: Install) -> None:
    text = export_text(source, PASSPHRASE)
    before = snapshot(target)
    sets = target.secrets.sets
    response = import_response(target, text, "a different passphrase")
    assert response.status_code == 422 and response.json() == {"error": "wrong_passphrase"}
    assert snapshot(target) == before and target.secrets.sets == sets


def test_an_encrypted_file_without_a_passphrase_is_passphrase_required(source: Install, target: Install) -> None:
    before = snapshot(target)
    response = import_response(target, export_text(source, PASSPHRASE), None)
    assert response.status_code == 422 and response.json() == {"error": "passphrase_required"}
    assert snapshot(target) == before


def test_a_passphrase_sent_with_a_plain_file_is_refused(source: Install, target: Install) -> None:
    """R3: a plain file where the owner expected an encrypted one may be a swapped file: never imported silently."""
    before = snapshot(target)
    response = import_response(target, export_text(source), PASSPHRASE)
    assert (response.status_code, response.json()) == (422, {"error": "export_not_encrypted"})
    assert snapshot(target) == before and target.expiry_resets == []
    assert import_response(target, export_text(source)).json()["encrypted"] is False  # without one it imports


def test_a_plain_file_that_holds_secrets_is_refused(target: Install) -> None:
    before = snapshot(target)
    text = file_for(good_payload(secrets=good_secrets()), None)
    response = import_response(target, text)
    assert response.status_code == 422 and response.json() == {"error": "export_invalid"}
    assert snapshot(target) == before


def test_an_encrypted_file_without_secrets_is_refused(target: Install) -> None:
    before = snapshot(target)
    response = import_response(target, file_for(good_payload(), PASSPHRASE), PASSPHRASE)
    assert response.status_code == 422 and response.json() == {"error": "export_invalid"}
    assert snapshot(target) == before


def test_tampered_files_fail_and_change_nothing(source: Install, target: Install) -> None:
    text = export_text(source, PASSPHRASE)
    before = snapshot(target)
    flip = lambda e: e.update(ciphertext=("A" if e["ciphertext"][0] != "A" else "B") + e["ciphertext"][1:])  # noqa: E731
    cases = {
        "ciphertext": (flip, "wrong_passphrase"),
        "created_at": (lambda e: e.update(created_at="2026-10-28T10:00:01Z"), "wrong_passphrase"),
        "app_version": (lambda e: e.update(app_version="9.9.9"), "wrong_passphrase"),
        "schema": (lambda e: e.update(schema=1), "wrong_passphrase"),
        "salt": (lambda e: e["encryption"].update(salt="QUFBQUFBQUFBQUFBQUFBQQ=="), "wrong_passphrase"),
        "nonce": (lambda e: e["encryption"].update(nonce="QUFBQUFBQUFBQUFB"), "wrong_passphrase"),
        "n": (lambda e: e["encryption"].update(n=2**20), "export_invalid"),
        "r": (lambda e: e["encryption"].update(r=16), "export_invalid"),
        "p": (lambda e: e["encryption"].update(p=2), "export_invalid"),
        "cipher": (lambda e: e["encryption"].update(cipher="AES-128-GCM"), "export_invalid"),
        "downgrade": (lambda e: e.update(encryption=None), "export_invalid"),
        "extra": (lambda e: e.update(extra=1), "export_invalid"),
        "format": (lambda e: e.update(format="x"), "export_invalid"),
    }
    for name, (change, code) in cases.items():
        response = import_response(target, tampered(text, change), PASSPHRASE)
        assert (response.status_code, response.json()) == (422, {"error": code}), name
    assert snapshot(target) == before


def test_raised_kdf_costs_are_refused_before_any_derivation(
    source: Install, target: Install, monkeypatch: pytest.MonkeyPatch
) -> None:
    text = export_text(source, PASSPHRASE)
    calls: list[int] = []

    def counting(*args: object, **kwargs: object) -> bytes:
        calls.append(1)
        raise AssertionError("scrypt must not run for a file asking for another cost")

    monkeypatch.setattr(backup_crypto.hashlib, "scrypt", counting)
    for change in (
        lambda e: e["encryption"].update(n=2**30),
        lambda e: e["encryption"].update(n=FAST_N * 2),
        lambda e: e["encryption"].update(r=2**20),
        lambda e: e["encryption"].update(p=2**20),
    ):
        response = import_response(target, tampered(text, change), PASSPHRASE)
        assert response.status_code == 422 and response.json() == {"error": "export_invalid"}
    assert calls == []


def test_a_newer_format_version_or_schema_is_too_new(source: Install, target: Install) -> None:
    before = snapshot(target)
    text = export_text(source, PASSPHRASE)
    for change in (lambda e: e.update(version=2), lambda e: e.update(schema=3), lambda e: e.update(schema=99)):
        response = import_response(target, tampered(text, change), PASSPHRASE)
        assert (response.status_code, response.json()) == (409, {"error": "export_too_new"})
    plain = tampered(export_text(source), lambda e: e.update(schema=3))
    assert import_response(target, plain).json() == {"error": "export_too_new"}
    assert snapshot(target) == before


def test_an_older_schema_is_accepted(source: Install, target: Install) -> None:
    text = tampered(export_text(source), lambda e: e.update(schema=1))
    assert import_response(target, text).status_code == 200


@pytest.mark.parametrize(
    "text",
    [
        "",
        "not json",
        "[]",
        "null",
        '{"format":"shelfsync-export","version":1,"version":1}',
        '{"a":1,"a":2}',
        '{"format": NaN}',
        "{}",
        '{"format":"shelfsync-export"}',
    ],
)
def test_a_file_that_is_not_an_export_is_export_invalid(target: Install, text: str) -> None:
    before = snapshot(target)
    response = import_response(target, text)
    assert (response.status_code, response.json()) == (422, {"error": "export_invalid"})
    assert snapshot(target) == before


def test_duplicate_keys_inside_the_payload_are_refused(target: Install) -> None:
    text = file_for(good_payload(), None)
    doubled = text.replace('"theme":"dark"', '"theme":"dark","theme":"light"', 1)
    assert doubled != text
    assert import_response(target, doubled).json() == {"error": "export_invalid"}
    assert rows(target, "store") == []


def test_an_unknown_field_anywhere_in_the_payload_is_refused(target: Install) -> None:
    payload = good_payload()
    variants = [
        {**payload, "extra": 1},
        {**payload, "settings": {**payload["settings"], "extra": 1}},
        {**payload, "storage": {**payload["storage"], "extra": 1}},
        {**payload, "stores": [{**payload["stores"][0], "extra": 1}, payload["stores"][1]]},
        {**payload, "catalog": {}},
        {key: value for key, value in payload.items() if key != "catalog"},
        {key: value for key, value in payload.items() if key != "storage"},
    ]
    for variant in variants:
        assert import_response(target, file_for(variant)).json() == {"error": "export_invalid"}
    assert rows(target, "store") == []


def test_the_storage_settings_rules_of_m23_apply_to_an_imported_file(target: Install) -> None:
    payload = good_payload()
    bad_storage = [
        {"s3_endpoint": "http://evil.example"},
        {"s3_endpoint": "https://user:pw@s3.example"},
        {"s3_bucket": "UPPER"},
        {"s3_bucket": "a..b"},
        {"s3_region": "AP South"},
        {"keep_previous_files": 0},
        {"keep_previous_files": 6},
        {"keep_previous_files": True},
        {"download_link_template": "no key here"},
        {"download_link_template": "{key}{key}"},
        {"download_link_template": "{key}\n"},
        {"download_link_template": "{key}{0}"},
    ]
    for change in bad_storage:
        variant = {**payload, "storage": {**payload["storage"], **change}}
        assert import_response(target, file_for(variant)).json() == {"error": "export_invalid"}, change
    good = {**payload, "storage": {**payload["storage"], "s3_endpoint": "http://127.0.0.1:5000"}}
    assert import_response(target, file_for(good)).status_code == 200


def test_the_settings_limits_of_the_app_and_backup_screens_apply(target: Install) -> None:
    payload = good_payload()
    for change in (
        {"port": 80},
        {"port": 47625},
        {"theme": "purple"},
        {"log_retention_days": 0},
        {"log_retention_days": 100000},
        {"db_backups_kept": 31},
        {"snapshot_retention_days": 0},
        {"notifications": "yes"},
        {"start_with_windows": 1},
    ):
        variant = {**payload, "settings": {**payload["settings"], **change}}
        assert import_response(target, file_for(variant)).json() == {"error": "export_invalid"}, change


def test_the_store_rules_of_the_stores_api_apply_to_an_imported_store(target: Install) -> None:
    payload = good_payload()
    first, second = payload["stores"]
    bad_stores: list[list[dict[str, Any]]] = [
        [{**first, "url": "http://store-a.example"}, second],
        [{**first, "url": "https://127.0.0.1"}, second],
        [{**first, "url": "https://user@store-a.example"}, second],
        [{**first, "url": "https://store-a.example/?x=1"}, second],
        [{**first, "code": "sa"}, second],
        [{**first, "code": "SAA"}, second],
        [{**first, "name": ""}, second],
        [{**first, "name": "x" * 61}, second],
        [{**first, "name": "bad\nname"}, second],
        [{**first, "shape": "star"}, second],
        [{**first, "color": "#ff0000"}, second],
        [{**first, "spacing_ms": 49}, second],
        [{**first, "spacing_ms": 5001}, second],
        [{**first, "spacing_ms": "150"}, second],
        [{**first, "main_button": ""}, second],
        [{**first, "state": "removed"}, second],
        [first, {**second, "code": "SA"}],  # a repeated code
        [first, {**second, "url": "https://store-a.example/"}],  # a repeated address once normalised
        [{key: value for key, value in first.items() if key != "name"}, second],
    ]
    for stores in bad_stores:
        assert import_response(target, file_for({**payload, "stores": stores})).json() == {"error": "export_invalid"}
    assert rows(target, "store") == []


def test_more_than_fifty_stores_are_refused(target: Install) -> None:
    payload = good_payload()
    many = [
        {**payload["stores"][0], "code": chr(65 + i // 26) + chr(65 + i % 26), "url": f"https://s{i}.example"}
        for i in range(51)
    ]
    assert import_response(target, file_for({**payload, "stores": many})).json() == {"error": "export_invalid"}


def test_the_secret_shapes_of_the_apis_apply_to_imported_secrets(target: Install) -> None:
    before = snapshot(target)
    bad = [
        good_secrets(stores={"SA": {"consumer_key": "ck_nope", "consumer_secret": SECRET}}),
        good_secrets(stores={"SA": {"consumer_key": KEY, "consumer_secret": KEY}}),
        good_secrets(stores={"SA": {"consumer_key": KEY}}),
        good_secrets(stores={"ZZ": {"consumer_key": KEY, "consumer_secret": SECRET}}),  # no such store in the file
        good_secrets(stores={"sa": {"consumer_key": KEY, "consumer_secret": SECRET}}),
        good_secrets(s3={"rw": {"access_key_id": "short", "secret_access_key": RW_SECRET}, "ro": None}),
        good_secrets(s3={"rw": {"access_key_id": RW_ID, "secret_access_key": "has space in it 1234"}, "ro": None}),
        good_secrets(s3={"rw": None}),
        good_secrets(s3={"rw": None, "ro": None, "extra": None}),
        good_secrets(github_token="ghp_" + "a" * 36),
        good_secrets(github_token=7),
        good_secrets(extra=1),
        {k: v for k, v in good_secrets().items() if k != "github_token"},
    ]
    for secrets in bad:
        response = import_response(target, file_for(good_payload(secrets=secrets), PASSPHRASE), PASSPHRASE)
        assert (response.status_code, response.json()) == (422, {"error": "export_invalid"})
    assert snapshot(target) == before


def test_an_import_into_an_install_with_a_live_store_is_refused_and_changes_nothing(
    source: Install, target: Install
) -> None:
    text = export_text(source, PASSPHRASE)
    target.client.post("/api/stores", headers=WRITE_HEADERS, json=_store_body())
    before = snapshot(target)
    sets = target.secrets.sets
    response = import_response(target, text, PASSPHRASE)
    assert (response.status_code, response.json()) == (409, {"error": "import_needs_empty"})
    assert snapshot(target) == before and target.secrets.sets == sets  # no secret was even touched


def _store_body() -> dict[str, Any]:
    return new_store_body(code="ZZ", url="https://other.example")


def test_a_removed_store_does_not_block_an_import(source: Install, target: Install) -> None:
    created = target.client.post("/api/stores", headers=WRITE_HEADERS, json=_store_body())
    assert target.client.delete(f"/api/stores/{created.json()['id']}", headers=WRITE_HEADERS).status_code == 204
    assert import_response(target, export_text(source, PASSPHRASE), PASSPHRASE).status_code == 200
    assert [s["code"] for s in target.client.get("/api/stores").json()["stores"]] == ["SA", "SB"]


def test_importing_twice_is_refused_the_second_time(source: Install, target: Install) -> None:
    text = export_text(source)
    assert import_response(target, text).status_code == 200
    assert import_response(target, text).json() == {"error": "import_needs_empty"}
    assert len(rows(target, "store")) == 2


# ---- size limits ----


def test_a_file_text_over_the_1_mib_cap_is_export_invalid(target: Install) -> None:
    assert MAX_FILE_CHARS == 1024 * 1024 and IMPORT_BODY_MAX == 2 * MAX_FILE_CHARS + 64 * 1024
    response = import_response(target, " " * (MAX_FILE_CHARS + 1))
    assert (response.status_code, response.json()) == (422, {"error": "export_invalid"})
    assert rows(target, "store") == []


def test_a_body_over_the_limit_is_refused_before_the_app_reads_it(target: Install) -> None:
    cookie = f"shelfsync_session={target.client.cookies.get('shelfsync_session')}"
    headers = [
        (b"host", b"127.0.0.1:47615"),
        (b"origin", ORIGIN.encode()),
        (b"x-shelfsync", b"1"),
        (b"cookie", cookie.encode()),
        (b"content-type", b"application/json"),
    ]
    too_big = asgi_http(
        target.harness.app, "POST", IMPORT, [*headers, (b"content-length", str(IMPORT_BODY_MAX + 1).encode())]
    )
    assert too_big.status == 422 and json.loads(too_big.body) == {"error": "export_invalid"}
    huge = asgi_http(target.harness.app, "POST", IMPORT, [*headers, (b"content-length", b"9" * 12)])
    assert huge.status == 422
    no_length = asgi_http(target.harness.app, "POST", IMPORT, headers, body=b'{"file":"{}","passphrase":null}')
    assert no_length.status == 422 and json.loads(no_length.body) == {"error": "export_invalid"}  # chunked: no length
    for bad_length in (b"-1", b"1e3", b" 5", b"0x10", b""):
        refused = asgi_http(target.harness.app, "POST", IMPORT, [*headers, (b"content-length", bad_length)], body=b"{}")
        assert refused.status == 422, bad_length
    two = asgi_http(
        target.harness.app, "POST", IMPORT, [*headers, (b"content-length", b"2"), (b"content-length", b"2")], body=b"{}"
    )
    assert two.status == 422
    for refused in (too_big, huge, no_length):
        assert refused.header("content-security-policy") and refused.header("cache-control") == "no-store"


def test_a_session_is_checked_before_the_body_size(target: Install) -> None:
    refused = asgi_http(
        target.harness.app,
        "POST",
        IMPORT,
        [
            (b"host", b"127.0.0.1:47615"),
            (b"origin", ORIGIN.encode()),
            (b"x-shelfsync", b"1"),
            (b"content-length", str(IMPORT_BODY_MAX + 1).encode()),
        ],
    )
    assert refused.status == 401 and json.loads(refused.body) == {"error": "signed_out"}


def test_the_export_body_is_limited_too(source: Install) -> None:
    response = source.client.post(EXPORT, headers=WRITE_HEADERS, json={"passphrase": "x" * 70000})
    assert (response.status_code, response.json()) == (422, {"error": "invalid_request"})


# ---- one derivation at a time ----


def test_while_a_derivation_runs_another_export_or_import_is_busy(source: Install, target: Install) -> None:
    text = export_text(source, PASSPHRASE)
    assert api_backup._KDF_SLOT.acquire(blocking=False)
    try:
        busy = source.client.post(EXPORT, headers=WRITE_HEADERS, json={"passphrase": PASSPHRASE})
        assert (busy.status_code, busy.json()) == (409, {"error": "busy"})
        busy_import = import_response(target, text, PASSPHRASE)
        assert (busy_import.status_code, busy_import.json()) == (409, {"error": "busy"})
        assert source.client.post(EXPORT, headers=WRITE_HEADERS, json={"passphrase": None}).status_code == 200  # no KDF
        plain = import_response(target, export_text(source))  # a plain import parses under the slot too (R2)
        assert (plain.status_code, plain.json()) == (409, {"error": "busy"})
        assert rows(target, "store") == []
    finally:
        api_backup._KDF_SLOT.release()
    assert source.client.post(EXPORT, headers=WRITE_HEADERS, json={"passphrase": PASSPHRASE}).status_code == 200


def test_two_requests_at_once_one_derivation_runs_and_the_other_is_busy(
    source: Install, monkeypatch: pytest.MonkeyPatch
) -> None:
    entered, release = threading.Event(), threading.Event()
    real = backup_crypto.derive_key

    def slow(passphrase: str, salt: bytes) -> bytes:
        entered.set()
        assert release.wait(10)
        return real(passphrase, salt)

    monkeypatch.setattr(backup_crypto, "derive_key", slow)
    first: dict[str, Any] = {}
    other = source.harness.signed_in_client()

    def run() -> None:
        first["response"] = source.client.post(EXPORT, headers=WRITE_HEADERS, json={"passphrase": PASSPHRASE})

    thread = threading.Thread(target=run)
    thread.start()
    try:
        assert entered.wait(10)
        second = other.post(EXPORT, headers=WRITE_HEADERS, json={"passphrase": PASSPHRASE})
        assert (second.status_code, second.json()) == (409, {"error": "busy"})
    finally:
        release.set()
        thread.join(10)
    assert first["response"].status_code == 200
    assert api_backup._KDF_SLOT.acquire(blocking=False)  # released
    api_backup._KDF_SLOT.release()


# ---- a failure half way ----


def test_a_failure_on_any_credential_manager_write_leaves_no_row_and_no_entry(source: Install, tmp_path: Path) -> None:
    text = export_text(source, PASSPHRASE)
    for nth in range(1, 10):  # nine writes in this import
        target = make_install(tmp_path, f"fail{nth}")
        before = snapshot(target)
        target.secrets.fail_set_on = target.secrets.sets + nth
        response = import_response(target, text, PASSPHRASE)
        assert (response.status_code, response.json()) == (503, {"error": "secrets_unavailable"}), nth
        assert snapshot(target) == before, nth
        assert live_store_count_of(target) == 0, nth
    ok = make_install(tmp_path, "ok")
    ok.secrets.fail_set_on = ok.secrets.sets + 10
    assert import_response(ok, text, PASSPHRASE).status_code == 200  # there are exactly nine writes


def live_store_count_of(install: Install) -> int:
    connection = install.open_db()
    try:
        return live_store_count(connection)
    finally:
        connection.close()


def test_a_failure_puts_back_the_s3_pairs_and_the_token_that_were_there(source: Install, tmp_path: Path) -> None:
    text = export_text(source, PASSPHRASE)
    for nth in range(1, 10):
        target = make_install(tmp_path, f"old{nth}")
        target.secrets.set("s3-rw-key-id", "AKIA" + "OLDOLDOLDOLD1234")
        target.secrets.set("s3-rw-secret", "old/Secret+" + "A" * 30)
        target.secrets.set("github-token", "github_pat_" + "old" * 10)
        before = snapshot(target)
        target.secrets.fail_set_on = target.secrets.sets + nth
        assert import_response(target, text, PASSPHRASE).status_code == 503, nth
        assert snapshot(target) == before, nth


def test_a_failed_commit_removes_the_entries_already_written(source: Install, target: Install) -> None:
    text = export_text(source, PASSPHRASE)
    target.secrets.set("github-token", "github_pat_" + "old" * 10)
    before = snapshot(target)
    target.exports._connect = lambda: CommitFails(target.open_db())
    response = import_response(target, text, PASSPHRASE)
    assert (response.status_code, response.json()) == (503, {"error": "backup_failed"})  # R6: no detail in the body
    assert snapshot(target) == before and target.expiry_resets == []


def test_a_credential_manager_that_cant_be_read_stops_an_import_before_anything_is_written(
    source: Install, target: Install
) -> None:
    text = export_text(source, PASSPHRASE)
    before = snapshot(target)
    target.secrets.fail_get = True
    response = import_response(target, text, PASSPHRASE)
    assert (response.status_code, response.json()) == (503, {"error": "secrets_unavailable"})
    target.secrets.fail_get = False
    assert snapshot(target) == before


def test_a_failure_to_delete_while_undoing_is_only_a_warning(
    source: Install, target: Install, caplog: pytest.LogCaptureFixture
) -> None:
    text = export_text(source, PASSPHRASE)
    target.secrets.fail_set_on = target.secrets.sets + 7  # the second S3 pair's first write fails
    target.secrets.fail_delete = {"s3-rw-key-id"}
    with caplog.at_level(logging.WARNING):
        response = import_response(target, text, PASSPHRASE)
    assert response.status_code == 503
    assert "couldn't be put back" in caplog.text
    for value in secret_values():
        assert value not in caplog.text


def test_a_race_that_inserts_a_clashing_store_is_export_invalid_not_a_500(
    source: Install, target: Install, monkeypatch: pytest.MonkeyPatch
) -> None:
    text = export_text(source, PASSPHRASE)
    target.client.post(
        "/api/stores", headers=WRITE_HEADERS, json=_store_body() | {"code": "SA", "url": "https://x.example"}
    )
    monkeypatch.setattr(api_backup, "live_store_count", lambda connection: 0)  # the check passed, then a store arrived
    before = snapshot(target)
    response = import_response(target, text, PASSPHRASE)
    assert (response.status_code, response.json()) == (422, {"error": "export_invalid"})
    assert snapshot(target) == before


# ---- the lock ----


def test_an_import_waits_for_a_storage_key_write_in_progress(source: Install, target: Install) -> None:
    text = export_text(source, PASSPHRASE)
    done = threading.Event()
    result: dict[str, Any] = {}

    def run() -> None:
        result["response"] = import_response(target, text, PASSPHRASE)
        done.set()

    with target.storage.lock:  # a storage write holds the lock
        thread = threading.Thread(target=run)
        thread.start()
        assert not done.wait(0.5)  # the import is parsed and decrypted, and waits here for the lock
        assert rows(target, "store") == []
    thread.join(10)
    assert result["response"].status_code == 200


def test_an_export_waits_for_a_storage_key_write_in_progress(source: Install) -> None:
    done = threading.Event()

    def run() -> None:
        export_text(source, PASSPHRASE)
        done.set()

    with source.storage.lock:
        thread = threading.Thread(target=run)
        thread.start()
        assert not done.wait(0.5)
    thread.join(10)
    assert done.is_set()


# ---- the passphrase is never kept or logged ----


def test_the_passphrase_is_masked_while_the_request_runs_and_forgotten_after(
    source: Install, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str] = []
    real = backup_crypto.derive_key

    def watching(passphrase: str, salt: bytes) -> bytes:
        seen.append(redact(f"during: {passphrase}"))
        return real(passphrase, salt)

    monkeypatch.setattr(backup_crypto, "derive_key", watching)
    export_text(source, PASSPHRASE)
    assert seen == ["during: [redacted]"]
    assert redact(PASSPHRASE) == PASSPHRASE  # no longer registered


def test_no_flow_logs_the_passphrase_or_any_secret(
    source: Install, target: Install, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        text = export_text(source, PASSPHRASE)
        import_response(target, text, "wrong passphrase!!")
        import_response(target, text, None)
        import_response(target, "garbage", None)
        assert import_response(target, text, PASSPHRASE).status_code == 200
        import_response(target, text, PASSPHRASE)
    logged = caplog.text
    assert "wrong passphrase!!" not in logged and PASSPHRASE not in logged
    for value in secret_values():
        assert value not in logged
    assert "A backup file was imported" in logged


# ---- the guard, the route walk ----


def test_the_two_routes_exist_and_nothing_else_is_backup(source: Install) -> None:
    routes = {(m, p) for m, p in api_routes(source.harness.app) if p.startswith("/api/backup")}
    assert routes == {("POST", EXPORT), ("POST", IMPORT)}


def test_both_routes_need_a_session_origin_and_the_csrf_header(source: Install) -> None:
    anonymous = source.harness.client()
    for path in (EXPORT, IMPORT):
        body = {"passphrase": None} if path == EXPORT else {"file": "{}", "passphrase": None}
        response = anonymous.post(path, headers=WRITE_HEADERS, json=body)
        assert (response.status_code, response.json()) == (401, {"error": "signed_out"})
        for headers in ({}, {"X-ShelfSync": "1"}, {"Origin": "http://evil.example", "X-ShelfSync": "1"}):
            assert source.client.post(path, headers=headers, json=body).status_code == 403
        assert source.client.get(path).status_code == 405


def test_the_default_app_has_an_in_memory_export_service() -> None:
    client = make_harness().signed_in_client()
    response = client.post(EXPORT, headers=WRITE_HEADERS, json={"passphrase": None})
    assert response.status_code == 200 and response.json()["payload"]["stores"] == []
    assert isinstance(ExportService.development(), ExportService)
