"""Redaction (LOG-01, 06 section 3): mask anything shaped like a secret, and every registered secret value.

`redact` is the one step every output path goes through. It works in two passes:
1. exact values registered with `register_secret` (the install token, and from M2 every secret read from
   Credential Manager) are masked wherever they appear;
2. patterns mask keys, tokens, signatures, auth headers and the sign-in values by their shape.

Known trade-off: the key and token patterns need a character that isn't a letter or digit (or the start of the
text) before the prefix, so `xck_...` glued to a letter is not masked. That keeps words like `block_...` intact.

The mask keeps the label and then writes `[redacted]` (`ck_[redacted]`, `Bearer [redacted]`,
`shelfsync_session=[redacted]`). Applying `redact` to its own output changes nothing. File names, ISO times, MD5
hashes and version strings don't match any pattern, so they pass through untouched.
"""

import re
import threading

MASK = "[redacted]"
MIN_REGISTERED_LENGTH = 16  # shorter values would mask ordinary text and aren't secrets worth guarding by value

_VALUE = r"[^\s&\"',;]+"  # a value runs to the next space, &, quote, comma or semicolon
_SEP = r"""["']?\s*[=:]\s*["']?"""  # `=`, `: `, `": "` between a label and its value

# (pattern, replacement). Order doesn't matter for the result: no mask re-creates a match.
_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # WooCommerce consumer key / secret: ck_ / cs_ followed by a long run of letters and digits (at least 20)
    (re.compile(r"(?<![A-Za-z0-9])(c[ks]_)[A-Za-z0-9]{20,}"), rf"\1{MASK}"),
    # AWS access key IDs
    (re.compile(r"(?<![A-Z0-9])(AKIA|ASIA)[A-Z0-9]{16}(?![A-Z0-9])"), rf"\1{MASK}"),
    # AWS secret key and pre-signed URL parts
    (re.compile(rf"(aws_secret_access_key{_SEP}){_VALUE}", re.IGNORECASE), rf"\1{MASK}"),
    (
        re.compile(rf"(X-Amz-(?:Signature|Credential|Security-Token)=){_VALUE}", re.IGNORECASE),
        rf"\1{MASK}",
    ),
    # GitHub tokens (docs.github.com, "About authentication to GitHub": ghp_ gho_ ghu_ ghs_ ghr_ github_pat_)
    (re.compile(r"(?<![A-Za-z0-9])(github_pat_)[A-Za-z0-9_]{20,}"), rf"\1{MASK}"),
    (re.compile(r"(?<![A-Za-z0-9])(gh[pousr]_)[A-Za-z0-9_]{20,}"), rf"\1{MASK}"),
    # An Authorization header (to the end of its line or quoted value), then any other `Bearer <token>`
    (re.compile(rf"(authorization{_SEP})[^\r\n\"']+", re.IGNORECASE), rf"\1{MASK}"),
    (re.compile(r"(?<![A-Za-z0-9])(Bearer\s+)[^\s\"',;]+", re.IGNORECASE), rf"\1{MASK}"),
    # ShelfSync's own sign-in values
    (re.compile(rf"(shelfsync_session{_SEP}){_VALUE}", re.IGNORECASE), rf"\1{MASK}"),
    (re.compile(r"(#t=)[^\s&\"',;]+"), rf"\1{MASK}"),
    (re.compile(r"""(["']ticket["']\s*:\s*["'])[^"']*"""), rf"\1{MASK}"),
    (re.compile(r"""(?<![A-Za-z0-9_])(ticket\s*=\s*["']?)[^\s&"',;]+""", re.IGNORECASE), rf"\1{MASK}"),
    # WooCommerce OAuth 1.0a parts
    (re.compile(rf"(consumer_secret{_SEP}){_VALUE}", re.IGNORECASE), rf"\1{MASK}"),
    (re.compile(rf"(oauth_signature{_SEP}){_VALUE}", re.IGNORECASE), rf"\1{MASK}"),
)

_lock = threading.Lock()
_secrets: set[str] = set()
_registered_pattern: re.Pattern[str] | None = None


def register_secret(value: str) -> bool:
    """Mask this exact value everywhere from now on. Returns False (and registers nothing) if it is shorter than 16
    characters. Thread-safe."""
    global _registered_pattern
    if len(value) < MIN_REGISTERED_LENGTH:
        return False
    with _lock:
        _secrets.add(value)
        # Longest first, so a secret that contains another one is masked whole.
        ordered = sorted(_secrets, key=len, reverse=True)
        _registered_pattern = re.compile("|".join(re.escape(item) for item in ordered))
    return True


def clear_secrets() -> None:
    """Forget every registered value (for tests)."""
    global _registered_pattern
    with _lock:
        _secrets.clear()
        _registered_pattern = None


def redact(text: str) -> str:
    """Mask registered secrets and anything shaped like one. Idempotent."""
    with _lock:
        registered = _registered_pattern
    if registered is not None:
        text = registered.sub(MASK, text)
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text
