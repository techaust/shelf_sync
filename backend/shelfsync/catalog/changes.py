"""Change detection for m3.3 (SYNC-01, SYNC-03, SYNC-04): what changed on a store outside ShelfSync. Pure: no database,
no network.

The saves that bring a store's state into the catalog (an incremental, `db.catalog.save_incremental`; a snapshot,
`db.catalog.apply_snapshot`) compare each catalog product **before** the save with what the store has **now**, and
return one `Change` per product that differs, so each change is reported once: by the save that first saw it.
- `changed`: its downloads (id, name and file, in order), slug, status or type differ (`fields` says which);
- `trashed`: it is in the trash now and wasn't before (`fields` holds every field that differs, `status` among them);
- `deleted`: the snapshot's listing, which holds every product of the store trash included, doesn't hold it any more
  (only a snapshot can say so; `after` is None).
Until M5 ShelfSync writes nothing to a store, so every change is one made outside it; from M5 its own writes are told
apart by the activity log. A new product isn't a change (the incremental links it as a full read would).
"""

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Literal

from shelfsync.catalog.model import Download, Product

TRASH = "trash"
CHANGE_FIELDS = ("downloads", "slug", "status", "type")

ChangeKind = Literal["changed", "trashed", "deleted"]
ChangeSource = Literal["incremental", "snapshot"]


@dataclass(frozen=True)
class ProductState:
    """What change detection compares of one store product."""

    wc_id: int
    slug: str
    status: str
    type: str
    downloads: tuple[Download, ...]


@dataclass(frozen=True)
class Change:
    store_id: int
    wc_id: int
    kind: ChangeKind
    fields: tuple[str, ...]  # the `CHANGE_FIELDS` that differ, in that order; empty for `deleted`
    before: ProductState
    after: ProductState | None  # None: deleted
    source: ChangeSource


def state_of(product: Product) -> ProductState:
    return ProductState(product.wc_id, product.slug, product.status, product.type, product.downloads)


def compare(store_id: int, before: ProductState, after: ProductState | None, source: ChangeSource) -> Change | None:
    """The change from `before` to `after` (None: the product is gone from the store), or None when nothing that
    change detection looks at differs."""
    if after is None:
        return Change(store_id, before.wc_id, "deleted", (), before, None, source)
    if before.wc_id != after.wc_id:
        raise ValueError("two different products")
    fields = tuple(name for name in CHANGE_FIELDS if getattr(before, name) != getattr(after, name))
    if not fields:
        return None
    kind: ChangeKind = "trashed" if after.status == TRASH and before.status != TRASH else "changed"
    return Change(store_id, before.wc_id, kind, fields, before, after, source)


def detect(
    store_id: int,
    before: Mapping[int, ProductState],
    after: Mapping[int, ProductState],
    source: ChangeSource,
    deleted: Collection[int] = (),
) -> list[Change]:
    """Every change, by WooCommerce id: each product in both `before` and `after` that differs, and each id in
    `deleted` (which must be in `before` and not in `after`). Products only in `after` are new, not changes."""
    found: list[Change] = []
    for wc_id in sorted(before):
        if wc_id in after:
            change = compare(store_id, before[wc_id], after[wc_id], source)
        elif wc_id in deleted:
            change = compare(store_id, before[wc_id], None, source)
        else:
            change = None
        if change is not None:
            found.append(change)
    if any(wc_id not in before or wc_id in after for wc_id in deleted):
        raise ValueError("a deleted product must be in the catalog and missing from the store")
    return found


def counts(changes: Collection[Change]) -> dict[ChangeKind, int]:
    """How many of each kind (for the log line: counts only, never a slug or a file)."""
    tally: dict[ChangeKind, int] = {"changed": 0, "trashed": 0, "deleted": 0}
    for change in changes:
        tally[change.kind] += 1
    return tally
