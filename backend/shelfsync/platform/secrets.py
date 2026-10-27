"""Secret storage behind a small interface (06 section 3, SYS-03, SET-06).

`KeyringSecretStore` is the Windows Credential Manager adapter. `MemorySecretStore` is the fake that every test
outside the `windows` marker, and the Linux CI, uses. Neither ever puts a secret into an error message.
"""

import logging
import sys
import threading
from typing import Protocol

_log = logging.getLogger("shelfsync.secrets")

SERVICE_NAME = "ShelfSync"  # the Credential Manager service name; each secret is one entry under it

INSTALL_TOKEN_ENTRY = "install-token"  # nosec B105
# Every Credential Manager entry ShelfSync owns, under SERVICE_NAME. The uninstaller's "Remove my data" removes exactly
# these (`shelfsync.uninstall`), so a new secret (the GitHub token of the updater, M2's keys) is added here and nowhere
# else; deleting one that was never stored is not an error. The per-store entries (`store-<id>-key` and
# `store-<id>-secret`) aren't fixed names: "Remove my data" adds them from the database
# (`uninstall.store_secret_names`).
OWNED_SECRET_NAMES: tuple[str, ...] = (
    INSTALL_TOKEN_ENTRY,
    "github-token",
    # the S3 keys (M2.3): one read-and-write pair for daily use, one read-only pair
    "s3-rw-key-id",
    "s3-rw-secret",
    "s3-ro-key-id",
    "s3-ro-secret",
)


class SecretStoreError(Exception):
    """A secret store couldn't be read or written. The message never holds a secret value."""


class SecretStore(Protocol):
    def get(self, name: str) -> str | None:
        """The stored value, or None if there is none."""
        ...

    def set(self, name: str, value: str) -> None:
        """Store the value, replacing any earlier one."""
        ...

    def delete(self, name: str) -> None:
        """Remove the entry. Removing one that doesn't exist is not an error."""
        ...


class MemorySecretStore:
    """In-memory fake. Thread-safe, nothing is persisted."""

    def __init__(self) -> None:
        self._values: dict[str, str] = {}
        self._lock = threading.Lock()

    def get(self, name: str) -> str | None:
        with self._lock:
            return self._values.get(name)

    def set(self, name: str, value: str) -> None:
        with self._lock:
            self._values[name] = value

    def delete(self, name: str) -> None:
        with self._lock:
            self._values.pop(name, None)


if sys.platform == "win32":
    import keyring.errors
    from keyring.backend import KeyringBackend
    from keyring.backends.Windows import WinVaultKeyring

    class KeyringSecretStore:
        """Windows Credential Manager through keyring 25.7.0: one entry per secret, under one service name.

        It uses its own `WinVaultKeyring()` instance, never keyring's process-wide backend, so no other backend
        (and no keyring configuration file or environment setting) can be picked in its place.

        Entries are kept "local machine" (they never roam with a roaming profile); `persist` is set after the backend
        is built, so no `KEYRING_PROPERTY_*` environment variable can change it. `set` writes the new value, then
        removes the `<name>@<service>` copy of the old one that keyring's `set_password` leaves behind.

        Only the entries this adapter is asked about are touched. Any keyring failure becomes a
        `SecretStoreError` that names the failure type and nothing else, so no value or backend detail can leak
        into a log line.
        """

        def __init__(self, service: str = SERVICE_NAME) -> None:
            self._service = service
            # keyring's WinVaultKeyring class is untyped; the base class gives the three methods their types
            backend = WinVaultKeyring()  # type: ignore[no-untyped-call]
            backend.persist = "local machine"  # after construction: the environment can't override it
            self._backend: KeyringBackend = backend

        def get(self, name: str) -> str | None:
            try:
                return self._backend.get_password(self._service, name)  # None when there is no such entry
            except Exception as error:
                raise SecretStoreError(f"Credential Manager read failed ({type(error).__name__})") from None

        def set(self, name: str, value: str) -> None:
            try:
                self._backend.set_password(self._service, name, value)  # writes first: a failure keeps the old value
            except Exception as error:
                raise SecretStoreError(f"Credential Manager write failed ({type(error).__name__})") from None
            self._remove_leftover_copy(name)

        def _remove_leftover_copy(self, name: str) -> None:
            """keyring's `set_password` first re-saves the entry it replaces as `<name>@<service>`; remove that copy
            of the old value, and only that one (R1: delete after the write, so a failed write never leaves no
            token). A failure here is logged, never raised: the new value is already stored."""
            target = f"{name}@{self._service}"
            try:
                leftover = self._backend._read_credential(target)  # type: ignore[attr-defined]
                if leftover is not None and leftover["UserName"] == name:
                    self._backend._delete_password(target)  # type: ignore[attr-defined]
            except Exception as error:
                _log.warning(
                    "Credential Manager: couldn't remove the old copy of a replaced entry (%s)", type(error).__name__
                )

        def delete(self, name: str) -> None:
            try:
                self._backend.delete_password(self._service, name)
            except keyring.errors.PasswordDeleteError:
                # keyring raises this when no entry was deleted. Fine if it's gone; an error if it's still there.
                if self.get(name) is not None:
                    raise SecretStoreError("Credential Manager delete failed (PasswordDeleteError)") from None
            except Exception as error:
                raise SecretStoreError(f"Credential Manager delete failed ({type(error).__name__})") from None

else:

    class KeyringSecretStore:
        """Credential Manager exists on Windows only. Here every use reports that, so nothing silently falls back
        to a weaker store."""

        def __init__(self, service: str = SERVICE_NAME) -> None:
            raise SecretStoreError("Credential Manager is available on Windows only")

        def get(self, name: str) -> str | None:
            raise SecretStoreError("Credential Manager is available on Windows only")

        def set(self, name: str, value: str) -> None:
            raise SecretStoreError("Credential Manager is available on Windows only")

        def delete(self, name: str) -> None:
            raise SecretStoreError("Credential Manager is available on Windows only")


def default_secret_store() -> SecretStore:
    """The store the running app uses: Credential Manager. Raises SecretStoreError off Windows."""
    return KeyringSecretStore()
