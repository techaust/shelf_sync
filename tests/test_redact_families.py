"""LOG-01: every pattern family, with neighbours made only of separators, and the keyword form of the ticket."""

import string

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from shelfsync.secure.redact import MASK, clear_secrets, redact

ALNUM = string.ascii_letters + string.digits
UPPER_DIGITS = string.ascii_uppercase + string.digits
URLSAFE = ALNUM + "-_"

# What may stand next to a secret in these tests: separators only (space, tab, newline, and the punctuation that
# ends or starts a value in a log line, a URL, a header or a cookie).
SEPARATORS = st.text(alphabet=" \t\n,;()<>|", max_size=6)

# (family, template with {s} for the secret, alphabet of the secret, shortest, longest)
FAMILIES = [
    ("woo-key", "c" + "k_{s}", ALNUM, 20, 50),
    ("woo-secret", "c" + "s_{s}", ALNUM, 20, 50),
    ("aws-key-id", "AK" + "IA{s}", UPPER_DIGITS, 16, 16),
    ("aws-temp-key-id", "AS" + "IA{s}", UPPER_DIGITS, 16, 16),
    ("aws-secret-key", "aws_secret_access_key={s}", ALNUM + "/+", 20, 40),
    ("aws-secret-key-camel", "SecretAccessKey={s}", ALNUM + "/+", 20, 40),
    ("aws-secret-key-json", '"SecretAccessKey": "{s}"', ALNUM + "/+", 20, 40),
    ("aws-session-token", "aws_session_token={s}", ALNUM + "/+=", 20, 80),
    ("aws-session-token-camel", "SessionToken={s}", ALNUM + "/+=", 20, 80),
    ("amz-signature", "X-Amz-Signature={s}", ALNUM, 16, 64),
    ("amz-credential", "X-Amz-Credential={s}", ALNUM + "%/", 16, 64),
    ("amz-security-token-header", "'X-Amz-Security-Token': '{s}'", ALNUM, 16, 64),
    ("github-classic", "gh" + "p_{s}", ALNUM, 20, 40),
    ("github-oauth", "gh" + "o_{s}", ALNUM, 20, 40),
    ("github-fine-grained", "github" + "_pat_{s}", ALNUM + "_", 20, 80),
    ("authorization-header", "Authorization: Bearer {s}", URLSAFE + ".", 12, 60),
    ("bearer", "Bearer {s}", URLSAFE + ".", 12, 60),
    ("session-cookie", "shelfsync_session={s}", URLSAFE, 12, 60),
    ("sign-in-fragment", "#t={s}", URLSAFE, 12, 60),
    ("ticket-json", '"ticket": "{s}"', URLSAFE, 12, 60),
    ("ticket-keyword", "ticket={s}", URLSAFE, 12, 60),
    ("ticket-keyword-quoted", "ticket='{s}'", URLSAFE, 12, 60),
    ("consumer-secret", "consumer_secret={s}", ALNUM, 12, 60),
    ("oauth-signature", "oauth_signature={s}", ALNUM + "%", 12, 60),
]


@pytest.mark.parametrize(
    ("family", "template", "alphabet", "shortest", "longest"), FAMILIES, ids=[f[0] for f in FAMILIES]
)
@given(data=st.data())
def test_property_the_secret_never_survives_among_separators(
    family: str, template: str, alphabet: str, shortest: int, longest: int, data: st.DataObject
) -> None:
    """LOG-01: for each pattern family, the secret inside the text is gone whatever separators surround it."""
    secret = data.draw(st.text(alphabet=alphabet, min_size=shortest, max_size=longest))
    before, after = data.draw(SEPARATORS), data.draw(SEPARATORS)
    assume(secret not in template.replace("{s}", ""))  # a "secret" that is part of the kept label can't be absent
    clear_secrets()
    result = redact(before + template.format(s=secret) + after)
    assert secret not in result, family
    assert MASK in result
    assert redact(result) == result  # and masking twice changes nothing


@pytest.mark.parametrize(
    ("text", "secret", "expected"),
    [
        ("GET /x?ticket=Zm9vYmFyEXAMPLE_-x&a=1", "Zm9vYmFyEXAMPLE", f"GET /x?ticket={MASK}&a=1"),
        ("params ticket='Zm9vYmFyEXAMPLE' done", "Zm9vYmFyEXAMPLE", f"params ticket='{MASK}' done"),
        ('args ticket="Zm9vYmFyEXAMPLE"', "Zm9vYmFyEXAMPLE", f'args ticket="{MASK}"'),
        ("Ticket = Zm9vYmFyEXAMPLE", "Zm9vYmFyEXAMPLE", f"Ticket = {MASK}"),
    ],
)
def test_the_keyword_form_of_the_ticket_is_masked(text: str, secret: str, expected: str) -> None:
    """LOG-01: ticket=... and ticket='...' (a call's keyword arguments), besides the JSON form."""
    result = redact(text)
    assert secret not in result
    assert result == expected


def test_words_that_only_contain_ticket_are_left_alone() -> None:
    """LOG-01: no mangling of ordinary text."""
    for text in ("the ticket was refused", "my_ticket=1 and tickets=2", "a ticket: expired"):
        assert redact(text) == text


def test_a_key_glued_to_a_letter_is_not_masked_the_documented_trade_off() -> None:
    """LOG-01: the left guard keeps words like `block_...` intact, so `x` + a key is not recognised by shape. (The
    exact-value registry still masks any registered secret in that position.)"""
    glued = "x" + "c" + "k_" + "0123456789abcdef0123"
    assert redact(glued) == glued
    assert redact("c" + "k_" + "0123456789abcdef0123") == f"ck_{MASK}"
