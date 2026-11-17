"""Download slots (CAT-05). Pure: no database, no network.

- **The main slot** is the download whose name equals the store's `main_button` (default `Download`). When no download
  has that name and the product has **exactly one** download, that one is the main slot (Lead (proposed), m3.1; L1
  counts how often). Otherwise the product has no main slot on that store.
- **Extra slots** are the other downloads, paired across the item's stores by their **exact** name.
- A second download with the same name on one product (a second `Download`, or two extras of one name) can't be told
  apart from the first, so only the first is put in the slot and the rest are counted as `unslotted` (m3.3 reports
  them; M5 decides before any write).
- A slot is found again by what it is (the main one, or an extra's name), so its id never changes across reads. A new
  main slot takes the name of the download that made it.
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
class Assignment:
    """A download put in a slot: the existing `slot_id`, or `new_slots[new_slot]` of the same plan."""

    download: Download
    slot_id: int | None = None
    new_slot: int | None = None


@dataclass(frozen=True)
class SlotPlan:
    new_slots: list[NewSlot]
    assignments: list[Assignment]
    unslotted: int
    main_by_single: bool  # the main slot came from the one-download rule, not from the name


def main_download(downloads: Sequence[Download], main_button: str) -> tuple[int | None, bool]:
    """The index of the main download and whether the one-download rule chose it (None: no main download)."""
    for index, download in enumerate(downloads):
        if download.name == main_button:
            return index, False
    if len(downloads) == 1:
        return 0, True
    return None, False


def plan_slots(downloads: Sequence[Download], main_button: str, existing: Sequence[SlotRef]) -> SlotPlan:
    """The slots one store's product fills, given the item's slots so far."""
    main_index, by_single = main_download(downloads, main_button)
    main_slot = next((slot.id for slot in existing if slot.is_main), None)
    extras = {slot.name: slot.id for slot in existing if not slot.is_main}
    new_slots: list[NewSlot] = []
    new_extras: dict[str, int] = {}
    assignments: list[Assignment] = []
    used_names: set[str] = set()
    unslotted = 0
    for index, download in enumerate(downloads):
        if index == main_index:
            if main_slot is not None:
                assignments.append(Assignment(download, slot_id=main_slot))
            else:
                new_slots.append(NewSlot(download.name, True))
                assignments.append(Assignment(download, new_slot=len(new_slots) - 1))
            used_names.add(download.name)
            continue
        if download.name in used_names:
            unslotted += 1
            continue
        used_names.add(download.name)
        if download.name in extras:
            assignments.append(Assignment(download, slot_id=extras[download.name]))
        else:
            if download.name not in new_extras:
                new_slots.append(NewSlot(download.name, False))
                new_extras[download.name] = len(new_slots) - 1
            assignments.append(Assignment(download, new_slot=new_extras[download.name]))
    return SlotPlan(new_slots, assignments, unslotted, main_index is not None and by_single)
