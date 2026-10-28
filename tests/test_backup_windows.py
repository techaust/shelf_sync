"""SET-05, 06 section 3, R9: an encrypted export and import through the real Windows Credential Manager, under two
THROWAWAY service names (one per install): every secret travels, and nothing is left behind. Run on purpose with
`uv run pytest -m windows --no-cov` (and by the owner in Windows PowerShell outside the Claude app). The values are made
up; no network call is made."""

import sys
import uuid
from collections.abc import Iterator

import pytest

from shelfsync.platform.secrets import OWNED_SECRET_NAMES, KeyringSecretStore
from shelfsync.secure import backup_crypto
from shelfsync.secure.credentials import S3Credentials, StoreCredentials, entry_names
from tests.backup_support import FAST_N, GITHUB_TOKEN, PASSPHRASE, export_text, import_response, make_install, populate
from tests.storage_support import RO_ID, RO_SECRET, RW_ID, RW_SECRET
from tests.store_support import KEY, KEY_2, SECRET, SECRET_2

pytestmark = [pytest.mark.windows, pytest.mark.skipif(sys.platform != "win32", reason="Windows only")]


def _sweep(store: KeyringSecretStore) -> None:
    for name in OWNED_SECRET_NAMES:
        store.delete(name)
    for store_id in range(1, 6):
        for name in entry_names(store_id):
            store.delete(name)


@pytest.fixture
def two_services() -> Iterator[tuple[KeyringSecretStore, KeyringSecretStore]]:
    first = KeyringSecretStore(service=f"ShelfSyncTest-{uuid.uuid4().hex}")
    second = KeyringSecretStore(service=f"ShelfSyncTest-{uuid.uuid4().hex}")
    try:
        yield first, second
    finally:  # whatever the test did, no throwaway entry stays
        _sweep(first)
        _sweep(second)


def test_an_encrypted_export_imports_every_secret_into_another_credential_manager_service(
    tmp_path, two_services: tuple[KeyringSecretStore, KeyringSecretStore], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(backup_crypto, "SCRYPT_N", FAST_N)
    first, second = two_services
    source = make_install(tmp_path, "source", secrets=first)  # type: ignore[arg-type]
    populate(source)
    target = make_install(tmp_path, "target", secrets=second)  # type: ignore[arg-type]
    response = import_response(target, export_text(source, PASSPHRASE), PASSPHRASE)
    assert response.status_code == 200 and response.json() == {"stores": 2, "settings": 12, "secrets": 9}
    ids = [s["id"] for s in target.client.get("/api/stores").json()["stores"]]
    keys = StoreCredentials(second)
    assert [keys.read(i) for i in ids] == [(KEY, SECRET), (KEY_2, SECRET_2)]
    assert S3Credentials(second).read("rw") == (RW_ID, RW_SECRET)
    assert S3Credentials(second).read("ro") == (RO_ID, RO_SECRET)
    assert second.get("github-token") == GITHUB_TOKEN
    assert first.get("install-token") != second.get("install-token")  # each install keeps its own, never exported
