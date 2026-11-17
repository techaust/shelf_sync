"""Slugs and titles (CAT-02, CAT-03): which slugs may be linked, the edit distance, WordPress's `-N` suffix and the
normalised title. Pure functions, standard library only."""

import html
import re
import unicodedata

TRASHED_SUFFIX = "__trashed"  # WordPress renames a trashed post's slug to `<slug>__trashed`
_WP_SUFFIX = re.compile(r"-([2-9]|[1-9][0-9]+)")  # WordPress's `-2`, `-3`, ... for a slug already taken
_SPACES = re.compile(r"\s+")


def is_linkable_slug(slug: str) -> bool:
    """A slug that may link products across stores: not empty (a draft can have none) and not a trashed one."""
    return bool(slug) and not slug.endswith(TRASHED_SUFFIX)


def edit_distance(first: str, second: str, limit: int | None = None) -> int:
    """The Levenshtein distance (insert, delete or replace one character). With `limit`, any distance above it is
    reported as `limit + 1`, and the work stops as soon as that is certain."""
    if first == second:
        return 0
    if len(first) < len(second):
        first, second = second, first
    if limit is not None and len(first) - len(second) > limit:
        return limit + 1
    previous = list(range(len(second) + 1))
    for row, a in enumerate(first, start=1):
        current = [row]
        for column, b in enumerate(second, start=1):
            current.append(min(previous[column] + 1, current[column - 1] + 1, previous[column - 1] + (a != b)))
        if limit is not None and min(current) > limit:
            return limit + 1
        previous = current
    distance = previous[-1]
    return distance if limit is None or distance <= limit else limit + 1


def wp_suffix_pair(first: str, second: str) -> bool:
    """True when one slug is the other plus WordPress's `-N` suffix (N of 2 or more, no leading zero)."""
    if len(first) == len(second):
        return False
    short, long = (first, second) if len(first) < len(second) else (second, first)
    return bool(short) and long.startswith(short) and _WP_SUFFIX.fullmatch(long[len(short) :]) is not None


def normalise_title(title: str) -> str:
    """The title compared for a near miss (CAT-03): `html.unescape`, Unicode NFKC, casefold, every punctuation
    character (Unicode category P*) to a space, spaces collapsed and trimmed. Edition words are kept: "X Pro" and "X"
    stay different (m3.0 correction 7)."""
    text = unicodedata.normalize("NFKC", html.unescape(title)).casefold()
    text = "".join(" " if unicodedata.category(character).startswith("P") else character for character in text)
    return _SPACES.sub(" ", text).strip()
