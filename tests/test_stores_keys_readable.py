"""SET-01 (M2.3 review R10): the stores list says whether Credential Manager could be read, so null masks aren't taken
for "no keys saved". The existing fields are unchanged."""

from shelfsync.platform.secrets import MemorySecretStore
from tests.store_support import KEY, SECRET, FailingSecretStore, make_store_rig, new_store_body
from tests.support import WRITE_HEADERS


def test_a_readable_store_says_so_and_keeps_its_masks() -> None:
    rig = make_store_rig(MemorySecretStore())
    client = rig.harness.signed_in_client()
    created = client.post("/api/stores", headers=WRITE_HEADERS, json=new_store_body())
    assert created.status_code == 201
    assert created.json()["keys_readable"] is True
    listed = client.get("/api/stores").json()["stores"][0]
    assert listed["keys_readable"] is True
    assert listed["keys"] == {"consumer_key": f"ck_••••{KEY[-4:]}", "consumer_secret": f"cs_••••{SECRET[-4:]}"}
    assert {"id", "name", "url", "code", "shape", "color", "spacing_ms", "main_button", "state", "health"} <= set(
        listed
    )


def test_an_unreadable_credential_manager_is_not_shown_as_no_keys() -> None:
    secrets = FailingSecretStore()
    rig = make_store_rig(secrets)
    client = rig.harness.signed_in_client()
    assert client.post("/api/stores", headers=WRITE_HEADERS, json=new_store_body()).status_code == 201
    secrets.fail_get = True
    listed = client.get("/api/stores").json()["stores"][0]
    assert listed["keys"] == {"consumer_key": None, "consumer_secret": None}
    assert listed["keys_readable"] is False
    secrets.fail_get = False
    assert client.get("/api/stores").json()["stores"][0]["keys_readable"] is True


def test_a_store_with_no_keys_stored_is_readable_and_not_set() -> None:
    rig = make_store_rig(MemorySecretStore())
    client = rig.harness.signed_in_client()
    assert client.post("/api/stores", headers=WRITE_HEADERS, json=new_store_body()).status_code == 201
    rig.secrets.delete("store-1-key")
    rig.secrets.delete("store-1-secret")
    listed = client.get("/api/stores").json()["stores"][0]
    assert listed["keys"] == {"consumer_key": None, "consumer_secret": None} and listed["keys_readable"] is True
