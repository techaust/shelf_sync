"""SET-01, ERR-01, SYS-03: the Stores API behind the deny-by-default guard: limits, duplicates, atomic saves, the key
pair, removal, the read test, and that no secret is ever in a response."""

from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from shelfsync.platform.secrets import MemorySecretStore
from shelfsync.secure.credentials import entry_names
from shelfsync.secure.redact import redact
from tests.store_support import (
    KEY,
    KEY_2,
    OTHER_URL,
    SECRET,
    SECRET_2,
    STORE_URL,
    FailingSecretStore,
    FakeWoo,
    StoreRig,
    html,
    make_store_rig,
    new_store_body,
    products,
    system_status,
    wp_error,
)
from tests.support import WRITE_HEADERS

STORE_ROUTES = [
    ("GET", "/api/stores"),
    ("POST", "/api/stores"),
    ("PATCH", "/api/stores/1"),
    ("PUT", "/api/stores/1/keys"),
    ("DELETE", "/api/stores/1"),
    ("POST", "/api/stores/1/test"),
]


def signed_in(rig: StoreRig) -> TestClient:
    return rig.harness.signed_in_client()


def add(client: TestClient, **changes: Any) -> dict[str, Any]:
    response = client.post("/api/stores", headers=WRITE_HEADERS, json=new_store_body(**changes))
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def error(response: Any) -> tuple[int, Any]:
    return response.status_code, response.json()


# ---- the guard ------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("method", "path"), STORE_ROUTES)
def test_every_stores_route_needs_a_session(method: str, path: str) -> None:
    rig = make_store_rig()
    headers = {} if method == "GET" else WRITE_HEADERS
    response = rig.harness.client().request(method, path, headers=headers)
    assert error(response) == (401, {"error": "signed_out"})


@pytest.mark.parametrize(("method", "path"), [r for r in STORE_ROUTES if r[0] != "GET"])
def test_a_write_needs_the_origin_and_the_csrf_header(method: str, path: str) -> None:
    rig = make_store_rig()
    client = signed_in(rig)
    for headers in ({}, {"X-ShelfSync": "1"}, {"Origin": "http://evil.example", "X-ShelfSync": "1"}):
        assert client.request(method, path, headers=headers, json=new_store_body()).status_code == 403
    assert client.get("/api/stores").json() == {"stores": []}  # a refused request changed nothing


def test_the_routes_are_in_the_route_table_and_typed_in_the_schema() -> None:
    from tests.test_guard import _api_routes

    rig = make_store_rig()
    found = set(_api_routes(rig.harness.app))
    assert {
        ("GET", "/api/stores"),
        ("POST", "/api/stores"),
        ("PATCH", "/api/stores/store_id"),
        ("PUT", "/api/stores/store_id/keys"),
        ("DELETE", "/api/stores/store_id"),
        ("POST", "/api/stores/store_id/test"),
    } <= found
    schemas = rig.harness.app.openapi()["components"]["schemas"]
    assert set(schemas["KeysModel"]["properties"]) == {"consumer_key", "consumer_secret"}  # masks, by name
    assert "StoreModel" in schemas and "StoreTestResponse" in schemas


# ---- add and list ---------------------------------------------------------------------------------------------------


def test_adding_a_store_returns_it_with_masked_keys_and_stores_the_keys_in_credential_manager() -> None:
    rig = make_store_rig()
    client = signed_in(rig)
    body = add(client, url="HTTPS://Store-A.Example:443/")
    assert body == {
        "id": 1,
        "name": "Store A",
        "url": "https://store-a.example",
        "code": "SA",
        "shape": "circle",
        "color": "indigo",
        "spacing_ms": 150,
        "main_button": "Download",
        "state": "active",
        "keys": {"consumer_key": "ck_••••" + KEY[-4:], "consumer_secret": "cs_••••" + SECRET[-4:]},
        "health": {
            "state": "unknown",
            "reason": None,
            "http_status": None,
            "latency_ms": None,
            "wc_version": None,
            "wp_version": None,
            "downloadable_count": None,
            "tested_at": None,
        },
    }
    assert rig.secrets.get("store-1-key") == KEY and rig.secrets.get("store-1-secret") == SECRET
    assert client.get("/api/stores").json() == {"stores": [body]}


def test_a_new_store_takes_the_defaults_and_the_owners_values() -> None:
    client = signed_in(make_store_rig())
    body = add(client, spacing_ms=2500, main_button="Get it", shape="diamond")
    assert (body["spacing_ms"], body["main_button"], body["shape"]) == (2500, "Get it", "diamond")


def test_the_url_is_normalised_lowercased_and_without_a_trailing_slash() -> None:
    client = signed_in(make_store_rig())
    assert add(client, url="https://Store-A.EXAMPLE/Shop/", code="AA")["url"] == "https://store-a.example/Shop"
    assert add(client, url="https://store-c.example:8443", code="CC")["url"] == "https://store-c.example:8443"


BAD_FIELDS: list[tuple[str, Any]] = [
    ("name", ""),
    ("name", "   "),
    ("name", "x" * 61),
    ("name", "two\nlines"),
    ("name", 5),
    ("code", "a1"),
    ("code", "sa"),
    ("code", "S"),
    ("code", "SAX"),
    ("code", "ÉÉ"),
    ("shape", "hexagon"),
    ("color", "#4d4d99"),
    ("color", "violet"),
    ("color", "teal "),
    ("color", "Indigo"),
    ("color", ""),
    ("spacing_ms", 49),
    ("spacing_ms", 5001),
    ("spacing_ms", "150"),
    ("spacing_ms", True),
    ("spacing_ms", 150.5),
    ("main_button", ""),
    ("main_button", "x" * 41),
    ("main_button", "a\tb"),
    ("consumer_key", "ck_short"),
    ("consumer_key", "cs_" + "a" * 30),
    ("consumer_key", "ck_" + "a" * 65),
    ("consumer_key", "ck_" + "a" * 29 + "!"),
    ("consumer_key", KEY + "\n"),
    ("consumer_secret", "ck_" + "a" * 30),
    ("consumer_secret", "cs_" + "a" * 19),
    ("consumer_secret", None),
    ("url", "http://store-a.example"),
    ("url", "store-a.example"),
    ("url", "https://127.0.0.1"),
    ("url", "https://[::1]"),
    ("url", "https://localhost"),
    ("url", "https://127.1"),
    ("url", "https://0x7f.1"),
    ("url", "https://user:pass@store-a.example"),
    ("url", "https://user@store-a.example"),
    ("url", "https://store-a.example/?a=1"),
    ("url", "https://store-a.example?"),
    ("url", "https://store-a.example/#x"),
    ("url", "https://store-a.example/a b"),
    ("url", "https://store-a.example/../x"),
    ("url", "https://store-a.example/a%2Fb"),
    ("url", "https://store-a.example/%2e%2e/x"),
    ("url", "https://store-a.example//x"),
    ("url", "https://störe-a.example"),
    ("url", "https://store-a.example:99999"),
    ("url", "https://store-a.example:abc"),
    ("url", "https://store_a.example"),
    ("url", "https://-store.example"),
    ("url", "https://store-a.example\\x"),
    ("url", "https://store-a." + "x" * 200 + ".example"),
    ("url", ""),
    ("url", None),
]


@pytest.mark.parametrize(("field", "value"), BAD_FIELDS, ids=[f"{f}={str(v)[:20]!r}" for f, v in BAD_FIELDS])
def test_every_limit_is_enforced_with_the_fixed_422(field: str, value: Any) -> None:
    rig = make_store_rig()
    client = signed_in(rig)
    response = client.post("/api/stores", headers=WRITE_HEADERS, json=new_store_body(**{field: value}))
    assert error(response) == (422, {"error": "invalid_request"})
    assert client.get("/api/stores").json() == {"stores": []}
    assert rig.secrets.get("store-1-key") is None  # nothing was stored


def test_the_limits_themselves_are_accepted() -> None:
    client = signed_in(make_store_rig())
    add(client, name="x" * 60, main_button="y" * 40, spacing_ms=50, code="AA", url="https://a1.example", shape="square")
    add(client, name="n", main_button="b", spacing_ms=5000, code="ZZ", url="https://b2.example", shape="triangle")
    add(client, consumer_key="ck_" + "a" * 64, consumer_secret="cs_" + "b" * 20, code="MM", url="https://c3.example")


@pytest.mark.parametrize("field", ["name", "url", "code", "shape", "color", "consumer_key", "consumer_secret"])
def test_a_missing_required_field_is_refused(field: str) -> None:
    body = new_store_body()
    del body[field]
    assert error(signed_in(make_store_rig()).post("/api/stores", headers=WRITE_HEADERS, json=body))[0] == 422


def test_an_unknown_field_is_refused_and_the_body_is_never_echoed() -> None:
    client = signed_in(make_store_rig())
    response = client.post("/api/stores", headers=WRITE_HEADERS, json=new_store_body(extra="hello-secret-text"))
    assert error(response) == (422, {"error": "invalid_request"})
    assert "hello-secret-text" not in response.text


def test_a_body_that_is_not_json_is_refused() -> None:
    client = signed_in(make_store_rig())
    response = client.post("/api/stores", headers=WRITE_HEADERS, content=KEY)
    assert error(response) == (422, {"error": "invalid_request"})


def test_a_second_store_with_the_same_address_is_refused_even_when_written_differently() -> None:
    rig = make_store_rig()
    client = signed_in(rig)
    add(client)
    for url in (STORE_URL, "https://STORE-A.example/", "https://store-a.example:443"):
        response = client.post("/api/stores", headers=WRITE_HEADERS, json=new_store_body(url=url, code="SB"))
        assert error(response) == (409, {"error": "store_exists"})
    assert rig.secrets.get("store-2-key") is None and len(client.get("/api/stores").json()["stores"]) == 1


def test_a_second_store_with_the_same_code_is_refused() -> None:
    client = signed_in(make_store_rig())
    add(client)
    response = client.post("/api/stores", headers=WRITE_HEADERS, json=new_store_body(url=OTHER_URL))
    assert error(response) == (409, {"error": "code_taken"})


def test_a_removed_stores_address_and_code_are_free_again_and_its_id_is_not_reused() -> None:
    rig = make_store_rig()
    client = signed_in(rig)
    add(client)
    assert client.delete("/api/stores/1", headers=WRITE_HEADERS).status_code == 204
    assert add(client)["id"] == 2


# ---- atomic saves ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("failing_set", [1, 2])
def test_a_save_that_fails_in_credential_manager_leaves_no_row_and_no_entry(failing_set: int) -> None:
    secrets = FailingSecretStore()
    secrets.fail_set_on = failing_set
    rig = make_store_rig(secrets)
    client = signed_in(rig)
    response = client.post("/api/stores", headers=WRITE_HEADERS, json=new_store_body())
    assert error(response) == (503, {"error": "secrets_unavailable"})
    assert client.get("/api/stores").json() == {"stores": []}
    assert secrets.get("store-1-key") is None and secrets.get("store-1-secret") is None
    secrets.fail_set_on = None
    assert add(client)["id"] == 1  # and the same request works once Credential Manager does


def test_a_save_that_cannot_even_read_credential_manager_changes_nothing() -> None:
    secrets = FailingSecretStore()
    secrets.fail_get = True
    rig = make_store_rig(secrets)
    client = signed_in(rig)
    assert error(client.post("/api/stores", headers=WRITE_HEADERS, json=new_store_body()))[0] == 503
    secrets.fail_get = False
    assert client.get("/api/stores").json() == {"stores": []}


# ---- edit -----------------------------------------------------------------------------------------------------------


def test_a_patch_changes_only_the_fields_sent() -> None:
    client = signed_in(make_store_rig())
    add(client)
    response = client.patch(
        "/api/stores/1", headers=WRITE_HEADERS, json={"name": " Renamed ", "state": "paused", "spacing_ms": 400}
    )
    body = response.json()
    assert response.status_code == 200
    assert (body["name"], body["state"], body["spacing_ms"], body["code"], body["url"]) == (
        "Renamed",
        "paused",
        400,
        "SA",
        STORE_URL,
    )
    assert body["keys"]["consumer_key"].endswith(KEY[-4:])


def test_an_empty_patch_changes_nothing() -> None:
    client = signed_in(make_store_rig())
    before = add(client)
    assert client.patch("/api/stores/1", headers=WRITE_HEADERS, json={}).json() == before


PATCH_BAD: list[dict[str, Any]] = [
    {"name": ""},
    {"name": None},
    {"url": None},
    {"state": "gone"},
    {"state": None},
    {"code": "x"},
    {"spacing_ms": 5001},
    {"shape": "star"},
    {"url": "http://store-a.example"},
    {"unknown": 1},
    {"id": 5},
    {"consumer_key": KEY},  # a pair or nothing
    {"consumer_secret": SECRET},
    {"consumer_key": KEY, "consumer_secret": "cs_x"},
]


@pytest.mark.parametrize("body", PATCH_BAD, ids=[str(sorted(b)) + str(i) for i, b in enumerate(PATCH_BAD)])
def test_a_bad_patch_is_refused_and_changes_nothing(body: dict[str, Any]) -> None:
    rig = make_store_rig()
    client = signed_in(rig)
    before = add(client)
    assert error(client.patch("/api/stores/1", headers=WRITE_HEADERS, json=body)) == (422, {"error": "invalid_request"})
    assert client.get("/api/stores").json() == {"stores": [before]}


def test_patching_a_store_that_is_not_there_is_a_404() -> None:
    client = signed_in(make_store_rig())
    assert error(client.patch("/api/stores/9", headers=WRITE_HEADERS, json={"name": "x"})) == (
        404,
        {"error": "not_found"},
    )
    assert error(client.patch("/api/stores/-1", headers=WRITE_HEADERS, json={"name": "x"}))[0] == 422
    assert error(client.patch("/api/stores/abc", headers=WRITE_HEADERS, json={"name": "x"}))[0] == 422


def test_a_patch_cannot_take_another_stores_address_or_code() -> None:
    client = signed_in(make_store_rig())
    add(client)
    add(client, url=STORE_URL + "/two", code="SB")  # the same host, so no keys are needed to move it
    assert error(client.patch("/api/stores/2", headers=WRITE_HEADERS, json={"url": STORE_URL}))[1] == {
        "error": "store_exists"
    }
    assert error(client.patch("/api/stores/2", headers=WRITE_HEADERS, json={"code": "SA"}))[1] == {
        "error": "code_taken"
    }
    assert client.patch("/api/stores/2", headers=WRITE_HEADERS, json={"code": "SB"}).status_code == 200  # its own


def test_a_url_change_on_the_same_host_resets_the_health_and_needs_no_keys() -> None:
    rig = make_store_rig()
    client = signed_in(rig)
    add(client)
    assert client.post("/api/stores/1/test", headers=WRITE_HEADERS).json()["ok"] is True
    assert client.get("/api/stores").json()["stores"][0]["health"]["state"] == "connected"
    response = client.patch("/api/stores/1", headers=WRITE_HEADERS, json={"url": STORE_URL + "/shop"})
    body = response.json()
    assert response.status_code == 200 and body["url"] == STORE_URL + "/shop"
    assert body["health"]["state"] == "unknown" and body["health"]["tested_at"] is None
    assert rig.secrets.get("store-1-key") == KEY  # the keys stay


def test_the_same_url_sent_again_keeps_the_last_test() -> None:
    client = signed_in(make_store_rig())
    add(client)
    client.post("/api/stores/1/test", headers=WRITE_HEADERS)
    body = client.patch("/api/stores/1", headers=WRITE_HEADERS, json={"url": "HTTPS://STORE-A.example/"}).json()
    assert body["health"]["state"] == "connected"


@pytest.mark.parametrize("new_url", [OTHER_URL, "https://store-a.example:8443", "https://www.store-a.example"])
def test_a_host_change_without_new_keys_is_refused_and_changes_nothing(new_url: str) -> None:
    rig = make_store_rig()
    client = signed_in(rig)
    before = add(client)
    response = client.patch("/api/stores/1", headers=WRITE_HEADERS, json={"url": new_url, "name": "Moved"})
    assert error(response) == (422, {"error": "keys_required"})
    assert client.get("/api/stores").json() == {"stores": [before]}  # not even the name changed
    assert rig.secrets.get("store-1-key") == KEY


def test_a_host_change_with_new_keys_in_the_same_request_replaces_them_and_resets_the_health() -> None:
    rig = make_store_rig()
    client = signed_in(rig)
    add(client)
    client.post("/api/stores/1/test", headers=WRITE_HEADERS)
    response = client.patch(
        "/api/stores/1",
        headers=WRITE_HEADERS,
        json={"url": OTHER_URL, "consumer_key": KEY_2, "consumer_secret": SECRET_2},
    )
    body = response.json()
    assert response.status_code == 200 and body["url"] == OTHER_URL
    assert body["health"]["state"] == "unknown"
    assert (rig.secrets.get("store-1-key"), rig.secrets.get("store-1-secret")) == (KEY_2, SECRET_2)
    assert body["keys"]["consumer_key"].endswith(KEY_2[-4:])


def test_a_patch_whose_keys_cannot_be_stored_changes_nothing_at_all() -> None:
    secrets = FailingSecretStore()
    rig = make_store_rig(secrets)
    client = signed_in(rig)
    before = add(client)
    secrets.fail_set_on = secrets.sets + 2  # the second write of the new pair fails
    response = client.patch(
        "/api/stores/1",
        headers=WRITE_HEADERS,
        json={"url": OTHER_URL, "name": "Moved", "consumer_key": KEY_2, "consumer_secret": SECRET_2},
    )
    assert error(response) == (503, {"error": "secrets_unavailable"})
    assert client.get("/api/stores").json() == {"stores": [before]}
    assert (secrets.get("store-1-key"), secrets.get("store-1-secret")) == (KEY, SECRET)  # the old pair is back


# ---- the key pair ---------------------------------------------------------------------------------------------------


def test_replacing_the_keys_is_a_204_that_resets_the_health() -> None:
    rig = make_store_rig()
    client = signed_in(rig)
    add(client)
    client.post("/api/stores/1/test", headers=WRITE_HEADERS)
    response = client.put(
        "/api/stores/1/keys", headers=WRITE_HEADERS, json={"consumer_key": KEY_2, "consumer_secret": SECRET_2}
    )
    assert response.status_code == 204 and response.content == b""
    assert (rig.secrets.get("store-1-key"), rig.secrets.get("store-1-secret")) == (KEY_2, SECRET_2)
    store = client.get("/api/stores").json()["stores"][0]
    assert store["health"]["state"] == "unknown" and store["keys"]["consumer_key"].endswith(KEY_2[-4:])


@pytest.mark.parametrize(
    "body",
    [{"consumer_key": KEY_2}, {"consumer_secret": SECRET_2}, {}, {"consumer_key": KEY_2, "consumer_secret": KEY_2},
     {"consumer_key": KEY_2, "consumer_secret": SECRET_2, "x": 1}],
)  # fmt: skip
def test_the_keys_are_always_a_valid_pair(body: dict[str, str]) -> None:
    rig = make_store_rig()
    client = signed_in(rig)
    add(client)
    assert error(client.put("/api/stores/1/keys", headers=WRITE_HEADERS, json=body))[0] == 422
    assert rig.secrets.get("store-1-key") == KEY


def test_keys_for_a_store_that_is_not_there_are_refused_and_not_stored() -> None:
    rig = make_store_rig()
    client = signed_in(rig)
    response = client.put(
        "/api/stores/4/keys", headers=WRITE_HEADERS, json={"consumer_key": KEY, "consumer_secret": SECRET}
    )
    assert error(response) == (404, {"error": "not_found"})
    assert rig.secrets.get("store-4-key") is None


def test_a_failed_key_replacement_keeps_the_old_pair() -> None:
    secrets = FailingSecretStore()
    rig = make_store_rig(secrets)
    client = signed_in(rig)
    add(client)
    secrets.fail_set_on = secrets.sets + 2
    response = client.put(
        "/api/stores/1/keys", headers=WRITE_HEADERS, json={"consumer_key": KEY_2, "consumer_secret": SECRET_2}
    )
    assert error(response) == (503, {"error": "secrets_unavailable"})
    assert (secrets.get("store-1-key"), secrets.get("store-1-secret")) == (KEY, SECRET)


# ---- remove ---------------------------------------------------------------------------------------------------------


def test_removing_a_store_deletes_both_entries_and_hides_the_row() -> None:
    rig = make_store_rig()
    client = signed_in(rig)
    add(client)
    assert client.delete("/api/stores/1", headers=WRITE_HEADERS).status_code == 204
    assert rig.secrets.get("store-1-key") is None and rig.secrets.get("store-1-secret") is None
    assert client.get("/api/stores").json() == {"stores": []}
    assert error(client.delete("/api/stores/1", headers=WRITE_HEADERS)) == (404, {"error": "not_found"})
    row = rig.service._open().execute("SELECT removed_at FROM store WHERE id = 1").fetchone()
    assert row[0] is not None  # a soft delete: history will point at the id


@pytest.mark.parametrize("failing", ["store-1-key", "store-1-secret"])
def test_a_removal_whose_entries_cannot_be_deleted_changes_nothing(failing: str) -> None:
    secrets = FailingSecretStore()
    rig = make_store_rig(secrets)
    client = signed_in(rig)
    before = add(client)
    secrets.fail_delete = {failing}
    assert error(client.delete("/api/stores/1", headers=WRITE_HEADERS)) == (503, {"error": "secrets_unavailable"})
    assert client.get("/api/stores").json() == {"stores": [before]}
    assert (secrets.get("store-1-key"), secrets.get("store-1-secret")) == (KEY, SECRET)  # both still there


# ---- the read test --------------------------------------------------------------------------------------------------


def test_a_good_test_answers_with_the_numbers_and_saves_them_on_the_store() -> None:
    rig = make_store_rig(woo=FakeWoo(latency=0.182))
    client = signed_in(rig)
    add(client)
    response = client.post("/api/stores/1/test", headers=WRITE_HEADERS)
    body = response.json()
    assert response.status_code == 200
    assert body["ok"] is True and body["state"] == "connected" and body["reason"] is None
    numbers = (
        body["http_status"],
        body["latency_ms"],
        body["wc_version"],
        body["wp_version"],
        body["downloadable_count"],
    )
    assert numbers == (
        200, 182, "9.4.1", "6.7.1", 42,
    )  # fmt: skip
    assert body["tested_at"].endswith("Z") and body["warning"] is None and body["detail"] is None
    assert [r.method for r in rig.woo.requests] == ["GET", "GET"] and rig.woo.time.slept == [0.15]
    saved = client.get("/api/stores").json()["stores"][0]["health"]
    assert saved == {
        "state": "connected", "reason": None, "http_status": 200, "latency_ms": 182, "wc_version": "9.4.1",
        "wp_version": "6.7.1", "downloadable_count": 42, "tested_at": body["tested_at"],
    }  # fmt: skip


def test_the_spacing_between_the_two_gets_is_the_stores_own() -> None:
    rig = make_store_rig()
    client = signed_in(rig)
    add(client, spacing_ms=1200)
    client.post("/api/stores/1/test", headers=WRITE_HEADERS)
    assert rig.woo.time.slept == [1.2]


def test_a_failed_test_is_still_a_200_with_ok_false_and_is_saved() -> None:
    rig = make_store_rig(woo=FakeWoo(status=wp_error(401, "woocommerce_rest_cannot_view")))
    client = signed_in(rig)
    add(client)
    response = client.post("/api/stores/1/test", headers=WRITE_HEADERS)
    body = response.json()
    assert response.status_code == 200
    assert (body["ok"], body["state"], body["reason"], body["http_status"]) == (False, "refused", "keys_refused", 401)
    health = client.get("/api/stores").json()["stores"][0]["health"]
    assert (health["state"], health["reason"], health["http_status"]) == ("refused", "keys_refused", 401)


def test_an_old_woocommerce_is_refused_and_its_versions_are_shown() -> None:
    client = signed_in(make_store_rig(woo=FakeWoo(status=system_status("5.7.0", "6.0"))))
    add(client)
    body = client.post("/api/stores/1/test", headers=WRITE_HEADERS).json()
    assert (body["reason"], body["state"], body["wc_version"], body["wp_version"]) == (
        "wc_too_old",
        "refused",
        "5.7.0",
        "6.0",
    )


def test_a_redirect_names_the_host_it_pointed_at() -> None:
    moved = httpx.Response(301, headers={"Location": "https://new-home.example/"})
    client = signed_in(make_store_rig(woo=FakeWoo(status=moved)))
    add(client)
    body = client.post("/api/stores/1/test", headers=WRITE_HEADERS).json()
    assert (body["reason"], body["detail"], body["state"]) == ("redirected", "new-home.example", "unreachable")


def test_a_store_with_no_downloadable_products_is_ok_with_a_warning() -> None:
    client = signed_in(make_store_rig(woo=FakeWoo(products_answer=products(total=0, body=[]))))
    add(client)
    body = client.post("/api/stores/1/test", headers=WRITE_HEADERS).json()
    assert (body["ok"], body["downloadable_count"], body["warning"]) == (True, 0, "no_downloadable_products")


def test_a_paused_store_can_be_tested() -> None:
    client = signed_in(make_store_rig())
    add(client)
    client.patch("/api/stores/1", headers=WRITE_HEADERS, json={"state": "paused"})
    assert client.post("/api/stores/1/test", headers=WRITE_HEADERS).json()["ok"] is True


def test_a_test_with_no_keys_answers_keys_missing_and_sends_nothing() -> None:
    rig = make_store_rig()
    client = signed_in(rig)
    add(client)
    for name in entry_names(1):
        rig.secrets.delete(name)
    assert error(client.post("/api/stores/1/test", headers=WRITE_HEADERS)) == (409, {"error": "keys_missing"})
    assert rig.woo.requests == []


def test_a_test_when_credential_manager_cannot_be_read_answers_keys_missing() -> None:
    secrets = FailingSecretStore()
    rig = make_store_rig(secrets)
    client = signed_in(rig)
    add(client)
    secrets.fail_get = True
    assert error(client.post("/api/stores/1/test", headers=WRITE_HEADERS)) == (409, {"error": "keys_missing"})
    assert rig.woo.requests == []


def test_testing_a_store_that_is_not_there_is_a_404() -> None:
    assert error(signed_in(make_store_rig()).post("/api/stores/3/test", headers=WRITE_HEADERS)) == (
        404,
        {"error": "not_found"},
    )


def test_only_one_test_runs_per_store_at_a_time() -> None:
    """While the first test is waiting for the store's answer, a second one for the same store is refused: the fake
    store's answer starts it, from inside the first request."""
    rig = make_store_rig()
    client = signed_in(rig)
    add(client)
    add(client, url=OTHER_URL, code="SB")
    inner: list[Any] = []

    def first_answer(request: httpx.Request) -> httpx.Response:
        from shelfsync.store_service import StoreError

        if inner:  # only the first answer starts the others
            return system_status()
        inner.append("started")
        try:
            rig.service.test(1)
        except StoreError as refused:
            inner.append((refused.status, refused.code))
        inner.append(rig.service.test(2).outcome.ok)  # another store is not blocked
        return system_status()

    rig.woo.status = first_answer
    assert client.post("/api/stores/1/test", headers=WRITE_HEADERS).json()["ok"] is True
    assert inner[1:] == [(409, "busy"), True]
    assert client.post("/api/stores/1/test", headers=WRITE_HEADERS).status_code == 200  # free again afterwards


def test_a_test_that_blows_up_still_frees_the_store() -> None:
    rig = make_store_rig()
    client = signed_in(rig)
    add(client)

    def explode(request: httpx.Request) -> httpx.Response:
        raise RuntimeError("boom")

    rig.woo.status = explode
    with pytest.raises(RuntimeError):
        rig.service.test(1)
    rig.woo.status = None
    assert client.post("/api/stores/1/test", headers=WRITE_HEADERS).status_code == 200


# ---- no secret in any response --------------------------------------------------------------------------------------


def test_no_response_body_ever_holds_a_key_or_a_secret() -> None:
    rig = make_store_rig()
    client = signed_in(rig)
    seen = []
    seen.append(client.post("/api/stores", headers=WRITE_HEADERS, json=new_store_body()))
    seen.append(client.get("/api/stores"))
    seen.append(client.post("/api/stores", headers=WRITE_HEADERS, json=new_store_body()))  # a refusal
    seen.append(client.post("/api/stores", headers=WRITE_HEADERS, json=new_store_body(consumer_key="ck_bad")))
    seen.append(client.post("/api/stores/1/test", headers=WRITE_HEADERS))
    seen.append(client.get("/api/stores"))
    seen.append(client.patch("/api/stores/1", headers=WRITE_HEADERS, json={"url": OTHER_URL}))
    seen.append(client.patch("/api/stores/1", headers=WRITE_HEADERS, json={"name": "x"}))
    seen.append(
        client.put(
            "/api/stores/1/keys", headers=WRITE_HEADERS, json={"consumer_key": KEY_2, "consumer_secret": SECRET_2}
        )
    )
    seen.append(client.get("/api/stores"))
    seen.append(client.post("/api/stores/1/test", headers=WRITE_HEADERS))
    seen.append(client.delete("/api/stores/1", headers=WRITE_HEADERS))
    seen.append(client.get("/api/stores/1"))
    assert len(seen) == 13
    for response in seen:
        text = response.text + str(dict(response.headers))
        for value in (KEY, SECRET, KEY_2, SECRET_2):
            assert value not in text
            assert value[3:] not in text  # nor the part after the prefix
    # the mask is all a GET shows: prefix, four dots, last four, and no more
    assert client.post("/api/stores", headers=WRITE_HEADERS, json=new_store_body()).status_code == 201
    mask = client.get("/api/stores").json()["stores"][0]["keys"]["consumer_key"]
    assert mask == "ck_••••" + KEY[-4:] and len(mask) == 11


def test_a_response_never_holds_the_html_or_text_the_store_sent() -> None:
    rig = make_store_rig(woo=FakeWoo(status=html(403)))
    client = signed_in(rig)
    add(client)
    response = client.post("/api/stores/1/test", headers=WRITE_HEADERS)
    assert "Just a moment" not in response.text and response.json()["reason"] == "blocked"


def test_a_stored_key_is_masked_in_the_log_from_the_moment_it_is_stored() -> None:
    client = signed_in(make_store_rig())
    add(client)
    assert redact(f"key {KEY} secret {SECRET}") == "key [redacted] secret [redacted]"


def test_default_app_stores_use_a_private_in_memory_database() -> None:
    from tests.support import make_harness

    a, b = make_harness().signed_in_client(), make_harness().signed_in_client()
    add(a)
    assert b.get("/api/stores").json() == {"stores": []}
    assert isinstance(MemorySecretStore(), MemorySecretStore)
