"""The install token (SYS-03, SET-06, 06 section 2): 32 random bytes made on first run, kept in Credential Manager.

It is only ever sent in an `Authorization: Bearer` header to `POST /api/session/ticket`, never in a URL, and it is
registered with `redact` the moment it is loaded or reset.
"""

import hmac
import secrets
import threading

from shelfsync.platform.secrets import SecretStore
from shelfsync.secure.redact import register_secret

INSTALL_TOKEN_NAME = "install-token"
_TOKEN_BYTES = 32
MIN_TOKEN_LENGTH = 32  # a stored value shorter than this (edited by hand, damaged) is not trusted and is replaced


def _new_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


def load_or_create_install_token(store: SecretStore) -> str:
    """The stored install token; made and stored first if there is none. Registers it with `redact`."""
    token = store.get(INSTALL_TOKEN_NAME)
    if token is None or len(token) < MIN_TOKEN_LENGTH:
        token = _new_token()
        store.set(INSTALL_TOKEN_NAME, token)
    register_secret(token)
    return token


def reset_install_token(store: SecretStore) -> str:
    """Make and store a new install token (the old one stops working). Registers the new one with `redact`.

    The old value stays registered: it is still a secret if it turns up in a log.
    """
    token = _new_token()
    store.set(INSTALL_TOKEN_NAME, token)
    register_secret(token)
    return token


def verify_install_token(presented: str, expected: str) -> bool:
    """Constant-time comparison on UTF-8 bytes, so a non-ASCII value is simply False (`hmac.compare_digest` raises
    TypeError for a non-ASCII `str`)."""
    return hmac.compare_digest(presented.encode("utf-8", "surrogatepass"), expected.encode("utf-8", "surrogatepass"))


class InstallToken:
    """The running app's copy of the install token, read from the store once and replaced on reset."""

    def __init__(self, store: SecretStore) -> None:
        self._store = store
        self._lock = threading.Lock()
        self._token = load_or_create_install_token(store)

    def matches(self, presented: str) -> bool:
        with self._lock:
            expected = self._token
        return verify_install_token(presented, expected)

    def reset(self) -> None:
        """Make a new token. If the store fails the old token stays in force and the error is raised."""
        new_token = reset_install_token(self._store)
        with self._lock:
            self._token = new_token
