"""The incremental read's watermark (SYNC-01). Pure.

The watermark is a store's own `date_modified_gmt` text (`YYYY-MM-DDTHH:MM:SS`, GMT), never the PC's clock: the largest
one the last full read saved, then the largest one each incremental that fully worked returned. The next incremental
asks for `modified_after` the watermark less 2 minutes (an overlap: an edit made in the same second as the watermark,
or a boundary the store doesn't include, is read again; reading it again changes nothing). The PC's clock only keeps out
a store date more than a day ahead of it: a wrong store clock or a hostile answer would otherwise hide every later
edit from the incrementals (the nightly snapshot still reads such a product).
"""

import re
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from shelfsync.catalog.model import Product

OVERLAP = timedelta(minutes=2)
FUTURE_LIMIT = timedelta(days=1)
GMT_FORMAT = "%Y-%m-%dT%H:%M:%S"
_GMT = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


def modified_after(watermark: str) -> str:
    """The incremental's `modified_after`: the watermark less 2 minutes, in the same form. `ValueError` for anything
    that isn't a store date."""
    if _GMT.fullmatch(watermark) is None:
        raise ValueError("a watermark is a store date, YYYY-MM-DDTHH:MM:SS")
    try:
        return (datetime.strptime(watermark, GMT_FORMAT) - OVERLAP).strftime(GMT_FORMAT)
    except ValueError, OverflowError:
        raise ValueError("a watermark is a store date, YYYY-MM-DDTHH:MM:SS") from None


def next_watermark(current: str | None, products: Iterable[Product], now: datetime) -> str | None:
    """The watermark after a read that fully worked: the largest of `current` and the products' own dates, leaving
    out a date more than a day ahead of `now` (aware)."""
    limit = (now.astimezone(UTC) + FUTURE_LIMIT).strftime(GMT_FORMAT)
    found = [
        product.modified_gmt
        for product in products
        if product.modified_gmt is not None and product.modified_gmt <= limit
    ]
    if current is not None:
        found.append(current)
    return max(found) if found else None
