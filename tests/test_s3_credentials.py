"""SET-02, 06 section 3: the four S3 secrets in Credential Manager (entry names, masks, atomic pairs), their
registration with the log redaction when stored and at start-up, and "Remove my data"."""

import logging
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from shelfsync import server, uninstall
from shelfsync.db.connection import connect
from shelfsync.db.migrate import migrate
from shelfsync.paths import DataPaths
from shelfsync.platform.notify import FakeNotifier
from shelfsync.platform.secrets import OWNED_SECRET_NAMES, MemorySecretStore, SecretStoreError
from shelfsync.secure.credentials import (
    S3_KEY_ID,
    S3_SECRET,
    S3Credentials,
    is_valid_s3_pair,
    mask_s3_key_id,
    mask_s3_secret,
    s3_entries,
)
from shelfsync.secure.redact import MASK, redact
from shelfsync.tray.instance import FakeInstanceLock
from tests.storage_support import RO_ID, RO_SECRET, RW_ID, RW_ID_2, RW_SECRET, RW_SECRET_2
from tests.store_support import FailingSecretStore
from tests.test_server import RecordingServe
from tests.test_uninstall import make_data

DOTS = "••••"


def test_the_four_entry_names_are_owned_and_follow_the_slot() -> None:
    assert s3_entries("rw") == ("s3-rw-key-id", "s3-rw-secret")
    assert s3_entries("ro") == ("s3-ro-key-id", "s3-ro-secret")
    for name in (*s3_entries("rw"), *s3_entries("ro")):
        assert name in OWNED_SECRET_NAMES


def test_the_shapes() -> None:
    assert is_valid_s3_pair(RW_ID, RW_SECRET) and is_valid_s3_pair("A" * 16, "a" * 16)
    assert not is_valid_s3_pair(RW_SECRET, RW_ID)  # the secret has characters a key ID may not
    assert not is_valid_s3_pair("A" * 15, RW_SECRET) and not is_valid_s3_pair(RW_ID, "a" * 15)
    assert not is_valid_s3_pair(RW_ID + "\n", RW_SECRET) and not is_valid_s3_pair(RW_ID, RW_SECRET + "\n")
    assert S3_KEY_ID.fullmatch("A" * 128) and not S3_KEY_ID.fullmatch("A" * 129)
    assert S3_SECRET.fullmatch("a/+=" * 32) and not S3_SECRET.fullmatch("a" * 129)


def test_a_key_id_mask_is_the_first_four_dots_and_the_last_four_whatever_the_length() -> None:
    assert mask_s3_key_id(RW_ID) == f"{RW_ID[:4]}{DOTS}{RW_ID[-4:]}"
    assert len(mask_s3_key_id("A" * 16) or "") == len(mask_s3_key_id("A" * 128) or "") == 12
    assert mask_s3_key_id(None) is None
    assert mask_s3_key_id("short") == DOTS  # can't happen for a validated value; never a tail of a short one


def test_a_secret_mask_is_dots_and_the_last_four_and_a_short_secret_shows_no_tail() -> None:
    assert mask_s3_secret(RW_SECRET) == f"{DOTS}{RW_SECRET[-4:]}"
    assert mask_s3_secret("a" * 31) == DOTS  # below an AWS secret's length: nothing of it shows
    assert mask_s3_secret("a" * 32) == f"{DOTS}aaaa"
    assert len(mask_s3_secret("a" * 40) or "") == len(mask_s3_secret("a" * 128) or "")
    assert mask_s3_secret(None) is None
    assert RW_SECRET[:1] not in (mask_s3_secret(RW_SECRET) or "")[:4]  # no leading characters of the secret


@given(st.from_regex(r"[A-Za-z0-9]{16,128}", fullmatch=True), st.from_regex(r"[A-Za-z0-9/+=]{16,128}", fullmatch=True))
def test_a_mask_never_holds_the_value_and_has_a_fixed_width(key_id: str, secret: str) -> None:
    masked_id, masked_secret = mask_s3_key_id(key_id), mask_s3_secret(secret)
    assert masked_id is not None and masked_secret is not None
    assert key_id not in masked_id and secret not in masked_secret
    assert len(masked_id) == 12 and len(masked_secret) in (4, 8)
    assert masked_secret.startswith(DOTS) and masked_id[4:8] == DOTS


def test_save_registers_both_values_for_redaction_and_reads_back() -> None:
    secrets = MemorySecretStore()
    credentials = S3Credentials(secrets)
    credentials.save("rw", RW_ID, RW_SECRET)
    assert secrets.get("s3-rw-key-id") == RW_ID and secrets.get("s3-rw-secret") == RW_SECRET
    assert credentials.read("ro") == (None, None)
    pair = credentials.pair("rw")
    assert pair is not None and (pair.key_id, pair.secret) == (RW_ID, RW_SECRET)
    assert credentials.masked("rw") == (mask_s3_key_id(RW_ID), mask_s3_secret(RW_SECRET))
    assert redact(f"{RW_ID} {RW_SECRET}") == f"{MASK} {MASK}"


def test_a_value_is_registered_even_when_the_write_then_fails() -> None:
    secrets = FailingSecretStore()
    secrets.fail_set_on = 1
    with pytest.raises(SecretStoreError, match="write failed"):
        S3Credentials(secrets).save("rw", RW_ID, RW_SECRET)
    assert redact(RW_ID) == MASK and redact(RW_SECRET) == MASK


@pytest.mark.parametrize("fail_on", [1, 2])
def test_a_failed_first_save_leaves_neither_entry(fail_on: int) -> None:
    secrets = FailingSecretStore()
    secrets.fail_set_on = fail_on
    with pytest.raises(SecretStoreError):
        S3Credentials(secrets).save("rw", RW_ID, RW_SECRET)
    assert secrets.get("s3-rw-key-id") is None and secrets.get("s3-rw-secret") is None


def test_a_failed_second_write_puts_the_old_pair_back_and_a_failed_put_back_only_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secrets = FailingSecretStore()
    credentials = S3Credentials(secrets)
    credentials.save("rw", RW_ID, RW_SECRET)
    secrets.fail_set_on = secrets.sets + 2
    with pytest.raises(SecretStoreError, match="write failed"):
        credentials.save("rw", RW_ID_2, RW_SECRET_2)
    assert credentials.read("rw") == (RW_ID, RW_SECRET)
    # the put-back itself fails (the store went away): the error is still the write's, and nothing leaks into the log
    secrets.fail_set_on = secrets.sets + 2  # the second write fails, and so does the first put-back's set
    secrets.fail_delete = {"s3-rw-key-id", "s3-rw-secret"}
    caplog.set_level(logging.WARNING)
    with pytest.raises(SecretStoreError, match="write failed"):
        credentials.save("rw", RW_ID_2, RW_SECRET_2)
    assert RW_ID not in caplog.text and RW_SECRET not in caplog.text and RW_SECRET_2 not in caplog.text


def test_the_other_slot_is_never_touched() -> None:
    secrets = FailingSecretStore()
    credentials = S3Credentials(secrets)
    credentials.save("ro", RO_ID, RO_SECRET)
    secrets.fail_set_on = secrets.sets + 2
    with pytest.raises(SecretStoreError):
        credentials.save("rw", RW_ID, RW_SECRET)
    credentials.delete("rw")
    assert credentials.read("ro") == (RO_ID, RO_SECRET)


def test_delete_removes_both_and_a_failed_second_delete_restores_the_first() -> None:
    secrets = FailingSecretStore()
    credentials = S3Credentials(secrets)
    credentials.save("rw", RW_ID, RW_SECRET)
    secrets.fail_delete = {"s3-rw-secret"}
    with pytest.raises(SecretStoreError, match="delete failed"):
        credentials.delete("rw")
    assert credentials.read("rw") == (RW_ID, RW_SECRET)
    secrets.fail_delete = set()
    credentials.delete("rw")
    assert credentials.read("rw") == (None, None)
    credentials.delete("rw")  # deleting what isn't there is not an error


def test_pair_and_masked_survive_an_unreadable_store_and_say_nothing_is_set(caplog: pytest.LogCaptureFixture) -> None:
    secrets = FailingSecretStore()
    credentials = S3Credentials(secrets)
    credentials.save("rw", RW_ID, RW_SECRET)
    secrets.fail_get = True
    caplog.set_level(logging.WARNING)
    assert credentials.pair("rw") is None and credentials.masked("rw") == (None, None)
    assert len(caplog.records) == 2 and RW_ID not in caplog.text and RW_SECRET not in caplog.text


def test_one_missing_entry_means_no_pair() -> None:
    secrets = MemorySecretStore()
    secrets.set("s3-ro-key-id", RO_ID)
    credentials = S3Credentials(secrets)
    assert credentials.pair("ro") is None
    assert credentials.masked("ro") == (mask_s3_key_id(RO_ID), None)


# ---- start-up -------------------------------------------------------------------------------------------------------


def test_register_all_masks_every_stored_value_and_ignores_missing_entries() -> None:
    secrets = MemorySecretStore()
    secrets.set("s3-rw-key-id", RW_ID)
    secrets.set("s3-rw-secret", RW_SECRET)
    secrets.set("s3-ro-key-id", RO_ID)  # half a pair
    S3Credentials(secrets).register_all()
    assert all(redact(value) == MASK for value in (RW_ID, RW_SECRET, RO_ID))
    assert redact(RO_SECRET) != MASK


def test_register_all_warns_once_and_goes_on_when_credential_manager_cannot_be_read(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secrets = FailingSecretStore()
    secrets.fail_get = True
    caplog.set_level(logging.WARNING)
    S3Credentials(secrets).register_all()  # no exception
    assert [r.levelname for r in caplog.records] == ["WARNING"]


def _stored_s3_keys() -> MemorySecretStore:
    secrets = MemorySecretStore()
    for name, value in zip((*s3_entries("rw"), *s3_entries("ro")), (RW_ID, RW_SECRET, RO_ID, RO_SECRET), strict=True):
        secrets.set(name, value)
    return secrets


def test_run_registers_the_stored_s3_keys_before_serving(data_paths: DataPaths) -> None:
    """The real start-up path: `server.run` reads the four entries and masks them before the app is built."""
    serve = RecordingServe()
    assert server.run(data_paths, FakeNotifier(), serve, 0.0, _stored_s3_keys()) == server.EXIT_OK
    assert serve.app is not None
    assert redact(f"{RW_ID} {RW_SECRET} {RO_ID} {RO_SECRET}") == " ".join([MASK] * 4)


def test_run_starts_even_when_the_stored_s3_keys_cannot_be_read(
    data_paths: DataPaths, caplog: pytest.LogCaptureFixture
) -> None:
    class Unreadable(MemorySecretStore):
        def get(self, name: str) -> str | None:
            if name.startswith("s3-"):
                raise SecretStoreError("Credential Manager read failed (Fake)")
            return super().get(name)

    caplog.set_level(logging.WARNING)
    serve = RecordingServe()
    assert server.run(data_paths, FakeNotifier(), serve, 0.0, Unreadable()) == server.EXIT_OK
    assert serve.app is not None
    assert "S3 keys couldn't be read at start-up" in caplog.text


def test_the_running_app_serves_the_storage_routes_on_the_real_database_and_secret_store(
    data_paths: DataPaths,
) -> None:
    """`server.run` wires the storage service to the data folder's database and the secret store it was given."""
    from fastapi.testclient import TestClient

    from tests.storage_support import key_body
    from tests.support import WRITE_HEADERS

    secrets = MemorySecretStore()
    serve = RecordingServe()
    assert server.run(data_paths, FakeNotifier(), serve, 0.0, secrets) == server.EXIT_OK
    assert serve.app is not None and serve.sockname is not None
    port = serve.sockname[1]
    token = secrets.get("install-token")
    assert token
    client = TestClient(serve.app, base_url=f"http://127.0.0.1:{port}")
    ticket = client.post("/api/session/ticket", headers={"Authorization": f"Bearer {token}"}).json()["ticket"]
    headers = {**WRITE_HEADERS, "Origin": f"http://127.0.0.1:{port}"}
    assert client.post("/api/session", json={"ticket": ticket}, headers=headers).status_code == 204
    assert client.put("/api/secrets/s3-ro", json=key_body(RO_ID, RO_SECRET), headers=headers).status_code == 204
    assert secrets.get("s3-ro-key-id") == RO_ID
    body = {
        "s3_endpoint": "",
        "s3_region": "ap-south-1",
        "s3_bucket": "example-bucket",
        "keep_previous_files": 1,
        "download_link_template": '[amazon_s3 object="{key}"]',
    }
    assert client.put("/api/settings/storage", json=body, headers=headers).status_code == 200
    connection = connect(data_paths.database)
    try:
        migrate(connection)
        row = connection.execute("SELECT value_json FROM setting WHERE key = 's3_region'").fetchone()
    finally:
        connection.close()
    assert row is not None and row[0] == '"ap-south-1"'  # it went to the data folder's database


# ---- "Remove my data" -----------------------------------------------------------------------------------------------


def test_remove_data_deletes_the_four_s3_entries(tmp_path: Path) -> None:
    paths = make_data(tmp_path)
    secrets = _stored_s3_keys()
    secrets.set("somebody-else", "keep")
    assert uninstall.remove_data(paths, secrets, FakeInstanceLock(set())) == uninstall.EXIT_OK
    for name in (*s3_entries("rw"), *s3_entries("ro")):
        assert secrets.get(name) is None
    assert secrets.get("somebody-else") == "keep"
