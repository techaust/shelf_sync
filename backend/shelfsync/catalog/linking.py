"""Linking products into items (CAT-02) and finding near misses (CAT-03). Pure: no database, no network.

**Links.** An item is identified by its links (store id and WooCommerce id), so a link, once made, never moves: ids, the
owner's slug edits and later decisions survive every re-read, and a product whose slug changes later keeps its link
(m3.3 reports the change). A product not linked yet:
1. joins the item that already has a **present** product with the **same URL slug on another store** and has **no
   present product on this store** (a gone one doesn't block it: a product deleted and made again joins its old item);
   the lowest item id when several qualify, so the result never depends on order;
2. otherwise gets a new item whose canonical slug is its slug, when the slug fits the canonical pattern
   (`names.CANONICAL_SLUG_PATTERN`; a percent-encoded slug doesn't) and no other item holds it (the owner gave it to an
   item by an edit, or two products on one store share a slug); otherwise the new item gets **no** canonical slug
   (NULL) rather than a made-up one, and the owner can give it one (Lead (proposed), m3.1);
3. an empty slug (a draft) or a trashed slug (`<slug>__trashed`) is never linked by slug: such a product gets a new item
   with no canonical slug.
Products are taken in WooCommerce id order.

**Near misses.** Among the products whose item is on one store only, a pair across two stores is a candidate when the
slugs are within edit distance 2 or differ only by WordPress's `-N` suffix, **and** the normalised titles are equal.
Candidates are returned, never linked.
"""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

from shelfsync.catalog.model import Product
from shelfsync.catalog.names import (
    edit_distance,
    is_canonical_slug,
    is_linkable_slug,
    normalise_title,
    wp_suffix_pair,
)

NEAR_MISS_DISTANCE = 2


@dataclass(frozen=True)
class KnownLink:
    """A link already saved, with what its product looks like now (`present`: the last full read returned it)."""

    item_id: int
    store_id: int
    wc_id: int
    slug: str
    present: bool


@dataclass(frozen=True)
class NewItem:
    canonical_slug: str | None
    title: str
    type: str


@dataclass(frozen=True)
class PlannedLink:
    """A product to link: to the existing `item_id`, or to `new_items[new_item]` of the same plan."""

    wc_id: int
    item_id: int | None = None
    new_item: int | None = None


@dataclass(frozen=True)
class LinkPlan:
    new_items: list[NewItem]
    links: list[PlannedLink]


def plan_links(
    store_id: int, products: Iterable[Product], known: Sequence[KnownLink], taken_slugs: Iterable[str]
) -> LinkPlan:
    """The links to add after one store's full read. `products` are the store's present products; `known` every link
    on every store that isn't removed; `taken_slugs` every canonical slug in use."""
    linked_here = {link.wc_id for link in known if link.store_id == store_id}
    present_on: dict[int, set[int]] = defaultdict(set)  # item -> the stores where it has a present product
    by_slug: dict[str, set[int]] = defaultdict(set)
    for link in known:
        if not link.present:
            continue
        present_on[link.item_id].add(link.store_id)
        if link.store_id != store_id and is_linkable_slug(link.slug):
            by_slug[link.slug].add(link.item_id)
    taken = set(taken_slugs)
    new_items: list[NewItem] = []
    links: list[PlannedLink] = []
    for product in sorted(products, key=lambda row: row.wc_id):
        if product.wc_id in linked_here:
            continue
        linked_here.add(product.wc_id)
        if is_linkable_slug(product.slug):
            joinable = sorted(item for item in by_slug.get(product.slug, ()) if store_id not in present_on[item])
            if joinable:
                present_on[joinable[0]].add(store_id)
                links.append(PlannedLink(product.wc_id, item_id=joinable[0]))
                continue
            usable = is_canonical_slug(product.slug) and product.slug not in taken
            canonical: str | None = product.slug if usable else None
            if canonical is not None:
                taken.add(canonical)
        else:
            canonical = None
        new_items.append(NewItem(canonical, product.title, product.type))
        links.append(PlannedLink(product.wc_id, new_item=len(new_items) - 1))
    return LinkPlan(new_items, links)


@dataclass(frozen=True)
class Placed:
    """A present product with the item it is linked to."""

    item_id: int
    store_id: int
    wc_id: int
    slug: str
    title: str


@dataclass(frozen=True)
class NearMiss:
    """A suggested pair (CAT-03): `first` is on the lower store id. `rule` says why the slugs are close."""

    first: Placed
    second: Placed
    rule: Literal["edit_distance", "wp_suffix"]


def near_misses(placed: Iterable[Placed]) -> list[NearMiss]:
    """Every candidate pair, ordered by the first product's store and WooCommerce id, then the second's. Products are
    grouped by normalised title first (the titles must be equal), so only same-title slugs are compared."""
    rows = list(placed)
    stores_of: dict[int, set[int]] = defaultdict(set)
    for row in rows:
        stores_of[row.item_id].add(row.store_id)
    by_title: dict[str, list[Placed]] = defaultdict(list)
    for row in rows:
        if len(stores_of[row.item_id]) == 1 and is_linkable_slug(row.slug):
            by_title[normalise_title(row.title)].append(row)
    found: list[NearMiss] = []
    for title, group in by_title.items():
        if not title:
            continue  # an empty normalised title says nothing about being the same product
        group.sort(key=lambda row: (row.store_id, row.wc_id))
        for index, first in enumerate(group):
            for second in group[index + 1 :]:
                if second.store_id == first.store_id or second.item_id == first.item_id:
                    continue
                rule = _close(first.slug, second.slug)
                if rule is not None:
                    found.append(NearMiss(first, second, rule))
    found.sort(key=lambda pair: (pair.first.store_id, pair.first.wc_id, pair.second.store_id, pair.second.wc_id))
    return found


def _close(first: str, second: str) -> Literal["edit_distance", "wp_suffix"] | None:
    if wp_suffix_pair(first, second):
        return "wp_suffix"
    if edit_distance(first, second, NEAR_MISS_DISTANCE) <= NEAR_MISS_DISTANCE:
        return "edit_distance"
    return None
