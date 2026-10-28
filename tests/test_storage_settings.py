"""SET-02: the storage settings (limits, defaults) and the Settings > Storage API (the settings, the two key pairs).

The S3 Test is not here: it needs boto3 (M2.7). One test pins that no such route exists yet."""

import json
import sqlite3
from contextlib import closing
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from shelfsync.api.storage import S3_RO_PATH, S3_RW_PATH, STORAGE_SETTINGS_PATH, StorageService
from shelfsync.db.migrate import migrate
from shelfsync.db.settings import (
    DEFAULT_LINK_TEMPLATE,
    DEFAULTS,
    check_link_template,
    check_s3_bucket,
    check_s3_endpoint,
    check_s3_region,
    get_setting,
    set_setting,
)
from tests.storage_support import (
    GOOD_SETTINGS,
    RO_ID,
    RO_SECRET,
    RW_ID,
    RW_ID_2,
    RW_SECRET,
    RW_SECRET_2,
    StorageRig,
    api_routes,
    key_body,
    make_storage_rig,
)
from tests.support import WRITE_HEADERS

DOTS = "••••"
KEYS = tuple(GOOD_SETTINGS)


@pytest.fixture
def rig() -> StorageRig:
    return make_storage_rig()


def put(rig: StorageRig, body: Any) -> Any:
    return rig.client.put(STORAGE_SETTINGS_PATH, json=body, headers=WRITE_HEADERS)


# ---- the limits (db/settings.py) -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "",
        "https://s3.us-east-1.amazonaws.com",
        "https://s3.example.com/",
        "https://objects.example.com:9000",
        "http://127.0.0.1:5000",
        "http://localhost:5000",
        "https://localhost",
        "https://127.0.0.1:5001/",
    ],
)
def test_an_acceptable_endpoint_is_accepted(value: str) -> None:
    check_s3_endpoint(value)


@pytest.mark.parametrize(
    "value",
    [
        "s3.amazonaws.com",  # no scheme
        "ftp://s3.example.com",
        "http://s3.example.com",  # http only to loopback
        "http://127.0.0.2:5000",  # not the loopback name
        "http://[::1]:5000",
        "http://0.0.0.0:5000",
        "https://192.168.1.5",  # an address, not a name
        "https://user@s3.example.com",
        "https://user:pw@s3.example.com",
        "http://127.0.0.1@evil.example.com",
        "http://localhost@evil.example.com",
        "http://127.0.0.1.evil.example.com",
        "https://s3.example.com?x=1",
        "https://s3.example.com/?x=1",
        "https://s3.example.com#frag",
        "https://s3.example.com/path",
        "https://s3.example.com/a/",
        "https://s3.example.com:0",
        "https://s3.example.com:99999",
        "https://s3.example.com:abc",
        "https://s3 .example.com",
        "https://s3.example.com\n",
        "https://s3.exam\\ple.com",
        "https://nodot",
        "https://s3.example.123",
        "HTTPS://s3.example.com",  # the scheme is written in lowercase
        "https://s3.exämple.com",
        "https://" + "a" * 200 + ".example.com",
        "https://",
    ],
)
def test_an_unacceptable_endpoint_is_refused(value: str) -> None:
    with pytest.raises(ValueError, match="s3_endpoint"):
        check_s3_endpoint(value)


@pytest.mark.parametrize("value", ["", "ap-south-1", "us-east-1", "eu", "a1", "x" * 32])
def test_a_region_is_empty_or_lowercase_words(value: str) -> None:
    check_s3_region(value)


@pytest.mark.parametrize("value", ["a", "x" * 33, "AP-south-1", "ap_south_1", "ap south", "ap-south-1\n", "région"])
def test_other_regions_are_refused(value: str) -> None:
    with pytest.raises(ValueError, match="s3_region"):
        check_s3_region(value)


@pytest.mark.parametrize("value", ["", "abc", "my-bucket", "my.bucket.name", "a1b", "0" * 63, "a" + "-" * 61 + "b"])
def test_a_bucket_is_empty_or_a_valid_name(value: str) -> None:
    check_s3_bucket(value)


@pytest.mark.parametrize(
    "value",
    ["a", "ab", "-ab", "ab-", ".ab", "ab.", "My-Bucket", "a_b", "a b", "a..b", "x" * 64, "ab\n", "ab/cd", "bücket"],
)
def test_other_buckets_are_refused(value: str) -> None:
    with pytest.raises(ValueError, match="s3_bucket"):
        check_s3_bucket(value)


def test_the_link_template_default_is_the_one_in_use_today() -> None:
    assert DEFAULTS["download_link_template"] == DEFAULT_LINK_TEMPLATE == '[amazon_s3 object="{key}"]'
    check_link_template(DEFAULT_LINK_TEMPLATE)


@pytest.mark.parametrize("value", ["{key}", "https://cdn.example.com/{key}", 'a "{key}" b', "x" * 195 + "{key}"])
def test_a_template_with_key_once_is_accepted(value: str) -> None:
    check_link_template(value)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "no placeholder",
        "{key}{key}",
        "{key} and {key}",
        "{Key}",
        "{key\n}",
        "a{key}\nb",
        "a{key}\r",
        "x" * 196 + "{key}",
    ],
)
def test_other_templates_are_refused(value: str) -> None:
    with pytest.raises(ValueError, match="download_link_template"):
        check_link_template(value)


def test_the_database_layer_applies_the_same_limits_and_exact_types() -> None:
    with closing(sqlite3.connect(":memory:", isolation_level=None)) as connection:
        migrate(connection)
        assert [get_setting(connection, key) for key in KEYS] == [DEFAULTS[key] for key in KEYS]
        assert DEFAULTS["keep_previous_files"] == 1
        for key, value in GOOD_SETTINGS.items():
            set_setting(connection, key, value)
            assert get_setting(connection, key) == value
        for key, bad in [
            ("s3_endpoint", "http://example.com"),
            ("s3_region", "A"),
            ("s3_bucket", "A"),
            ("keep_previous_files", 0),
            ("keep_previous_files", 6),
            ("keep_previous_files", True),
            ("keep_previous_files", "2"),
            ("download_link_template", "no key"),
            ("s3_region", None),
        ]:
            with pytest.raises((ValueError, TypeError)):
                set_setting(connection, key, bad)
        assert get_setting(connection, "s3_region") == "ap-south-1"  # a refused value changed nothing


@given(st.text(max_size=300))
def test_the_endpoint_check_only_ever_raises_value_error_and_accepts_only_safe_hosts(text: str) -> None:
    try:
        check_s3_endpoint(text)
    except ValueError:
        return
    if text:
        assert text.startswith(("https://", "http://"))
        assert "@" not in text and "?" not in text and "#" not in text and " " not in text
        if text.startswith("http://"):
            assert text.split("/")[2].split(":")[0] in ("127.0.0.1", "localhost")


@given(st.text(max_size=300))
def test_the_template_check_only_accepts_one_key_on_one_line(text: str) -> None:
    try:
        check_link_template(text)
    except ValueError:
        return
    assert text.count("{key}") == 1 and "\n" not in text and "\r" not in text and len(text) <= 200


# ---- GET and PUT /api/settings/storage -------------------------------------------------------------------------------


def test_get_with_nothing_saved_gives_the_defaults_and_no_keys(rig: StorageRig) -> None:
    response = rig.client.get(STORAGE_SETTINGS_PATH)
    assert response.status_code == 200
    assert response.json() == {
        "s3_endpoint": "",
        "s3_region": "",
        "s3_bucket": "",
        "keep_previous_files": 1,
        "download_link_template": '[amazon_s3 object="{key}"]',
        "rw": {"access_key_id": None, "secret_access_key": None},
        "ro": {"access_key_id": None, "secret_access_key": None},
    }


def test_put_saves_all_five_answers_what_was_saved_and_get_agrees(rig: StorageRig) -> None:
    response = put(rig, GOOD_SETTINGS)
    assert response.status_code == 200
    assert response.json() == GOOD_SETTINGS
    assert {
        key: value for key, value in rig.client.get(STORAGE_SETTINGS_PATH).json().items() if key in KEYS
    } == GOOD_SETTINGS


def test_put_accepts_the_local_test_stack_endpoint_and_empty_region_and_bucket(rig: StorageRig) -> None:
    body = {**GOOD_SETTINGS, "s3_endpoint": "http://127.0.0.1:5000", "s3_region": "", "s3_bucket": ""}
    assert put(rig, body).json() == body


@pytest.mark.parametrize("missing", KEYS)
def test_every_setting_is_required(rig: StorageRig, missing: str) -> None:
    body = {key: value for key, value in GOOD_SETTINGS.items() if key != missing}
    response = put(rig, body)
    assert response.status_code == 422 and response.json() == {"error": "invalid_request"}


def test_an_unknown_field_is_refused_and_changes_nothing(rig: StorageRig) -> None:
    before = rig.client.get(STORAGE_SETTINGS_PATH).json()
    for extra in ({"extra": 1}, {"rw": {"access_key_id": "x", "secret_access_key": "y"}}, {"s3_secret": "x"}):
        response = put(rig, {**GOOD_SETTINGS, **extra})
        assert response.status_code == 422 and response.json() == {"error": "invalid_request"}
    assert rig.client.get(STORAGE_SETTINGS_PATH).json() == before


@pytest.mark.parametrize(
    ("key", "bad"),
    [
        ("s3_endpoint", "http://example.com"),
        ("s3_endpoint", "https://user@example.com"),
        ("s3_endpoint", 5),
        ("s3_endpoint", None),
        ("s3_region", "AP"),
        ("s3_region", 1),
        ("s3_bucket", "UPPER"),
        ("s3_bucket", ["a"]),
        ("keep_previous_files", 0),
        ("keep_previous_files", 6),
        ("keep_previous_files", True),
        ("keep_previous_files", "2"),
        ("keep_previous_files", 2.5),
        ("download_link_template", "no key"),
        ("download_link_template", "{key}{key}"),
        ("download_link_template", "{key}\n"),
        ("download_link_template", "x" * 300),
    ],
)
def test_a_value_outside_its_limit_is_refused_with_the_fixed_body(rig: StorageRig, key: str, bad: Any) -> None:
    before = rig.client.get(STORAGE_SETTINGS_PATH).json()
    response = put(rig, {**GOOD_SETTINGS, key: bad})
    assert response.status_code == 422
    assert response.json() == {"error": "invalid_request"}
    assert str(bad) not in response.text or str(bad) in ("", "None")  # the request is never echoed
    assert rig.client.get(STORAGE_SETTINGS_PATH).json() == before


def test_one_bad_field_saves_none_of_them(rig: StorageRig) -> None:
    assert put(rig, {**GOOD_SETTINGS, "keep_previous_files": 9}).status_code == 422
    assert rig.client.get(STORAGE_SETTINGS_PATH).json()["s3_bucket"] == ""


def test_the_limits_at_the_edges_are_accepted(rig: StorageRig) -> None:
    body = {
        "s3_endpoint": "https://" + "a" * 60 + ".example.com",
        "s3_region": "x" * 32,
        "s3_bucket": "b" * 63,
        "keep_previous_files": 5,
        "download_link_template": "x" * 195 + "{key}",
    }
    assert put(rig, body).json() == body
    assert put(rig, {**body, "keep_previous_files": 1}).status_code == 200


def test_a_stored_value_that_is_no_longer_valid_reads_as_the_default(
    rig: StorageRig, caplog: pytest.LogCaptureFixture
) -> None:
    """A hand-edited database never breaks the GET: the default is shown, with a warning naming the key only."""
    connection = rig.service._connect()
    connection.execute(
        "INSERT INTO setting (key, value_json) VALUES ('s3_endpoint', ?)", (json.dumps("http://evil.test"),)
    )
    connection.close()
    caplog.set_level("WARNING")
    assert rig.client.get(STORAGE_SETTINGS_PATH).json()["s3_endpoint"] == ""
    assert "evil.test" not in caplog.text and "s3_endpoint" in caplog.text


def test_a_failed_save_rolls_back_every_setting(rig: StorageRig, monkeypatch: pytest.MonkeyPatch) -> None:
    from shelfsync.api import storage

    calls: list[str] = []

    def fail_on_third(connection: sqlite3.Connection, key: str, value: Any) -> None:
        calls.append(key)
        if len(calls) == 3:
            raise sqlite3.OperationalError("disk I/O error")
        set_setting(connection, key, value)

    monkeypatch.setattr(storage, "set_setting", fail_on_third)
    signed = rig.harness.signed_in_client(raise_server_exceptions=False)
    assert signed.put(STORAGE_SETTINGS_PATH, json=GOOD_SETTINGS, headers=WRITE_HEADERS).status_code == 500
    monkeypatch.undo()
    assert rig.client.get(STORAGE_SETTINGS_PATH).json()["s3_region"] == ""  # none of the written ones stayed


# ---- the keys: PUT and DELETE /api/secrets/s3-rw and s3-ro -----------------------------------------------------------


def test_a_pair_is_stored_in_credential_manager_and_shown_masked_only(rig: StorageRig) -> None:
    assert rig.client.put(S3_RW_PATH, json=key_body(), headers=WRITE_HEADERS).status_code == 204
    assert rig.client.put(S3_RO_PATH, json=key_body(RO_ID, RO_SECRET), headers=WRITE_HEADERS).status_code == 204
    assert rig.secrets.get("s3-rw-key-id") == RW_ID and rig.secrets.get("s3-rw-secret") == RW_SECRET
    assert rig.secrets.get("s3-ro-key-id") == RO_ID and rig.secrets.get("s3-ro-secret") == RO_SECRET
    response = rig.client.get(STORAGE_SETTINGS_PATH)
    body = response.json()
    assert body["rw"] == {
        "access_key_id": f"{RW_ID[:4]}{DOTS}{RW_ID[-4:]}",
        "secret_access_key": f"{DOTS}{RW_SECRET[-4:]}",
    }
    assert body["ro"] == {
        "access_key_id": f"{RO_ID[:4]}{DOTS}{RO_ID[-4:]}",
        "secret_access_key": f"{DOTS}{RO_SECRET[-4:]}",
    }


def test_no_response_ever_holds_a_raw_key_id_or_secret(rig: StorageRig) -> None:
    texts: list[str] = []
    for path, body in ((S3_RW_PATH, key_body()), (S3_RO_PATH, key_body(RO_ID, RO_SECRET))):
        response = rig.client.put(path, json=body, headers=WRITE_HEADERS)
        texts.append(response.text + str(response.headers))
    texts.append(rig.client.get(STORAGE_SETTINGS_PATH).text)
    texts.append(put(rig, GOOD_SETTINGS).text)
    # refusals that carry a key in the request
    for bad in (
        {**key_body(), "x": 1},
        key_body(RW_ID, "short"),
        key_body("short!", RW_SECRET),
        {"access_key_id": RW_ID},
    ):
        response = rig.client.put(S3_RW_PATH, json=bad, headers=WRITE_HEADERS)
        assert response.status_code == 422
        texts.append(response.text)
    texts.append(rig.client.delete(S3_RW_PATH, headers=WRITE_HEADERS).text)
    for text in texts:
        for value in (RW_ID, RW_SECRET, RO_ID, RO_SECRET):
            assert value not in text
        for value in (RW_SECRET, RO_SECRET):
            assert value[: len(value) // 2] not in text  # not even half of a secret


@pytest.mark.parametrize("path", [S3_RW_PATH, S3_RO_PATH])
@pytest.mark.parametrize(
    "body",
    [
        {"access_key_id": RW_ID},
        {"secret_access_key": RW_SECRET},
        {},
        {**key_body(), "extra": "x"},
        {"access_key_id": RW_ID, "secret_access_key": RW_SECRET, "region": "x"},
        key_body("A" * 15, RW_SECRET),
        key_body("A" * 129, RW_SECRET),
        key_body("AKIA-WITH-DASH-123", RW_SECRET),
        key_body("AKIA 1234567890123", RW_SECRET),
        key_body(RW_ID, "s" * 15),
        key_body(RW_ID, "s" * 129),
        key_body(RW_ID, "secret with space 1234"),
        key_body(RW_ID, RW_SECRET + "\n"),
        key_body(RW_ID + "\n", RW_SECRET),
        key_body(RW_ID, "secret_with_underscore_123"),
        {"access_key_id": 1234567890123456, "secret_access_key": RW_SECRET},
        {"access_key_id": None, "secret_access_key": None},
        {"access_key_id": [RW_ID], "secret_access_key": RW_SECRET},
    ],
)
def test_a_key_pair_must_be_a_whole_valid_pair(rig: StorageRig, path: str, body: Any) -> None:
    response = rig.client.put(path, json=body, headers=WRITE_HEADERS)
    assert response.status_code == 422
    assert response.json() == {"error": "invalid_request"}
    assert rig.secrets.sets == 0  # nothing was written


@pytest.mark.parametrize(
    ("key_id", "secret"),
    [("A" * 16, "s" * 16), ("Z" * 128, "/" * 128), ("a0" * 8, "a+/=" * 4), (RW_ID, RW_SECRET)],
)
def test_the_edges_of_the_key_shapes_are_accepted(rig: StorageRig, key_id: str, secret: str) -> None:
    assert rig.client.put(S3_RW_PATH, json=key_body(key_id, secret), headers=WRITE_HEADERS).status_code == 204
    assert rig.service._credentials.read("rw") == (key_id, secret)


def test_a_failure_on_the_second_write_leaves_nothing(rig: StorageRig) -> None:
    rig.secrets.fail_set_on = 2
    response = rig.client.put(S3_RW_PATH, json=key_body(), headers=WRITE_HEADERS)
    assert response.status_code == 503 and response.json() == {"error": "secrets_unavailable"}
    assert rig.secrets.get("s3-rw-key-id") is None and rig.secrets.get("s3-rw-secret") is None
    assert rig.client.get(STORAGE_SETTINGS_PATH).json()["rw"] == {"access_key_id": None, "secret_access_key": None}


def test_a_failure_on_the_first_write_leaves_nothing(rig: StorageRig) -> None:
    rig.secrets.fail_set_on = 1
    assert rig.client.put(S3_RO_PATH, json=key_body(RO_ID, RO_SECRET), headers=WRITE_HEADERS).status_code == 503
    assert rig.secrets.get("s3-ro-key-id") is None and rig.secrets.get("s3-ro-secret") is None


def test_a_failed_replacement_keeps_the_pair_that_was_there(rig: StorageRig) -> None:
    assert rig.client.put(S3_RW_PATH, json=key_body(), headers=WRITE_HEADERS).status_code == 204
    rig.secrets.fail_set_on = rig.secrets.sets + 2
    assert rig.client.put(S3_RW_PATH, json=key_body(RW_ID_2, RW_SECRET_2), headers=WRITE_HEADERS).status_code == 503
    assert (rig.secrets.get("s3-rw-key-id"), rig.secrets.get("s3-rw-secret")) == (RW_ID, RW_SECRET)
    rig.secrets.fail_set_on = None
    assert rig.client.put(S3_RW_PATH, json=key_body(RW_ID_2, RW_SECRET_2), headers=WRITE_HEADERS).status_code == 204
    assert (rig.secrets.get("s3-rw-key-id"), rig.secrets.get("s3-rw-secret")) == (RW_ID_2, RW_SECRET_2)


def test_an_unreadable_credential_manager_is_503_on_a_write_and_not_set_on_a_read(rig: StorageRig) -> None:
    assert rig.client.put(S3_RW_PATH, json=key_body(), headers=WRITE_HEADERS).status_code == 204
    rig.secrets.fail_get = True
    response = rig.client.put(S3_RW_PATH, json=key_body(RW_ID_2, RW_SECRET_2), headers=WRITE_HEADERS)
    assert response.status_code == 503 and response.json() == {"error": "secrets_unavailable"}
    assert rig.client.delete(S3_RW_PATH, headers=WRITE_HEADERS).status_code == 503
    body = rig.client.get(STORAGE_SETTINGS_PATH)
    assert body.status_code == 200 and body.json()["rw"] == {"access_key_id": None, "secret_access_key": None}
    rig.secrets.fail_get = False
    assert rig.secrets.get("s3-rw-key-id") == RW_ID  # nothing changed


def test_delete_removes_the_pair_and_removing_nothing_is_fine(rig: StorageRig) -> None:
    rig.client.put(S3_RW_PATH, json=key_body(), headers=WRITE_HEADERS)
    rig.client.put(S3_RO_PATH, json=key_body(RO_ID, RO_SECRET), headers=WRITE_HEADERS)
    assert rig.client.delete(S3_RW_PATH, headers=WRITE_HEADERS).status_code == 204
    assert rig.secrets.get("s3-rw-key-id") is None and rig.secrets.get("s3-rw-secret") is None
    assert rig.secrets.get("s3-ro-key-id") == RO_ID  # the other pair is untouched
    assert rig.client.delete(S3_RW_PATH, headers=WRITE_HEADERS).status_code == 204
    assert rig.client.delete(S3_RO_PATH, headers=WRITE_HEADERS).status_code == 204
    assert rig.secrets.get("s3-ro-secret") is None


def test_a_failed_second_delete_puts_the_first_back(rig: StorageRig) -> None:
    rig.client.put(S3_RW_PATH, json=key_body(), headers=WRITE_HEADERS)
    rig.secrets.fail_delete = {"s3-rw-secret"}
    response = rig.client.delete(S3_RW_PATH, headers=WRITE_HEADERS)
    assert response.status_code == 503 and response.json() == {"error": "secrets_unavailable"}
    assert (rig.secrets.get("s3-rw-key-id"), rig.secrets.get("s3-rw-secret")) == (RW_ID, RW_SECRET)


def test_saving_the_settings_never_touches_the_keys_and_the_keys_never_touch_the_settings(rig: StorageRig) -> None:
    rig.client.put(S3_RW_PATH, json=key_body(), headers=WRITE_HEADERS)
    put(rig, GOOD_SETTINGS)
    assert rig.secrets.get("s3-rw-key-id") == RW_ID
    rig.client.delete(S3_RW_PATH, headers=WRITE_HEADERS)
    assert {k: v for k, v in rig.client.get(STORAGE_SETTINGS_PATH).json().items() if k in KEYS} == GOOD_SETTINGS


def test_the_secret_store_is_never_written_by_a_get(rig: StorageRig) -> None:
    rig.client.get(STORAGE_SETTINGS_PATH)
    assert rig.secrets.sets == 0


# ---- the guard, and what is not there yet ----------------------------------------------------------------------------

NEW_ROUTES = {
    ("GET", STORAGE_SETTINGS_PATH),
    ("PUT", STORAGE_SETTINGS_PATH),
    ("PUT", S3_RW_PATH),
    ("DELETE", S3_RW_PATH),
    ("PUT", S3_RO_PATH),
    ("DELETE", S3_RO_PATH),
}


def test_the_six_routes_exist_and_there_is_no_test_route_yet(rig: StorageRig) -> None:
    routes = set(api_routes(rig.harness.app))
    assert routes >= NEW_ROUTES
    storage_like = {(m, p) for m, p in routes if "storage" in p or "s3" in p}
    assert storage_like == NEW_ROUTES  # nothing else: no Test route until boto3 is approved (M2.7)


def test_every_new_route_needs_a_session(rig: StorageRig) -> None:
    anonymous = rig.harness.client()
    for method, path in sorted(NEW_ROUTES):
        headers = {} if method == "GET" else WRITE_HEADERS
        response = anonymous.request(method, path, headers=headers, json=None if method == "GET" else key_body())
        assert response.status_code == 401 and response.json() == {"error": "signed_out"}, (method, path)
    assert rig.secrets.sets == 0


def test_a_write_needs_the_origin_and_the_csrf_header(rig: StorageRig) -> None:
    for headers in ({}, {"Origin": "http://evil.example", "X-ShelfSync": "1"}, {"X-ShelfSync": "1"}):
        assert rig.client.put(S3_RW_PATH, json=key_body(), headers=headers).status_code == 403
        assert rig.client.delete(S3_RW_PATH, headers=headers).status_code == 403
        assert rig.client.put(STORAGE_SETTINGS_PATH, json=GOOD_SETTINGS, headers=headers).status_code == 403
    assert rig.secrets.sets == 0


def test_the_default_app_has_an_in_memory_storage_service() -> None:
    from tests.support import make_harness

    client = make_harness().signed_in_client()
    assert client.put(S3_RW_PATH, json=key_body(), headers=WRITE_HEADERS).status_code == 204
    assert client.get(STORAGE_SETTINGS_PATH).json()["rw"]["access_key_id"] is not None
    assert isinstance(StorageService.development(), StorageService)
