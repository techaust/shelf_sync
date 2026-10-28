"""SET-02, 06 section 3, R9: the four S3 entries in the real Windows Credential Manager, under a THROWAWAY service name:
set, read, replace, delete, and nothing left behind. Run on purpose with `uv run pytest -m windows --no-cov` (and by the
owner in Windows PowerShell outside the Claude app). The values are made up; no S3 call is made."""

import sys
import uuid
from collections.abc import Iterator

import pytest

from shelfsync.platform.secrets import KeyringSecretStore
from shelfsync.secure.credentials import S3Credentials, mask_s3_key_id, mask_s3_secret, s3_entries
from tests.storage_support import RO_ID, RO_SECRET, RW_ID, RW_ID_2, RW_SECRET, RW_SECRET_2

pytestmark = [pytest.mark.windows, pytest.mark.skipif(sys.platform != "win32", reason="Windows only")]


@pytest.fixture
def credential_manager() -> Iterator[KeyringSecretStore]:
    store = KeyringSecretStore(service=f"ShelfSyncTest-{uuid.uuid4().hex}")
    try:
        yield store
    finally:  # whatever the test did, no throwaway entry stays
        for slot in ("rw", "ro"):
            for name in s3_entries(slot):
                store.delete(name)


def test_four_entries_are_set_read_replaced_and_deleted_and_nothing_is_left(
    credential_manager: KeyringSecretStore,
) -> None:
    credentials = S3Credentials(credential_manager)
    credentials.save("rw", RW_ID, RW_SECRET)
    credentials.save("ro", RO_ID, RO_SECRET)
    assert credentials.read("rw") == (RW_ID, RW_SECRET) and credentials.read("ro") == (RO_ID, RO_SECRET)
    pair = credentials.pair("ro")
    assert pair is not None and pair.key_id == RO_ID
    assert credentials.masked("rw") == (mask_s3_key_id(RW_ID), mask_s3_secret(RW_SECRET))

    credentials.save("rw", RW_ID_2, RW_SECRET_2)  # replaced, not duplicated; the other pair is untouched
    assert credentials.read("rw") == (RW_ID_2, RW_SECRET_2)
    assert credentials.read("ro") == (RO_ID, RO_SECRET)

    for slot in ("rw", "ro"):
        credentials.delete(slot)
    for slot in ("rw", "ro"):
        assert credentials.read(slot) == (None, None)
        for name in s3_entries(slot):
            assert credential_manager.get(name) is None
    credentials.delete("rw")  # removing what is gone is not an error
