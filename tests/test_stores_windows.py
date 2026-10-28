"""SET-01, 06 section 3, R9: three stores' key pairs (six entries) in the real Windows Credential Manager, under a
THROWAWAY service name: set, read, replace and delete each, and nothing left behind. Run on purpose with
`uv run pytest -m windows --no-cov` (and by the owner in Windows PowerShell outside the Claude app)."""

import sys
import uuid
from collections.abc import Iterator

import pytest

from shelfsync.platform.secrets import KeyringSecretStore
from shelfsync.secure.credentials import StoreCredentials, entry_names
from tests.store_support import KEY, KEY_2, SECRET, SECRET_2

pytestmark = [pytest.mark.windows, pytest.mark.skipif(sys.platform != "win32", reason="Windows only")]

STORE_IDS = (1, 2, 12)  # a two-digit id too: the names are compound


@pytest.fixture
def credential_manager() -> Iterator[KeyringSecretStore]:
    store = KeyringSecretStore(service=f"ShelfSyncTest-{uuid.uuid4().hex}")
    try:
        yield store
    finally:  # whatever the test did, no throwaway entry stays
        for store_id in STORE_IDS:
            for name in entry_names(store_id):
                store.delete(name)


def test_six_entries_are_set_read_replaced_and_deleted_and_nothing_is_left(
    credential_manager: KeyringSecretStore,
) -> None:
    credentials = StoreCredentials(credential_manager)
    for store_id in STORE_IDS:
        credentials.save(store_id, KEY, SECRET)
    for store_id in STORE_IDS:
        assert credentials.read(store_id) == (KEY, SECRET)
        pair = credentials.pair(store_id)
        assert pair is not None and pair.consumer_key == KEY
    assert credentials.masks(12) == (f"ck_••••{KEY[-4:]}", f"cs_••••{SECRET[-4:]}", True)

    credentials.save(2, KEY_2, SECRET_2)  # replaced, not duplicated; the others are untouched
    assert credentials.read(2) == (KEY_2, SECRET_2)
    assert credentials.read(1) == (KEY, SECRET) and credentials.read(12) == (KEY, SECRET)

    for store_id in STORE_IDS:
        credentials.delete(store_id)
    for store_id in STORE_IDS:
        assert credentials.read(store_id) == (None, None)
        for name in entry_names(store_id):
            assert credential_manager.get(name) is None
    credentials.delete(1)  # removing what is gone is not an error
