"""A store's consumer key and secret in Credential Manager (SET-01, 06 section 3).

Each store has two entries under ShelfSync's service, `store-<id>-key` and `store-<id>-secret` (the id is the store
row's, never reused). Keys always travel as a pair. Every value is registered with the log redaction when it is stored
and when it is read at start-up, so it is masked wherever it might end up. Masks show the two-letter prefix, four dots
and the last four characters, and never the length. No message here holds a value.
"""

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass

from shelfsync.platform.secrets import SecretStore, SecretStoreError
from shelfsync.secure.redact import register_secret

_log = logging.getLogger("shelfsync.secrets")

CONSUMER_KEY = re.compile(r"ck_[A-Za-z0-9]{20,64}")
CONSUMER_SECRET = re.compile(r"cs_[A-Za-z0-9]{20,64}")
_DOTS = "••••"
MASK_SHOWS_TAIL_FROM = 23  # a validated key has at least 23 characters (3 + 20), so four shown are never most of it


def key_entry(store_id: int) -> str:
    return f"store-{store_id}-key"


def secret_entry(store_id: int) -> str:
    return f"store-{store_id}-secret"


def entry_names(store_id: int) -> tuple[str, str]:
    return key_entry(store_id), secret_entry(store_id)


def is_valid_pair(consumer_key: str, consumer_secret: str) -> bool:
    return CONSUMER_KEY.fullmatch(consumer_key) is not None and CONSUMER_SECRET.fullmatch(consumer_secret) is not None


def mask(value: str | None) -> str | None:
    """`ck_` + four dots + the last four characters. Fixed width: the length of the value is never shown."""
    if value is None:
        return None
    if len(value) < MASK_SHOWS_TAIL_FROM:  # can't happen for a validated value; never show a tail of a short one
        return f"{value[:3]}{_DOTS}"
    return f"{value[:3]}{_DOTS}{value[-4:]}"


@dataclass(frozen=True)
class KeyPair:
    consumer_key: str
    consumer_secret: str


class StoreCredentials:
    def __init__(self, secrets: SecretStore) -> None:
        self._secrets = secrets

    def read(self, store_id: int) -> tuple[str | None, str | None]:
        """(key, secret), each None when not stored. Raises `SecretStoreError` when the store can't be read."""
        key_name, secret_name = entry_names(store_id)
        return self._secrets.get(key_name), self._secrets.get(secret_name)

    def pair(self, store_id: int) -> KeyPair | None:
        """Both values, or None when either is missing or Credential Manager can't be read."""
        try:
            key, secret = self.read(store_id)
        except SecretStoreError as error:
            _log.warning("The keys of a store couldn't be read (%s)", type(error).__name__)
            return None
        if key is None or secret is None:
            return None
        register_secret(key)  # whatever is read for use is masked in the log from here on, whoever stored it
        register_secret(secret)
        return KeyPair(key, secret)

    def masked(self, store_id: int) -> tuple[str | None, str | None]:
        """What a screen may show: the two masks. A read failure shows both as not set."""
        try:
            key, secret = self.read(store_id)
        except SecretStoreError as error:
            _log.warning("The keys of a store couldn't be read (%s)", type(error).__name__)
            return None, None
        return mask(key), mask(secret)

    def save(self, store_id: int, consumer_key: str, consumer_secret: str) -> None:
        """Write the pair. If the second write fails, the first is put back (or removed if there was none), then
        `SecretStoreError` is raised, so a pair is never half replaced. Both values are registered for redaction first:
        a value that reaches Credential Manager must never be loggable, even if the write fails half way."""
        register_secret(consumer_key)
        register_secret(consumer_secret)
        key_name, secret_name = entry_names(store_id)
        old_key, old_secret = self.read(store_id)
        try:
            self._secrets.set(key_name, consumer_key)
            self._secrets.set(secret_name, consumer_secret)
        except SecretStoreError:
            self._put_back(key_name, old_key)
            self._put_back(secret_name, old_secret)
            raise

    def delete(self, store_id: int) -> None:
        """Remove both entries. If the second removal fails, the first is put back, so nothing changes."""
        key_name, secret_name = entry_names(store_id)
        old_key = self._secrets.get(key_name)
        self._secrets.delete(key_name)
        try:
            self._secrets.delete(secret_name)
        except SecretStoreError:
            self._put_back(key_name, old_key)
            raise

    def discard(self, store_id: int) -> None:
        """Best effort, for rolling back a save that never became a row: remove what was written, ignore failures."""
        for name in entry_names(store_id):
            try:
                self._secrets.delete(name)
            except SecretStoreError as error:
                _log.warning("A stored entry couldn't be cleaned up (%s)", type(error).__name__)

    def register_all(self, store_ids: Iterable[int]) -> None:
        """Start-up: register every stored value with the redaction. A store that can't be read is logged (a warning,
        never the value) and start-up goes on: its test then answers `keys_missing`."""
        for store_id in store_ids:
            try:
                key, secret = self.read(store_id)
            except SecretStoreError as error:
                _log.warning("The stored keys couldn't be read at start-up (%s)", type(error).__name__)
                return  # the store is unreadable as a whole; one warning is enough
            for value in (key, secret):
                if value is not None:
                    register_secret(value)

    def put_back(self, store_id: int, old_key: str | None, old_secret: str | None) -> None:
        """Return the pair to what `read` gave before a `save`, after a failure that came later (best effort)."""
        key_name, secret_name = entry_names(store_id)
        self._put_back(key_name, old_key)
        self._put_back(secret_name, old_secret)

    def _put_back(self, name: str, old: str | None) -> None:
        try:
            if old is None:
                self._secrets.delete(name)
            else:
                self._secrets.set(name, old)
        except SecretStoreError as error:
            _log.warning("A stored entry couldn't be put back (%s)", type(error).__name__)
