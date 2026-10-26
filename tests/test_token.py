"""SYS-03, SET-06, LOG-01: the secret store fake and the install token."""

import pytest

from shelfsync.platform.secrets import MemorySecretStore, SecretStoreError
from shelfsync.secure.redact import MASK, redact
from shelfsync.secure.token import (
    INSTALL_TOKEN_NAME,
    MIN_TOKEN_LENGTH,
    InstallToken,
    load_or_create_install_token,
    reset_install_token,
    verify_install_token,
)


def test_memory_store_get_set_delete() -> None:
    """SYS-03: the fake behaves like the Credential Manager adapter (None for a missing entry, quiet delete)."""
    store = MemorySecretStore()
    assert store.get("a") is None
    store.set("a", "one")
    assert store.get("a") == "one"
    store.set("a", "two")
    assert store.get("a") == "two"
    store.delete("a")
    assert store.get("a") is None
    store.delete("a")  # deleting what isn't there is not an error


def test_token_is_created_once_then_the_same_value_is_loaded() -> None:
    """SYS-03: made on first run, kept, loaded again afterwards."""
    store = MemorySecretStore()
    first = load_or_create_install_token(store)
    second = load_or_create_install_token(store)
    assert first == second
    assert store.get(INSTALL_TOKEN_NAME) == first
    assert len(first) >= 43  # 32 random bytes, URL-safe base64


def test_two_stores_get_different_tokens() -> None:
    """SYS-03: the token is random."""
    assert load_or_create_install_token(MemorySecretStore()) != load_or_create_install_token(MemorySecretStore())


def test_reset_gives_a_new_value_and_stores_it() -> None:
    """SET-06: Reset access token makes a new token."""
    store = MemorySecretStore()
    old = load_or_create_install_token(store)
    new = reset_install_token(store)
    assert new != old
    assert store.get(INSTALL_TOKEN_NAME) == new
    assert load_or_create_install_token(store) == new


def test_a_damaged_short_stored_value_is_replaced() -> None:
    """SYS-03: a stored value too short to be a real token is not trusted."""
    store = MemorySecretStore()
    store.set(INSTALL_TOKEN_NAME, "x" * (MIN_TOKEN_LENGTH - 1))
    token = load_or_create_install_token(store)
    assert len(token) >= MIN_TOKEN_LENGTH
    assert store.get(INSTALL_TOKEN_NAME) == token


def test_loading_and_resetting_register_the_token_with_redact() -> None:
    """LOG-01: the token is masked wherever it shows up, from the moment it is loaded or reset."""
    store = MemorySecretStore()
    token = load_or_create_install_token(store)
    assert redact(f"value {token} here") == f"value {MASK} here"
    new = reset_install_token(store)
    assert redact(f"value {new} here") == f"value {MASK} here"
    assert token not in redact(f"old {token}")  # the old one stays registered


def test_verify_accepts_only_the_exact_token() -> None:
    """SYS-03: constant-time comparison; equal means True."""
    assert verify_install_token("abc", "abc") is True
    assert verify_install_token("abd", "abc") is False


@pytest.mark.parametrize(
    "presented",
    ["", "é" * 40, "‮" * 3, "x" * 100_000, "\ud800", "ключ", "abc\x00"],
    ids=["empty", "latin1", "bidi", "very-long", "lone-surrogate", "cyrillic", "nul"],
)
def test_verify_gives_false_never_an_error_for_odd_input(presented: str) -> None:
    """SYS-03: a non-ASCII header must be a 401, never a 500 (hmac.compare_digest raises on non-ASCII str)."""
    assert verify_install_token(presented, "a-real-token-value") is False


def test_verify_with_a_non_ascii_expected_value() -> None:
    assert verify_install_token("é", "é") is True


def _matches(holder: InstallToken, presented: str) -> bool:
    return holder.run_if_matches(presented, lambda: True) is True


def test_install_token_holder_follows_a_reset() -> None:
    """SET-06: after a reset only the new value matches."""
    store = MemorySecretStore()
    holder = InstallToken(store)
    old = store.get(INSTALL_TOKEN_NAME)
    assert old is not None and _matches(holder, old)
    holder.reset()
    new = store.get(INSTALL_TOKEN_NAME)
    assert new is not None and new != old
    assert _matches(holder, new)
    assert not _matches(holder, old)


class _FailingStore:
    def get(self, name: str) -> str | None:
        raise SecretStoreError("boom")

    def set(self, name: str, value: str) -> None:
        raise SecretStoreError("boom")

    def delete(self, name: str) -> None:
        raise SecretStoreError("boom")


def test_a_failed_reset_keeps_the_old_token() -> None:
    """SET-06: if the store can't be written, the old token stays in force."""
    store = MemorySecretStore()
    holder = InstallToken(store)
    old = store.get(INSTALL_TOKEN_NAME)
    assert old is not None
    holder._store = _FailingStore()
    with pytest.raises(SecretStoreError):
        holder.reset()
    assert _matches(holder, old)


def test_run_if_matches_runs_the_action_only_for_the_current_token() -> None:
    """SYS-03: the check and the action happen together."""
    store = MemorySecretStore()
    holder = InstallToken(store)
    token = store.get(INSTALL_TOKEN_NAME)
    assert token is not None
    assert holder.run_if_matches(token, lambda: "ran") == "ran"
    assert holder.run_if_matches("wrong", lambda: "ran") is None
    assert holder.run_if_matches("", lambda: "ran") is None
    assert holder.run_if_matches("é", lambda: "ran") is None


def test_reset_runs_its_follow_up_after_the_new_token_is_in_force() -> None:
    """SET-06: the follow-up (ending every session) sees the new token already stored."""
    store = MemorySecretStore()
    holder = InstallToken(store)
    old = store.get(INSTALL_TOKEN_NAME)
    seen: list[str | None] = []
    holder.reset(then=lambda: seen.append(store.get(INSTALL_TOKEN_NAME)))
    assert seen and seen[0] != old
    assert _matches(holder, seen[0] or "")


def test_a_failed_reset_does_not_run_its_follow_up() -> None:
    """SET-06: if the new token can't be stored, sessions are not ended."""
    store = MemorySecretStore()
    holder = InstallToken(store)
    holder._store = _FailingStore()
    ran: list[bool] = []
    with pytest.raises(SecretStoreError):
        holder.reset(then=lambda: ran.append(True))
    assert ran == []
