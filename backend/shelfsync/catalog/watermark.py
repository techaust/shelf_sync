"""The incremental read's watermark (SYNC-01). Pure.

The watermark is a store's own `date_modified_gmt` text (`YYYY-MM-DDTHH:MM:SS`, GMT), never the PC's clock. After a read
that fully worked (a full read, an incremental) it becomes the larger of itself and **the largest date the read saw
less the read's own duration** (m3.2 F3: a product edited while a long read was past its id has a date inside the
read's span but wasn't in the read; stepping back by the duration reads it next time). The duration is measured on the
monotonic clock from the read's first products request to its last answer, rounded up to whole seconds. The next
incremental asks for `modified_after` the watermark less 2 minutes (an overlap: an edit in the same second as the
watermark, or a boundary the store doesn't include, is read again; reading it again changes nothing). The PC's wall
clock only keeps out a store date more than a day ahead of it: a wrong store clock or a hostile answer would otherwise
hide every later edit from the incrementals (the nightly snapshot still reads such a product).
"""

import contextlib
import re
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from shelfsync.catalog.model import Product

OVERLAP = timedelta(minutes=2)
FUTURE_LIMIT = timedelta(days=1)
GMT_FORMAT = "%Y-%m-%dT%H:%M:%S"
_GMT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}")  # ASCII digits only (F7)


def _parse(date: str) -> datetime:
    if _GMT.fullmatch(date) is None:
        raise ValueError("a watermark is a store date, YYYY-MM-DDTHH:MM:SS")
    try:
        return datetime.strptime(date, GMT_FORMAT)
    except ValueError:
        raise ValueError("a watermark is a store date, YYYY-MM-DDTHH:MM:SS") from None


def _earlier(date: str, by: timedelta) -> str:
    try:
        return (_parse(date) - by).strftime(GMT_FORMAT)
    except OverflowError:
        raise ValueError("a watermark is a store date, YYYY-MM-DDTHH:MM:SS") from None


def modified_after(watermark: str) -> str:
    """The incremental's `modified_after`: the watermark less 2 minutes, in the same form. `ValueError` for anything
    that isn't a store date."""
    return _earlier(watermark, OVERLAP)


def next_watermark(current: str | None, products: Iterable[Product], now: datetime, seconds: int = 0) -> str | None:
    """The watermark after a read that fully worked: the larger of `current` and the products' largest own date less
    `seconds` (the read's duration), leaving out a date more than a day ahead of `now` (aware) and any that isn't a
    store date."""
    limit = (now.astimezone(UTC) + FUTURE_LIMIT).strftime(GMT_FORMAT)
    dates = [
        product.modified_gmt
        for product in products
        if product.modified_gmt is not None
        and _GMT.fullmatch(product.modified_gmt) is not None
        and product.modified_gmt <= limit
    ]
    found: list[str] = [current] if current is not None else []
    if dates:
        with contextlib.suppress(ValueError):  # a date too early to step back from never becomes the watermark
            found.append(_earlier(max(dates), timedelta(seconds=max(seconds, 0))))
    return max(found) if found else None
