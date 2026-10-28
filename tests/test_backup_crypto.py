"""SET-05: the `.ssbak` file's sealing and opening (`secure/backup_crypto.py`), with no I/O.

The scrypt cost is lowered for speed through the module's own constant (the writer and the reader move together, and no
production code touches it); the real parameters run in the tests marked "real parameters", at least once each way.
"""

import base64
import contextlib
import copy
import hashlib
import json
import unicodedata
from collections.abc import Callable
from typing import Any

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from shelfsync.secure import backup_crypto
from shelfsync.secure.backup_crypto import (
    ExportInvalid,
    ExportTooNew,
    PassphraseInvalid,
    PassphraseRequired,
    WrongPassphrase,
    canonical,
    check_header,
    check_passphrase,
    dumps,
    open_envelope,
    parse_envelope,
    seal,
)

REAL_N = backup_crypto.SCRYPT_N  # read before any test lowers it
PASSPHRASE = "correct horse battery staple"
CREATED = "2026-10-28T10:00:00.123456Z"
PAYLOAD = {"settings": {"theme": "dark"}, "stores": [], "catalog": None, "note": "café ☃"}
BODY = canonical(PAYLOAD)
FAST_N = 2**10


@pytest.fixture(autouse=True)
def fast_kdf(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(backup_crypto, "SCRYPT_N", FAST_N)


def make(passphrase: str | None = PASSPHRASE, body: bytes = BODY, schema: int = 2) -> dict[str, Any]:
    return seal(body, passphrase, created_at=CREATED, app_version="0.1.0", schema=schema)


def reencode(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


class ScryptCalled(AssertionError):
    pass


# ---- the decided parameters ----


def test_the_decided_costs_cipher_and_sizes_are_pinned() -> None:
    assert (REAL_N, backup_crypto.SCRYPT_R, backup_crypto.SCRYPT_P) == (131072, 8, 1)
    assert backup_crypto.SCRYPT_MAXMEM == 256 * 1024 * 1024
    assert (backup_crypto.CIPHER, backup_crypto.KDF_NAME) == ("AES-256-GCM", "scrypt")
    assert (backup_crypto.SALT_BYTES, backup_crypto.NONCE_BYTES, backup_crypto.KEY_BYTES) == (16, 12, 32)
    assert (backup_crypto.PASSPHRASE_MIN, backup_crypto.PASSPHRASE_MAX) == (12, 1024)
    assert backup_crypto.MAX_FILE_CHARS == 1024 * 1024  # format v1; v2 (the catalog) raises it


def test_real_parameters_round_trip_and_match_an_independent_derivation(monkeypatch: pytest.MonkeyPatch) -> None:
    """The real N = 2**17 (about 128 MiB): the file says so, and plain `hashlib.scrypt` plus `AESGCM` open it."""
    monkeypatch.setattr(backup_crypto, "SCRYPT_N", REAL_N)
    envelope = make()
    assert (
        envelope["encryption"]["n"] == 131072 and envelope["encryption"]["r"] == 8 and envelope["encryption"]["p"] == 1
    )
    assert open_envelope(envelope, PASSPHRASE) == BODY
    encryption = envelope["encryption"]
    key = hashlib.scrypt(
        unicodedata.normalize("NFC", PASSPHRASE).encode("utf-8"),
        salt=base64.b64decode(encryption["salt"]),
        n=2**17,
        r=8,
        p=1,
        maxmem=256 * 1024 * 1024,
        dklen=32,
    )
    aad = json.dumps(
        {k: v for k, v in envelope.items() if k != "ciphertext"},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")
    raw = base64.b64decode(envelope["ciphertext"])
    assert len(raw) == len(BODY) + 16  # the 16-byte tag is appended
    assert AESGCM(key).decrypt(base64.b64decode(encryption["nonce"]), raw, aad) == BODY


def test_real_parameters_refuse_a_wrong_passphrase(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(backup_crypto, "SCRYPT_N", REAL_N)
    envelope = make()
    with pytest.raises(WrongPassphrase):
        open_envelope(envelope, PASSPHRASE + "x")


# ---- round trips ----


def test_an_encrypted_file_round_trips_and_a_plain_file_round_trips() -> None:
    assert open_envelope(make(), PASSPHRASE) == BODY
    assert open_envelope(make(None), None) == BODY
    assert open_envelope(parse_envelope(dumps(make())), PASSPHRASE) == BODY  # through the file text too
    assert open_envelope(parse_envelope(dumps(make(None))), None) == BODY


def test_the_file_text_is_ascii_compact_json() -> None:
    text = dumps(make())
    assert text.isascii() and " " not in text.replace("shelfsync-export", "")
    assert json.loads(text)["format"] == "shelfsync-export"


def test_every_export_has_a_new_salt_and_a_new_nonce() -> None:
    first, second = make(), make()
    assert first["encryption"]["salt"] != second["encryption"]["salt"]
    assert first["encryption"]["nonce"] != second["encryption"]["nonce"]
    assert first["ciphertext"] != second["ciphertext"]


def test_the_header_fields_are_exactly_the_documented_ones() -> None:
    encrypted, plain = make(), make(None)
    assert set(encrypted) == {"format", "version", "created_at", "app_version", "schema", "encryption", "ciphertext"}
    assert set(plain) == {"format", "version", "created_at", "app_version", "schema", "encryption", "payload", "sha256"}
    assert plain["encryption"] is None and plain["payload"] == PAYLOAD
    assert plain["sha256"] == hashlib.sha256(BODY).hexdigest()
    assert set(encrypted["encryption"]) == {"cipher", "kdf", "n", "r", "p", "salt", "nonce"}
    assert encrypted["version"] == 1 and encrypted["format"] == "shelfsync-export"


def test_a_passphrase_given_for_a_plain_file_is_ignored() -> None:
    assert open_envelope(make(None), "not needed at all") == BODY


def test_the_composed_and_the_decomposed_passphrase_are_the_same_passphrase() -> None:
    composed = "café au lait 2026"
    decomposed = unicodedata.normalize("NFD", composed)
    assert composed != decomposed
    assert open_envelope(make(composed), decomposed) == BODY
    assert open_envelope(make(decomposed), composed) == BODY


# ---- the passphrase rules ----


@pytest.mark.parametrize("length", [0, 1, 11])
def test_a_short_passphrase_is_refused(length: int) -> None:
    with pytest.raises(PassphraseInvalid):
        check_passphrase("a" * length)
    with pytest.raises(PassphraseInvalid):
        make("a" * length)


@pytest.mark.parametrize("length", [12, 13, 1024])
def test_a_12_to_1024_character_passphrase_is_accepted(length: int) -> None:
    assert check_passphrase("a" * length) == "a" * length


def test_a_passphrase_over_1024_characters_is_refused() -> None:
    with pytest.raises(PassphraseInvalid):
        check_passphrase("a" * 1025)


def test_the_length_is_counted_after_nfc() -> None:
    typed = "é" * 600  # 1200 typed characters, 600 after NFC
    assert check_passphrase(typed) == typed
    with pytest.raises(PassphraseInvalid):
        check_passphrase("é" * 5)  # 10 typed, 5 after NFC: too short


def test_a_lone_surrogate_is_refused() -> None:
    with pytest.raises(PassphraseInvalid):
        check_passphrase("\ud800" * 20)


# ---- refusals ----


def test_a_wrong_passphrase_fails_and_no_passphrase_is_asked_for() -> None:
    envelope = make()
    with pytest.raises(WrongPassphrase):
        open_envelope(envelope, "a different passphrase")
    with pytest.raises(PassphraseRequired):
        open_envelope(envelope, None)


def test_a_flipped_ciphertext_byte_fails_the_tag() -> None:
    envelope = make()
    raw = bytearray(base64.b64decode(envelope["ciphertext"]))
    raw[0] ^= 1
    envelope["ciphertext"] = reencode(bytes(raw))
    with pytest.raises(WrongPassphrase):
        open_envelope(envelope, PASSPHRASE)


def test_a_flipped_tag_byte_and_a_cut_ciphertext_fail() -> None:
    envelope = make()
    raw = base64.b64decode(envelope["ciphertext"])
    flipped = bytearray(raw)
    flipped[-1] ^= 0x80
    with pytest.raises(WrongPassphrase):
        open_envelope({**envelope, "ciphertext": reencode(bytes(flipped))}, PASSPHRASE)
    with pytest.raises(WrongPassphrase):
        open_envelope({**envelope, "ciphertext": reencode(raw[:-1])}, PASSPHRASE)
    with pytest.raises(ExportInvalid):  # shorter than a tag
        open_envelope({**envelope, "ciphertext": reencode(raw[:15])}, PASSPHRASE)
    with pytest.raises(WrongPassphrase):
        open_envelope({**envelope, "ciphertext": reencode(raw + b"\x00")}, PASSPHRASE)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("created_at", "2026-10-28T10:00:01Z"),
        ("app_version", "9.9.9"),
        ("schema", 3),
        ("schema", 1),
    ],
)
def test_a_changed_header_field_fails_the_tag_because_the_header_is_the_aad(field: str, value: object) -> None:
    envelope = make()
    envelope[field] = value
    with pytest.raises(WrongPassphrase):
        open_envelope(envelope, PASSPHRASE)


@pytest.mark.parametrize("field", ["salt", "nonce"])
def test_a_changed_salt_or_nonce_fails_the_tag(field: str) -> None:
    envelope = make()
    raw = bytearray(base64.b64decode(envelope["encryption"][field]))
    raw[0] ^= 1
    envelope["encryption"][field] = reencode(bytes(raw))
    with pytest.raises(WrongPassphrase):
        open_envelope(envelope, PASSPHRASE)


def test_the_aad_is_the_canonical_json_of_the_header_without_the_ciphertext() -> None:
    envelope = make()
    header = {k: v for k, v in envelope.items() if k != "ciphertext"}
    aad = json.dumps(header, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    key = backup_crypto.derive_key(PASSPHRASE, base64.b64decode(envelope["encryption"]["salt"]))
    box = AESGCM(key)
    nonce = base64.b64decode(envelope["encryption"]["nonce"])
    raw = base64.b64decode(envelope["ciphertext"])
    assert box.decrypt(nonce, raw, aad) == BODY
    for wrong in (b"", aad + b" ", json.dumps(header).encode()):
        with pytest.raises(Exception):  # noqa: B017 - cryptography's InvalidTag
            box.decrypt(nonce, raw, wrong)


def _saved_file() -> dict[str, Any]:
    """An encrypted file made with a real (fast) derivation, before `no_scrypt` is switched on."""
    return make()


@pytest.mark.parametrize(
    "change",
    [
        lambda e: e["encryption"].update(n=backup_crypto.SCRYPT_N * 2),
        lambda e: e["encryption"].update(n=2**20),
        lambda e: e["encryption"].update(n=2**40),
        lambda e: e["encryption"].update(n=backup_crypto.SCRYPT_N // 2),
        lambda e: e["encryption"].update(r=16),
        lambda e: e["encryption"].update(r=1),
        lambda e: e["encryption"].update(p=2),
        lambda e: e["encryption"].update(p=16),
        lambda e: e["encryption"].update(n=True),
        lambda e: e["encryption"].update(n=float(backup_crypto.SCRYPT_N)),
        lambda e: e["encryption"].update(n=str(backup_crypto.SCRYPT_N)),
        lambda e: e["encryption"].update(cipher="AES-128-GCM"),
        lambda e: e["encryption"].update(kdf="pbkdf2"),
        lambda e: e["encryption"].update(extra=1),
        lambda e: e["encryption"].pop("p"),
    ],
)
def test_a_file_asking_for_other_costs_or_algorithms_is_refused_before_any_derivation(
    change: Callable[[dict[str, Any]], object], monkeypatch: pytest.MonkeyPatch
) -> None:
    envelope = _saved_file()
    change(envelope)

    def boom(*args: object, **kwargs: object) -> bytes:
        raise ScryptCalled("a derivation ran")

    monkeypatch.setattr(backup_crypto.hashlib, "scrypt", boom)
    with pytest.raises(ExportInvalid):
        open_envelope(envelope, PASSPHRASE)
    with pytest.raises(ExportInvalid):
        check_header(envelope, max_schema=10)


@pytest.mark.parametrize(
    "change",
    [
        lambda e: e.update(format="other"),
        lambda e: e.pop("format"),
        lambda e: e.update(version=0),
        lambda e: e.update(version=-1),
        lambda e: e.update(version=True),
        lambda e: e.update(version=1.0),
        lambda e: e.update(version="1"),
        lambda e: e.update(created_at="yesterday"),
        lambda e: e.update(created_at=5),
        lambda e: e.update(app_version=""),
        lambda e: e.update(app_version="x" * 65),
        lambda e: e.update(app_version="1.0\n2"),
        lambda e: e.update(app_version=1),
        lambda e: e.update(schema=0),
        lambda e: e.update(schema=True),
        lambda e: e.update(schema="2"),
        lambda e: e.update(schema=2_000_000),
        lambda e: e.update(extra="x"),
        lambda e: e.update(payload={}),
        lambda e: e.update(sha256="0" * 64),
        lambda e: e.pop("ciphertext"),
        lambda e: e.pop("encryption"),
        lambda e: e["encryption"].update(salt="not base64!"),
        lambda e: e["encryption"].update(salt=reencode(b"x" * 15)),
        lambda e: e["encryption"].update(salt=reencode(b"x" * 17)),
        lambda e: e["encryption"].update(nonce=reencode(b"x" * 11)),
        lambda e: e["encryption"].update(nonce=reencode(b"x" * 13)),
        lambda e: e["encryption"].update(nonce=base64.b64encode(b"x" * 12).decode().rstrip("=") + "\n"),
        lambda e: e["encryption"].update(salt=base64.urlsafe_b64encode(b"\xfb" * 16).decode()),
        lambda e: e["encryption"].update(salt=7),
        lambda e: e.update(ciphertext="***"),
        lambda e: e.update(ciphertext=reencode(b"x" * 20).rstrip("=")),
        lambda e: e.update(ciphertext=7),
        lambda e: e.update(encryption="AES"),
        lambda e: e.update(encryption=[]),
    ],
)
def test_a_malformed_encrypted_file_is_refused_as_invalid(change: Callable[[dict[str, Any]], object]) -> None:
    envelope = _saved_file()
    change(envelope)
    with pytest.raises(ExportInvalid):
        open_envelope(envelope, PASSPHRASE)


@pytest.mark.parametrize("not_an_envelope", [None, [], "text", 7, {}, {"format": "shelfsync-export"}, []])
def test_something_that_isnt_an_envelope_is_refused(not_an_envelope: object) -> None:
    with pytest.raises(ExportInvalid):
        open_envelope(not_an_envelope, PASSPHRASE)
    with pytest.raises(ExportInvalid):
        check_header(not_an_envelope, max_schema=5)


def test_a_newer_format_version_is_too_new_not_invalid() -> None:
    for version in (2, 3, 100):
        envelope = _saved_file()
        envelope["version"] = version
        with pytest.raises(ExportTooNew):
            check_header(envelope, max_schema=10)
        with pytest.raises(ExportTooNew):
            open_envelope(envelope, PASSPHRASE)
    plain = make(None)
    plain["version"] = 2
    with pytest.raises(ExportTooNew):
        open_envelope(plain, None)


def test_a_newer_schema_is_too_new_and_an_equal_or_older_one_passes() -> None:
    envelope = make(schema=4)
    with pytest.raises(ExportTooNew):
        check_header(envelope, max_schema=3)
    check_header(envelope, max_schema=4)
    check_header(envelope, max_schema=9)


def test_a_version_two_file_with_other_fields_is_too_new_before_its_fields_are_judged() -> None:
    with pytest.raises(ExportTooNew):
        check_header({"format": "shelfsync-export", "version": 2, "anything": 1}, max_schema=1)


# ---- plain files ----


def test_a_changed_plain_payload_fails_the_checksum() -> None:
    envelope = make(None)
    envelope["payload"] = {**envelope["payload"], "note": "changed"}
    with pytest.raises(ExportInvalid):
        open_envelope(envelope, None)


def test_a_plain_files_checksum_is_a_corruption_check_not_authenticity() -> None:
    """Whoever changes the payload can also change the checksum: the plain file says so, it is not signed."""
    envelope = make(None)
    changed = {**envelope["payload"], "note": "changed"}
    envelope["payload"] = changed
    envelope["sha256"] = hashlib.sha256(canonical(changed)).hexdigest()
    assert json.loads(open_envelope(envelope, None))["note"] == "changed"


@pytest.mark.parametrize(
    "change",
    [
        lambda e: e.pop("payload"),
        lambda e: e.pop("sha256"),
        lambda e: e.update(ciphertext="AAAA"),
        lambda e: e.update(payload=[1]),
        lambda e: e.update(payload="x"),
        lambda e: e.update(sha256="ABC"),
        lambda e: e.update(sha256="G" * 64),
        lambda e: e.update(sha256="A" * 64),
        lambda e: e.update(sha256=5),
    ],
)
def test_a_malformed_plain_file_is_refused(change: Callable[[dict[str, Any]], object]) -> None:
    envelope = make(None)
    change(envelope)
    with pytest.raises(ExportInvalid):
        open_envelope(envelope, None)


def test_a_plain_header_change_that_the_checksum_doesnt_cover_is_not_detected() -> None:
    """The checksum is over the payload only: a plain file's date can be edited (so a plain file isn't trusted)."""
    envelope = make(None)
    envelope["created_at"] = "2020-01-01T00:00:00Z"
    assert open_envelope(envelope, None) == BODY


# ---- the file text ----


def test_parse_refuses_duplicate_keys_at_any_depth() -> None:
    for text in (
        '{"format":"a","format":"b"}',
        '{"encryption":{"n":1,"n":2}}',
        '{"payload":{"stores":[{"code":"AA","code":"BB"}]}}',
    ):
        with pytest.raises(ExportInvalid):
            parse_envelope(text)


@pytest.mark.parametrize(
    "text",
    ["", "   ", "null", "[]", "5", '"x"', "{", "{'a': 1}", '{"a": NaN}', '{"a": Infinity}', '{"a": -Infinity}', "﻿{}"],
)
def test_parse_refuses_what_is_not_a_json_object(text: str) -> None:
    with pytest.raises(ExportInvalid):
        parse_envelope(text)


def test_parse_refuses_a_text_that_is_too_long(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(backup_crypto, "MAX_FILE_CHARS", 20)
    with pytest.raises(ExportInvalid):
        parse_envelope('{"a":"' + "x" * 30 + '"}')
    assert parse_envelope('{"a":1}') == {"a": 1}


def test_parse_refuses_very_deep_nesting_and_huge_numbers() -> None:
    with pytest.raises(ExportInvalid):
        parse_envelope("[" * 200_000)
    with pytest.raises(ExportInvalid):
        parse_envelope('{"a": ' + "9" * 5000 + "}")


def test_parse_refuses_a_non_string() -> None:
    with pytest.raises(ExportInvalid):
        parse_envelope(b"{}")  # type: ignore[arg-type]


def test_canonical_is_sorted_compact_ascii_and_refuses_nan() -> None:
    assert canonical({"b": 1, "a": ["é"]}) == b'{"a":["\\u00e9"],"b":1}'
    with pytest.raises(ValueError, match="Out of range"):
        canonical({"a": float("nan")})


def test_seal_refuses_a_bad_date_or_version_text() -> None:
    with pytest.raises(ExportInvalid):
        seal(BODY, None, created_at="not a date", app_version="1", schema=1)
    with pytest.raises(ExportInvalid):
        seal(BODY, None, created_at=CREATED, app_version="", schema=1)


def test_seal_refuses_a_payload_with_a_repeated_key_when_plain() -> None:
    with pytest.raises(ValueError, match="repeated"):
        seal(b'{"a":1,"a":2}', None, created_at=CREATED, app_version="1", schema=1)


# ---- properties ----


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(data=st.data())
def test_any_single_byte_change_to_the_ciphertext_fails(data: st.DataObject) -> None:
    envelope = _saved_file_cached()
    raw = base64.b64decode(envelope["ciphertext"])
    index = data.draw(st.integers(min_value=0, max_value=len(raw) - 1))
    delta = data.draw(st.integers(min_value=1, max_value=255))
    changed = bytearray(raw)
    changed[index] ^= delta
    broken = copy.deepcopy(envelope)
    broken["ciphertext"] = reencode(bytes(changed))
    with pytest.raises(WrongPassphrase):
        open_envelope(broken, PASSPHRASE)


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    payload=st.dictionaries(
        st.text(max_size=12),
        st.one_of(st.integers(-(2**40), 2**40), st.text(max_size=40), st.none(), st.booleans()),
        max_size=8,
    ),
    passphrase=st.text(min_size=12, max_size=60).filter(lambda t: len(unicodedata.normalize("NFC", t)) >= 12),
)
def test_any_payload_and_passphrase_round_trip(payload: dict[str, Any], passphrase: str) -> None:
    try:
        passphrase.encode("utf-8")
    except UnicodeEncodeError:
        return
    body = canonical(payload)
    assert open_envelope(seal(body, passphrase, created_at=CREATED, app_version="1", schema=1), passphrase) == body
    assert open_envelope(seal(body, None, created_at=CREATED, app_version="1", schema=1), None) == body


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(text=st.text(max_size=300))
def test_parse_never_fails_with_anything_but_an_export_error(text: str) -> None:
    with contextlib.suppress(ExportInvalid):
        parse_envelope(text)


_CACHE: dict[str, Any] = {}


def _saved_file_cached() -> dict[str, Any]:
    if "file" not in _CACHE:
        _CACHE["file"] = _saved_file()
    return _CACHE["file"]


def test_base64_must_be_in_its_one_canonical_form() -> None:
    """`QQ==` and `QR==` decode to the same byte; only the first is what this module writes."""
    assert backup_crypto._unb64("QQ==") == b"A"
    with pytest.raises(ExportInvalid):
        backup_crypto._unb64("QR==")


@pytest.mark.parametrize("error", [ValueError("limit"), MemoryError(), OverflowError()])
def test_scrypt_failing_is_key_derivation_failed_with_the_type_name_only(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    def boom(*args: object, **kwargs: object) -> bytes:
        raise error

    monkeypatch.setattr(backup_crypto.hashlib, "scrypt", boom)
    with pytest.raises(backup_crypto.KeyDerivationFailed) as caught:
        make()
    assert str(caught.value) == type(error).__name__
    with pytest.raises(backup_crypto.KeyDerivationFailed):
        open_envelope(_saved_file_cached(), PASSPHRASE)
    with pytest.raises(PassphraseInvalid):  # a bad passphrase is still its own refusal, before scrypt
        backup_crypto.derive_key("short", b"x" * 16)
