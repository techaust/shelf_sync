"""The install token (SYS-03, SET-06, 06 section 2): 32 random bytes made on first run, kept in Credential Manager.

It is only ever sent in an `Authorization: Bearer` header to `POST /api/session/ticket`, never in a URL, and it is
registered with `redact` the moment it is loaded or reset.
"""

import hmac
import secrets
import threading
from collections.abc import Callable

from shelfsync.platform.secrets import INSTALL_TOKEN_ENTRY, SecretStore
from shelfsync.secure.redact import register_secret

# bandit B105 flags the name: this is the name of the Credential Manager entry, not the token
INSTALL_TOKEN_NAME = INSTALL_TOKEN_ENTRY
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
    """The running app's copy of the install token, read from the store once and replaced on reset.

    One lock covers the check of a presented token together with what follows from it (issuing a ticket), and the
    reset together with what must follow it (ending every session). So a reset can never fall between a successful
    check and the ticket it leads to: a token that was valid when it was checked can't get a ticket that outlives
    the reset.
    """

    def __init__(self, store: SecretStore) -> None:
        self._store = store
        self._lock = threading.Lock()
        self._token = load_or_create_install_token(store)

    def run_if_matches[T](self, presented: str, action: Callable[[], T]) -> T | None:
        """Run `action` and return its result if `presented` is the current token, all under the lock; otherwise
        return None."""
        with self._lock:
            if not verify_install_token(presented, self._token):
                return None
            return action()

    def reset(self, then: Callable[[], None] | None = None) -> None:
        """Make a new token, then run `then` (ending every session), all under the lock. If the store fails the old
        token stays in force, `then` doesn't run, and the error is raised."""
        with self._lock:
            self._token = reset_install_token(self._store)
            if then is not None:
                then()
