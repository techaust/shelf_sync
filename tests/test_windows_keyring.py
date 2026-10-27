"""SYS-03, SET-06: the Windows Credential Manager adapter, against the real Credential Manager.

These run only on Windows (`-m windows`). They touch one throwaway service name per test, `ShelfSync-test-<random>`,
and remove what they wrote in `finally`. Nothing else in Credential Manager is read, listed or changed: not the
real `ShelfSync` service, and no other program's entries.
"""

import secrets
import sys
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

pytestmark = [
    pytest.mark.windows,
    pytest.mark.skipif(sys.platform != "win32", reason="Windows Credential Manager"),
]

if sys.platform == "win32":
    from shelfsync.platform.secrets import SERVICE_NAME, KeyringSecretStore, SecretStoreError, default_secret_store
    from shelfsync.secure.redact import clear_secrets, redact
    from shelfsync.secure.token import INSTALL_TOKEN_NAME, load_or_create_install_token, reset_install_token


@contextmanager
def throwaway_store(names: list[str]) -> Iterator["KeyringSecretStore"]:
    """A store under a one-off service name; the given entry names are always deleted afterwards."""
    store = KeyringSecretStore(f"ShelfSync-test-{secrets.token_hex(6)}")
    try:
        yield store
    finally:
        for name in names:
            store.delete(name)


def test_set_get_replace_and_delete_one_entry() -> None:
    """SYS-03: the adapter round-trips a value and removes it."""
    name = "check"
    with throwaway_store([name]) as store:
        assert store.get(name) is None
        store.set(name, "first-" + secrets.token_urlsafe(8))
        value = "second-" + secrets.token_urlsafe(8)
        store.set(name, value)  # replaces
        assert store.get(name) == value
        store.delete(name)
        assert store.get(name) is None  # gone, and nothing else with it to confirm


def test_a_missing_entry_returns_none_and_deleting_it_is_quiet() -> None:
    """SYS-03: keyring returns None for a missing entry; delete of a missing one is not an error."""
    with throwaway_store(["nothing-here"]) as store:
        assert store.get("nothing-here") is None
        store.delete("nothing-here")
        assert store.get("nothing-here") is None


def test_the_install_token_loaded_twice_is_the_same_and_a_reset_changes_it() -> None:
    """SYS-03, SET-06: through the real Credential Manager under the throwaway service name."""
    clear_secrets()
    with throwaway_store([INSTALL_TOKEN_NAME]) as store:
        first = load_or_create_install_token(store)
        assert load_or_create_install_token(store) == first
        assert store.get(INSTALL_TOKEN_NAME) == first
        second = reset_install_token(store)
        assert second != first
        assert load_or_create_install_token(store) == second
        assert redact(f"x {second} y") == "x [redacted] y"


def test_a_keyring_failure_becomes_a_secret_store_error_without_the_message() -> None:
    """SYS-03: only the failure type reaches the error; a value in the original message does not. Nothing in
    Credential Manager is touched: the backend is replaced by one that fails."""
    leaked = "c" + "k_" + "0123456789abcdef" * 3

    class Failing:
        def get_password(self, service: str, username: str) -> str | None:
            raise RuntimeError(f"read failed for {leaked}")

        def set_password(self, service: str, username: str, password: str) -> None:
            raise RuntimeError(f"write failed for {password}")

        def delete_password(self, service: str, username: str) -> None:
            raise RuntimeError(f"delete failed for {leaked}")

    store = KeyringSecretStore(f"ShelfSync-test-{secrets.token_hex(6)}")
    store._backend = Failing()  # type: ignore[assignment]
    for call in (lambda: store.get("a"), lambda: store.set("a", leaked), lambda: store.delete("a")):
        with pytest.raises(SecretStoreError) as caught:
            call()
        assert leaked not in str(caught.value)
        assert "RuntimeError" in str(caught.value)
        assert caught.value.__cause__ is None and caught.value.__suppress_context__


def test_the_app_store_is_credential_manager_under_the_shelfsync_service_name() -> None:
    """SYS-03: constructing it reads nothing."""
    store = default_secret_store()
    assert isinstance(store, KeyringSecretStore)
    assert store._service == SERVICE_NAME == "ShelfSync"


def test_replacing_a_value_leaves_no_copy_of_the_old_one_behind() -> None:
    """SET-06: keyring's own set_password would re-save the old value under `<name>@<service>`; the adapter deletes
    first, so after two sets only the second value exists in Credential Manager under this throwaway service."""
    name = "replaced"
    with throwaway_store([name]) as store:
        service = store._service
        first, second = "first-" + secrets.token_urlsafe(8), "second-" + secrets.token_urlsafe(8)
        store.set(name, first)
        store.set(name, second)
        assert store.get(name) == second
        assert store._backend._read_credential(f"{name}@{service}") is None  # type: ignore[attr-defined]
        current = store._backend._read_credential(service)  # type: ignore[attr-defined]
        assert current is not None and current.value == second


def test_entries_are_kept_on_this_machine_even_if_the_environment_asks_otherwise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SYS-03: persistence is "local machine" (Persist == 2), set after construction, so KEYRING_PROPERTY_PERSIST
    can't change it."""
    monkeypatch.setenv("KEYRING_PROPERTY_PERSIST", "enterprise")
    name = "persisted"
    with throwaway_store([name]) as store:
        store.set(name, "value-" + secrets.token_urlsafe(8))
        entry = store._backend._read_credential(store._service)  # type: ignore[attr-defined]
        assert entry is not None and entry["Persist"] == 2  # CRED_PERSIST_LOCAL_MACHINE
