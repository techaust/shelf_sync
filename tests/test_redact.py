"""LOG-01: redaction. One test per pattern family, the registry, and the properties."""

import json
import logging
import string
import threading

import pytest
from hypothesis import given
from hypothesis import strategies as st

from shelfsync import logs
from shelfsync.secure.redact import MASK, clear_secrets, redact, register_secret

# The fake secrets are built from pieces so no real-looking token sits in the source as one literal.
HEX40 = "0123456789abcdef" * 3
WOO_KEY = "c" + "k_" + HEX40[:40]
WOO_SECRET = "c" + "s_" + HEX40[:40]
AWS_KEY_ID = "AK" + "IAIOSFODNN7EXAMPLE"
AWS_TEMP_KEY_ID = "AS" + "IAIOSFODNN7EXAMPLE"
GH_CLASSIC = "gh" + "p_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
GH_OAUTH = "gh" + "o_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
GH_FINE = "github" + "_pat_" + "11ABCDEFG0abcdefghij_klmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRS"


@pytest.mark.parametrize(
    ("text", "secret", "expected"),
    [
        (f"key {WOO_KEY} used", WOO_KEY, f"key ck_{MASK} used"),
        (f"secret={WOO_SECRET}&x=1", WOO_SECRET, f"secret=cs_{MASK}&x=1"),
        (f"id {AWS_KEY_ID} ok", AWS_KEY_ID, f"id AKIA{MASK} ok"),
        (f"id {AWS_TEMP_KEY_ID} ok", AWS_TEMP_KEY_ID, f"id ASIA{MASK} ok"),
        (
            "aws_secret_access_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "wJalrXUtnFEMI",
            f"aws_secret_access_key={MASK}",
        ),
        ("AWS_SECRET_ACCESS_KEY: abcdef/12345+xyz==", "abcdef/12345", f"AWS_SECRET_ACCESS_KEY: {MASK}"),
        ("GET /f?X-Amz-Signature=deadbeef0123&a=1", "deadbeef0123", f"GET /f?X-Amz-Signature={MASK}&a=1"),
        ("GET /f?a=1&X-Amz-Credential=AKID%2F2026%2Fs3&b=2", "AKID%2F2026", f"GET /f?a=1&X-Amz-Credential={MASK}&b=2"),
        ("x-amz-security-token=FwoGZXIvYXdzEXAMPLE", "FwoGZXIvYXdz", f"x-amz-security-token={MASK}"),
        (f"token {GH_CLASSIC}", GH_CLASSIC, f"token ghp_{MASK}"),
        (f"token {GH_OAUTH}", GH_OAUTH, f"token gho_{MASK}"),
        (f"token {GH_FINE}", GH_FINE, f"token github_pat_{MASK}"),
        ("Authorization: Bearer abc.def.ghi", "abc.def.ghi", f"Authorization: {MASK}"),
        ("authorization=Basic dXNlcjpwYXNz", "dXNlcjpwYXNz", f"authorization={MASK}"),
        ("headers {'Authorization': 'Bearer abc123xyz'}", "abc123xyz", f"headers {{'Authorization': '{MASK}'}}"),
        ("sent Bearer abc123xyz.def to the store", "abc123xyz", f"sent Bearer {MASK} to the store"),
        (
            "Cookie: a=1; shelfsync_session=Zm9vYmFy_-x; b=2",
            "Zm9vYmFy_-x",
            f"Cookie: a=1; shelfsync_session={MASK}; b=2",
        ),
        (
            "open http://127.0.0.1:47615/#t=Zm9vYmFyEXAMPLE_-x now",
            "Zm9vYmFyEXAMPLE",
            f"open http://127.0.0.1:47615/#t={MASK} now",
        ),
        ('body {"ticket": "Zm9vYmFyEXAMPLE_-x"}', "Zm9vYmFyEXAMPLE", f'body {{"ticket": "{MASK}"}}'),
        ("params {'ticket': 'Zm9vYmFyEXAMPLE'}", "Zm9vYmFyEXAMPLE", f"params {{'ticket': '{MASK}'}}"),
        ("consumer_secret=abc123def456&oauth_nonce=1", "abc123def456", f"consumer_secret={MASK}&oauth_nonce=1"),
        ("oauth_signature=Zm9vYmFyEXAMPLE%3D", "Zm9vYmFyEXAMPLE", f"oauth_signature={MASK}"),
    ],
    ids=[
        "woo-key",
        "woo-secret",
        "aws-key-id",
        "aws-temp-key-id",
        "aws-secret-eq",
        "aws-secret-colon",
        "amz-signature",
        "amz-credential",
        "amz-token",
        "github-classic",
        "github-oauth",
        "github-fine-grained",
        "authorization-header",
        "authorization-basic",
        "authorization-in-a-dict",
        "bearer-alone",
        "session-cookie",
        "sign-in-fragment",
        "ticket-json",
        "ticket-dict",
        "consumer-secret",
        "oauth-signature",
    ],
)
def test_each_pattern_family_masks_and_keeps_its_label(text: str, secret: str, expected: str) -> None:
    """LOG-01: the label stays, then [redacted]."""
    result = redact(text)
    assert secret not in result
    assert result == expected


@pytest.mark.parametrize(
    "text",
    [
        "2026-10-26T09:05:03.000120Z",
        "jupiterx-4.61.0.zip",
        "d41d8cd98f00b204e9800998ecf8427e",  # an MD5
        "version 4.61.0 and 6.0.0-beta.2",
        "Port 47615 is in use, so ShelfSync started on 47616.",
        "lock_file_name_is_long_enough_to_look_like_a_key",
        "block_aaaaaaaaaaaaaaaaaaaaaaaa",
        "a short ck_abc",
        "AKIA-too-short",
        "authorization required",
        "the ticket was refused",
    ],
)
def test_ordinary_text_is_never_masked(text: str) -> None:
    """LOG-01: ISO times, file names, MD5s and versions pass through."""
    assert redact(text) == text


def test_registered_values_are_masked_wherever_they_appear() -> None:
    """LOG-01: the install token and, from M2, keyring secrets."""
    secret = "this-is-a-registered-value-123"
    assert register_secret(secret) is True
    assert redact(f"a {secret} b {secret}") == f"a {MASK} b {MASK}"
    assert redact(f"url?x={secret}&y=1") == f"url?x={MASK}&y=1"


def test_a_registered_value_that_contains_another_is_masked_whole() -> None:
    """LOG-01: the longest value wins."""
    short = "0123456789abcdef"
    long = short + "ghijklmnop"
    register_secret(short)
    register_secret(long)
    assert redact(f"x {long} y") == f"x {MASK} y"


def test_values_shorter_than_16_characters_are_not_registered() -> None:
    """LOG-01: a short value would mask ordinary words."""
    assert register_secret("short-value-15ch") is True  # exactly 16
    assert register_secret("short-value-1ch") is False
    assert redact("a short-value-1ch b") == "a short-value-1ch b"


def test_the_registry_is_thread_safe() -> None:
    """LOG-01: threads registering and redacting at once never fail and every value ends up masked."""
    values = [f"thread-secret-value-{index:04d}" for index in range(200)]
    errors: list[BaseException] = []

    def work(chunk: list[str]) -> None:
        try:
            for value in chunk:
                register_secret(value)
                redact(f"x {value} y")
        except BaseException as error:
            errors.append(error)

    threads = [threading.Thread(target=work, args=(values[i::4],)) for i in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert all(redact(value) == MASK for value in values)


def test_logs_redact_is_the_hook_and_delegates() -> None:
    """LOG-01: shelfsync.logs.redact stays the named hook and masks."""
    assert logs.redact(f"key {WOO_KEY}") == f"key ck_{MASK}"


def test_job_id_and_step_are_redacted_in_log_lines(tmp_path_factory: pytest.TempPathFactory) -> None:
    """LOG-01: the JSON fields job_id and step go through redact too."""
    folder = tmp_path_factory.mktemp("logs")
    handler = logs.configure_logging(folder, retention_days=1)
    try:
        logging.getLogger("shelfsync.test").info("x", extra={"job_id": WOO_KEY, "step": f"Bearer {HEX40}"})
        handler.flush()
    finally:
        logs.remove_logging(handler)
    entry = json.loads((folder / logs.LOG_FILE_NAME).read_text(encoding="utf-8").splitlines()[0])
    assert WOO_KEY not in json.dumps(entry)
    assert HEX40 not in json.dumps(entry)
    assert entry["job_id"] == f"ck_{MASK}"
    assert entry["step"] == f"Bearer {MASK}"


_SECRET_ALPHABET = string.ascii_letters + string.digits + "-_"
secrets_strategy = st.text(alphabet=_SECRET_ALPHABET, min_size=16, max_size=64)


@given(secret=secrets_strategy, before=st.text(max_size=80), after=st.text(max_size=80))
def test_property_a_registered_secret_never_survives_anywhere_in_the_text(secret: str, before: str, after: str) -> None:
    """LOG-01: random text with a registered secret inserted anywhere never keeps the secret."""
    clear_secrets()
    register_secret(secret)
    assert secret not in redact(f"{before}{secret}{after}")
    assert secret not in redact(f"{before}{secret}{after}{secret}")


@given(text=st.text(max_size=300))
def test_property_redact_is_idempotent(text: str) -> None:
    """LOG-01: redacting twice gives what redacting once gives."""
    clear_secrets()
    once = redact(text)
    assert redact(once) == once


@given(
    prefix=st.text(alphabet=string.ascii_letters + " :=#_", max_size=30),
    secret=st.text(alphabet=string.ascii_letters + string.digits, min_size=20, max_size=40),
)
def test_property_idempotent_on_text_that_holds_pattern_shaped_secrets(prefix: str, secret: str) -> None:
    """LOG-01: idempotence also on the shapes the patterns match."""
    clear_secrets()
    for text in (
        f"{prefix}ck_{secret}",
        f"{prefix}Bearer {secret}",
        f"{prefix}shelfsync_session={secret}",
        f"{prefix}#t={secret}",
        f'{prefix}"ticket": "{secret}"',
        f"{prefix}Authorization: {secret}",
    ):
        once = redact(text)
        assert redact(once) == once


@given(text=st.text(alphabet="0123456789 .-:/TZxyzmqw_\n", max_size=200))
def test_property_text_with_no_secret_comes_out_unchanged(text: str) -> None:
    """LOG-01: no secret, no change."""
    clear_secrets()
    assert redact(text) == text
