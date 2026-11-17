"""Download slots (CAT-05). Pure: no database, no network.

An item's slots are planned from **every store's present product at once** (one product per store: the save picks
the lowest WooCommerce id), so the result never depends on which store was saved first:
- **The main slot** holds each store's download whose name equals that store's `main_button` (default `Download`).
- **Extra slots** hold the other downloads, paired across the item's stores by their **exact** name.
- **The one-download rule** (Lead (proposed), m3.1): a store whose product has no download named like its button and
  exactly one download puts that one in the main slot, **unless another store has a download of that same name as an
  extra**: then it goes to that extra slot (m3.1 review 1, finding 4). L1 counts how often the rule is used.
- A second download with the same name on one product (a second `Download`, or two extras of one name) can't be told
  apart from the first, so only the first is put in a slot and the rest are counted as `unslotted` (m3.3 reports them;
  M5 decides before any write).
- A slot is found again by what it is (the main one, or an extra's name), so its id never changes across reads. The
  main slot is named after the main download of the lowest store id that has one named like its button, else after
  the one-download rule's download (`ItemSlotPlan.main_name`).
"""

from collections.abc import Sequence
from dataclasses import dataclass

from shelfsync.catalog.model import Download


@dataclass(frozen=True)
class SlotRef:
    """A slot already saved for the item."""

    id: int
    name: str
    is_main: bool


@dataclass(frozen=True)
class NewSlot:
    name: str
    is_main: bool


@dataclass(frozen=True)
class StoreDownloads:
    """One store's present product of the item: its downloads, and the store's main button."""

    store_id: int
    downloads: tuple[Download, ...]
    main_button: str


@dataclass(frozen=True)
class Placement:
    """A store's download put in a slot: the existing `slot_id`, or `new_slots[new_slot]` of the same plan."""

    store_id: int
    download: Download
    slot_id: int | None = None
    new_slot: int | None = None


@dataclass(frozen=True)
class StoreCounts:
    unslotted: int  # downloads in no slot (a name repeated on the product)
    main_by_single: bool  # the main slot came from the one-download rule


@dataclass(frozen=True)
class ItemSlotPlan:
    new_slots: list[NewSlot]
    placements: list[Placement]
    main_name: str | None  # what the main slot is to be called; None: no store has a main download
    counts: dict[int, StoreCounts]


def main_download(downloads: Sequence[Download], main_button: str) -> tuple[int | None, bool]:
    """One product on its own (L1's counts): the index of the main download and whether the one-download rule chose
    it (None: no main download)."""
    for index, download in enumerate(downloads):
        if download.name == main_button:
            return index, False
    if len(downloads) == 1:
        return 0, True
    return None, False


def _named(store: StoreDownloads) -> int | None:
    return next((index for index, d in enumerate(store.downloads) if d.name == store.main_button), None)


def plan_item_slots(stores: Sequence[StoreDownloads], existing: Sequence[SlotRef]) -> ItemSlotPlan:
    """Where each store's downloads go, given the item's slots so far (the module text says how)."""
    ordered = sorted(stores, key=lambda store: store.store_id)
    named = {store.store_id: _named(store) for store in ordered}
    # The extras' names from the stores whose downloads are decided without the one-download rule.
    extra_names: dict[int, set[str]] = {}
    for store in ordered:
        index = named[store.store_id]
        if index is None and len(store.downloads) == 1:
            continue
        its_main = store.downloads[index].name if index is not None else None
        extra_names[store.store_id] = {
            d.name for position, d in enumerate(store.downloads) if position != index and d.name != its_main
        }
    main_of: dict[int, int | None] = {}
    by_single: dict[int, bool] = {}
    for store in ordered:
        index = named[store.store_id]
        single = False
        if index is None and len(store.downloads) == 1:
            others = set[str]().union(*(names for sid, names in extra_names.items() if sid != store.store_id))
            if store.downloads[0].name not in others:
                index, single = 0, True
        main_of[store.store_id] = index
        by_single[store.store_id] = single

    main_slot = next((slot.id for slot in existing if slot.is_main), None)
    extras = {slot.name: slot.id for slot in existing if not slot.is_main}
    new_slots: list[NewSlot] = []
    new_main: int | None = None
    new_extras: dict[str, int] = {}
    placements: list[Placement] = []
    counts: dict[int, StoreCounts] = {}
    for store in ordered:
        used: set[str] = set()
        unslotted = 0
        for position, download in enumerate(store.downloads):
            if position == main_of[store.store_id]:
                if main_slot is None and new_main is None:
                    new_slots.append(NewSlot(download.name, True))
                    new_main = len(new_slots) - 1
                placements.append(Placement(store.store_id, download, slot_id=main_slot, new_slot=new_main))
                used.add(download.name)
                continue
            if download.name in used:
                unslotted += 1
                continue
            used.add(download.name)
            if download.name in extras:
                placements.append(Placement(store.store_id, download, slot_id=extras[download.name]))
                continue
            if download.name not in new_extras:
                new_slots.append(NewSlot(download.name, False))
                new_extras[download.name] = len(new_slots) - 1
            placements.append(Placement(store.store_id, download, new_slot=new_extras[download.name]))
        counts[store.store_id] = StoreCounts(unslotted, by_single[store.store_id])

    main_name: str | None = None
    for prefer_named in (True, False):
        for store in ordered:
            index = main_of[store.store_id]
            if index is not None and by_single[store.store_id] != prefer_named:
                main_name = store.downloads[index].name
                break
        if main_name is not None:
            break
    return ItemSlotPlan(new_slots, placements, main_name, counts)
