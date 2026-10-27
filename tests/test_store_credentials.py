"""SET-01, 06 section 3: a store's keys in Credential Manager (entry names, masks, atomic pairs), their registration
with the log redaction when stored and at start-up, and the "Remove my data" sweep."""

import logging
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from shelfsync import server, uninstall
from shelfsync.db.connection import connect
from shelfsync.db.migrate import migrate
from shelfsync.paths import DataPaths
from shelfsync.platform.notify import FakeNotifier
from shelfsync.platform.secrets import OWNED_SECRET_NAMES, MemorySecretStore
from shelfsync.secure.credentials import (
    StoreCredentials,
    entry_names,
    is_valid_pair,
    key_entry,
    mask,
    secret_entry,
)
from shelfsync.secure.redact import MASK, redact
from shelfsync.store_service import StoreService
from shelfsync.tray.instance import FakeInstanceLock
from tests.store_support import KEY, KEY_2, SECRET, SECRET_2, FailingSecretStore
from tests.test_server import RecordingServe
from tests.test_uninstall import make_data, make_link

DOTS = "••••"


# ---- names and masks ------------------------------------------------------------------------------------------------


def test_entry_names_use_the_store_id() -> None:
    assert (key_entry(7), secret_entry(7)) == ("store-7-key", "store-7-secret")
    assert entry_names(12) == ("store-12-key", "store-12-secret")


def test_a_mask_is_the_prefix_four_dots_and_the_last_four_whatever_the_length() -> None:
    assert mask(KEY) == f"ck_{DOTS}{KEY[-4:]}"
    assert mask(SECRET) == f"cs_{DOTS}{SECRET[-4:]}"
    assert mask("ck_" + "a" * 64) == f"ck_{DOTS}aaaa"
    assert len(mask("ck_" + "a" * 20) or "") == len(mask("ck_" + "a" * 64) or "")  # the length never shows
    assert mask(None) is None
    assert mask("short") == f"sho{DOTS}"  # a short value shows no tail at all
    assert mask("ck_" + "a" * 19) == f"ck_{DOTS}"  # 22 characters: below the length that shows a tail
    assert mask("ck_" + "a" * 20) == f"ck_{DOTS}aaaa"  # 23: the shortest valid key shows its last four


def test_the_pair_shapes_are_checked() -> None:
    assert is_valid_pair(KEY, SECRET)
    assert not is_valid_pair(SECRET, KEY)
    assert not is_valid_pair(KEY, KEY)
    assert not is_valid_pair("ck_" + "a" * 19, SECRET)
    assert not is_valid_pair(KEY + "\n", SECRET)


# ---- the pair -------------------------------------------------------------------------------------------------------


def test_save_registers_both_values_for_redaction_and_reads_back() -> None:
    secrets = MemorySecretStore()
    credentials = StoreCredentials(secrets)
    credentials.save(3, KEY, SECRET)
    assert secrets.get("store-3-key") == KEY and secrets.get("store-3-secret") == SECRET
    pair = credentials.pair(3)
    assert pair is not None and (pair.consumer_key, pair.consumer_secret) == (KEY, SECRET)
    assert credentials.masked(3) == (f"ck_{DOTS}{KEY[-4:]}", f"cs_{DOTS}{SECRET[-4:]}")
    assert redact(f"{KEY} {SECRET}") == f"{MASK} {MASK}"


def test_a_value_is_registered_even_when_the_write_then_fails() -> None:
    secrets = FailingSecretStore()
    secrets.fail_set_on = 1
    with pytest.raises(Exception, match="write failed"):
        StoreCredentials(secrets).save(1, KEY, SECRET)
    assert redact(KEY) == MASK  # it was in memory, so it must never be loggable


def test_a_failed_second_write_puts_the_old_pair_back() -> None:
    secrets = FailingSecretStore()
    credentials = StoreCredentials(secrets)
    credentials.save(1, KEY, SECRET)
    secrets.fail_set_on = secrets.sets + 2
    with pytest.raises(Exception, match="write failed"):
        credentials.save(1, KEY_2, SECRET_2)
    assert credentials.read(1) == (KEY, SECRET)


def test_a_failed_first_save_leaves_neither_entry() -> None:
    secrets = FailingSecretStore()
    secrets.fail_set_on = 2
    with pytest.raises(Exception, match="write failed"):
        StoreCredentials(secrets).save(1, KEY, SECRET)
    assert secrets.get("store-1-key") is None and secrets.get("store-1-secret") is None


def test_delete_removes_both_and_a_failed_second_delete_restores_the_first() -> None:
    secrets = FailingSecretStore()
    credentials = StoreCredentials(secrets)
    credentials.save(1, KEY, SECRET)
    secrets.fail_delete = {"store-1-secret"}
    with pytest.raises(Exception, match="delete failed"):
        credentials.delete(1)
    assert credentials.read(1) == (KEY, SECRET)
    secrets.fail_delete = set()
    credentials.delete(1)
    assert credentials.read(1) == (None, None)
    credentials.delete(1)  # deleting what isn't there is not an error


def test_discard_is_best_effort() -> None:
    secrets = FailingSecretStore()
    credentials = StoreCredentials(secrets)
    credentials.save(1, KEY, SECRET)
    secrets.fail_delete = {"store-1-key"}
    credentials.discard(1)  # no exception
    assert secrets.get("store-1-key") == KEY and secrets.get("store-1-secret") is None


def test_pair_and_masked_survive_an_unreadable_store_and_say_nothing_is_set(caplog: pytest.LogCaptureFixture) -> None:
    secrets = FailingSecretStore()
    credentials = StoreCredentials(secrets)
    credentials.save(1, KEY, SECRET)
    secrets.fail_get = True
    caplog.set_level(logging.WARNING)
    assert credentials.pair(1) is None and credentials.masked(1) == (None, None)
    assert "Fake" not in caplog.text or KEY not in caplog.text
    assert KEY not in caplog.text and SECRET not in caplog.text


def test_one_missing_entry_means_no_pair() -> None:
    secrets = MemorySecretStore()
    secrets.set("store-1-key", KEY)
    assert StoreCredentials(secrets).pair(1) is None


# ---- start-up -------------------------------------------------------------------------------------------------------


def test_register_all_masks_every_stored_value_and_ignores_missing_entries() -> None:
    secrets = MemorySecretStore()
    secrets.set("store-1-key", KEY)
    secrets.set("store-1-secret", SECRET)
    secrets.set("store-2-key", KEY_2)  # half a pair
    StoreCredentials(secrets).register_all([1, 2, 3])
    assert all(redact(value) == MASK for value in (KEY, SECRET, KEY_2))
    assert redact(SECRET_2) != MASK


def test_register_all_warns_and_goes_on_when_credential_manager_cannot_be_read(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secrets = FailingSecretStore()
    secrets.fail_get = True
    caplog.set_level(logging.WARNING)
    StoreCredentials(secrets).register_all([1, 2])  # no exception
    assert [r.levelname for r in caplog.records] == ["WARNING"]  # one warning, not one per store


def test_the_service_registers_stored_keys_at_start_up_and_warns_when_the_database_cannot_be_read(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secrets = MemorySecretStore()
    secrets.set("store-1-key", KEY)
    secrets.set("store-1-secret", SECRET)
    service = StoreService.in_memory(secrets)
    with closing(service._open()) as connection:
        connection.execute(
            "INSERT INTO store (name, url, code, shape, color, created_at) "
            "VALUES ('S', 'https://a.example', 'SA', 'circle', 'indigo', 'x')"
        )
    service.register_secrets()
    assert redact(KEY) == MASK and redact(SECRET) == MASK

    def broken() -> sqlite3.Connection:
        raise sqlite3.OperationalError("unable to open database file")

    caplog.set_level(logging.WARNING)
    StoreService(open_connection=broken, secrets=secrets).register_secrets()  # no exception
    assert "couldn't be listed" in caplog.text


def test_run_registers_the_keys_of_stores_already_in_the_database(data_paths: DataPaths) -> None:
    """The real start-up path: `server.run` reads every stored store secret and masks it before serving."""
    data_paths.root.mkdir(parents=True)
    conn = connect(data_paths.database)
    migrate(conn)
    conn.execute(
        "INSERT INTO store (name, url, code, shape, color, created_at) "
        "VALUES ('S', 'https://a.example', 'SA', 'circle', 'indigo', 'x')"
    )
    conn.close()
    secrets = MemorySecretStore()
    secrets.set("store-1-key", KEY)
    secrets.set("store-1-secret", SECRET)
    serve = RecordingServe()
    assert server.run(data_paths, FakeNotifier(), serve, 0.0, secrets) == server.EXIT_OK
    assert serve.app is not None
    assert redact(f"{KEY} {SECRET}") == f"{MASK} {MASK}"


def test_run_starts_even_when_the_stored_keys_cannot_be_read(
    data_paths: DataPaths, caplog: pytest.LogCaptureFixture
) -> None:
    data_paths.root.mkdir(parents=True)
    conn = connect(data_paths.database)
    migrate(conn)
    conn.execute(
        "INSERT INTO store (name, url, code, shape, color, created_at) "
        "VALUES ('S', 'https://a.example', 'SA', 'circle', 'indigo', 'x')"
    )
    conn.close()

    class Unreadable(MemorySecretStore):
        def get(self, name: str) -> str | None:
            if name.startswith("store-"):
                from shelfsync.platform.secrets import SecretStoreError

                raise SecretStoreError("Credential Manager read failed (Fake)")
            return super().get(name)

    caplog.set_level(logging.WARNING)
    serve = RecordingServe()
    assert server.run(data_paths, FakeNotifier(), serve, 0.0, Unreadable()) == server.EXIT_OK
    assert serve.app is not None
    assert "couldn't be read at start-up" in caplog.text


# ---- "Remove my data" -----------------------------------------------------------------------------------------------


def test_the_four_s3_names_are_owned_entries_now() -> None:
    for name in ("s3-rw-key-id", "s3-rw-secret", "s3-ro-key-id", "s3-ro-secret", "github-token", "install-token"):
        assert name in OWNED_SECRET_NAMES


def _database_with_stores(paths: DataPaths, ids_removed: tuple[int, ...] = ()) -> None:
    conn = connect(paths.database)
    migrate(conn)
    for number, code in enumerate(("SA", "SB", "SC"), start=1):
        conn.execute(
            "INSERT INTO store (name, url, code, shape, color, created_at, removed_at) "
            "VALUES ('S', ?, ?, 'circle', 'indigo', 'x', ?)",
            (f"https://store-{number}.example", code, "y" if number in ids_removed else None),
        )
    conn.close()


def test_the_store_entry_names_come_from_the_database_removed_stores_included(tmp_path: Path) -> None:
    paths = make_data(tmp_path)
    paths.database.unlink()
    _database_with_stores(paths, ids_removed=(2,))
    assert uninstall.store_secret_names(paths.database) == [
        "store-1-key", "store-1-secret", "store-2-key", "store-2-secret", "store-3-key", "store-3-secret",
    ]  # fmt: skip


def test_no_database_or_an_old_one_has_no_store_entries(tmp_path: Path) -> None:
    assert uninstall.store_secret_names(tmp_path / "nothing.db") == []
    old = tmp_path / "old.db"
    conn = sqlite3.connect(old)
    conn.execute("CREATE TABLE setting (key TEXT PRIMARY KEY, value_json TEXT NOT NULL)")
    conn.close()
    assert uninstall.store_secret_names(old) == []


def test_remove_data_deletes_every_store_entry_and_nothing_else(tmp_path: Path) -> None:
    paths = make_data(tmp_path)
    paths.database.unlink()
    _database_with_stores(paths, ids_removed=(3,))
    secrets = MemorySecretStore()
    for number in (1, 2, 3):
        secrets.set(f"store-{number}-key", KEY)
        secrets.set(f"store-{number}-secret", SECRET)
    for name in OWNED_SECRET_NAMES:
        secrets.set(name, "value")
    secrets.set("store-9-key", "someone else's?")  # an id this database never held: not ours to touch
    secrets.set("somebody-else", "keep")
    assert uninstall.remove_data(paths, secrets, FakeInstanceLock(set())) == uninstall.EXIT_OK
    assert not paths.root.exists()
    for number in (1, 2, 3):
        assert secrets.get(f"store-{number}-key") is None and secrets.get(f"store-{number}-secret") is None
    assert all(secrets.get(name) is None for name in OWNED_SECRET_NAMES)
    assert secrets.get("somebody-else") == "keep" and secrets.get("store-9-key") == "someone else's?"


def test_a_store_entry_that_cannot_be_deleted_is_exit_5(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    paths = make_data(tmp_path)
    paths.database.unlink()
    _database_with_stores(paths)
    secrets = FailingSecretStore()
    secrets.set("store-2-secret", SECRET)
    secrets.fail_delete = {"store-2-secret"}
    assert uninstall.remove_data(paths, secrets, FakeInstanceLock(set())) == uninstall.EXIT_SECRETS
    out = capsys.readouterr().out
    assert "store-2-secret" in out and SECRET not in out
    assert not paths.root.exists()  # the data went anyway


def test_a_database_that_cannot_be_read_uses_the_existing_exit_codes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths = make_data(tmp_path)
    paths.database.write_text("db", encoding="utf-8")  # not a database
    secrets = MemorySecretStore()
    assert uninstall.remove_data(paths, secrets, FakeInstanceLock(set())) == uninstall.EXIT_SECRETS
    assert "Couldn't read the list of stores" in capsys.readouterr().out
    assert not paths.root.exists()


def test_a_database_that_cannot_be_read_and_data_left_behind_is_exit_6(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "shelfsync.db").write_text("db", encoding="utf-8")  # not a database
    link = tmp_path / "ShelfSync"
    if not make_link(link, outside):
        pytest.skip("this account can't make directory links")
    # a data folder that is itself a link is left alone (data left) and the unreadable list adds the token problem
    assert uninstall.remove_data(DataPaths(link), MemorySecretStore(), FakeInstanceLock(set())) == uninstall.EXIT_BOTH
    assert (outside / "shelfsync.db").is_file()
