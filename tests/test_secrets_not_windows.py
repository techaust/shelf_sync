"""SYS-03: off Windows there is no Credential Manager, and nothing quietly falls back to a weaker store.

These run on the Linux CI only (keyring isn't installed there); on Windows they are skipped.
"""

import sys

import pytest

from shelfsync.platform.secrets import KeyringSecretStore, SecretStoreError, default_secret_store

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the Windows adapter is tested by the windows checks")


def test_the_adapter_refuses_to_exist_off_windows() -> None:
    """SYS-03."""
    with pytest.raises(SecretStoreError):
        KeyringSecretStore()


def test_the_default_store_off_windows_is_an_error_not_a_fallback() -> None:
    """SYS-03: start-up then fails with exit 3 instead of running with a token kept somewhere weaker."""
    with pytest.raises(SecretStoreError):
        default_secret_store()
