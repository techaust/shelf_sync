"""Secret storage behind a small interface (06 section 3, SYS-03, SET-06).

`KeyringSecretStore` is the Windows Credential Manager adapter. `MemorySecretStore` is the fake that every test
outside the `windows` marker, and the Linux CI, uses. Neither ever puts a secret into an error message.
"""

import sys
import threading
from typing import Protocol

SERVICE_NAME = "ShelfSync"  # the Credential Manager service name; each secret is one entry under it


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
    import keyring
    import keyring.errors

    class KeyringSecretStore:
        """Windows Credential Manager through keyring 25.7.0: one entry per secret, under one service name.

        Only the entries this adapter is asked about are touched. Any keyring failure becomes a
        `SecretStoreError` that names the failure type and nothing else, so no value or backend detail can leak
        into a log line.
        """

        def __init__(self, service: str = SERVICE_NAME) -> None:
            self._service = service

        def get(self, name: str) -> str | None:
            try:
                return keyring.get_password(self._service, name)  # None when there is no such entry
            except Exception as error:
                raise SecretStoreError(f"Credential Manager read failed ({type(error).__name__})") from None

        def set(self, name: str, value: str) -> None:
            try:
                keyring.set_password(self._service, name, value)
            except Exception as error:
                raise SecretStoreError(f"Credential Manager write failed ({type(error).__name__})") from None

        def delete(self, name: str) -> None:
            try:
                keyring.delete_password(self._service, name)
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
