"""CAT-02, CAT-03, CAT-04, CAT-05: the pure catalog rules (`catalog/names.py`, `linking.py`, `slots.py`), without a
database or a network. Property tests (hypothesis) for the edit distance, WordPress's `-N` rule and the normalised
title."""

import html

from hypothesis import given
from hypothesis import strategies as st

from shelfsync.catalog.linking import KnownLink, NearMiss, Placed, near_misses, plan_links
from shelfsync.catalog.model import Download
from shelfsync.catalog.names import (
    edit_distance,
    is_canonical_slug,
    is_linkable_slug,
    normalise_title,
    wp_suffix_pair,
)
from shelfsync.catalog.slots import SlotRef, main_download, plan_slots
from tests.catalog_support import NEAR_MISS_PAIRS, product

SLUGS = st.text(alphabet="abc-12", max_size=12)


def reference_distance(first: str, second: str) -> int:
    """Levenshtein by the textbook recursion's full table: the reference the fast one is checked against."""
    table = [[0] * (len(second) + 1) for _ in range(len(first) + 1)]
    for i in range(len(first) + 1):
        for j in range(len(second) + 1):
            if i == 0 or j == 0:
                table[i][j] = i + j
            else:
                table[i][j] = min(
                    table[i - 1][j] + 1, table[i][j - 1] + 1, table[i - 1][j - 1] + (first[i - 1] != second[j - 1])
                )
    return table[-1][-1]


# ---- the edit distance ---------------------------------------------------------------------------------------------


@given(SLUGS, SLUGS)
def test_the_edit_distance_equals_the_reference_and_is_symmetric(first: str, second: str) -> None:
    expected = reference_distance(first, second)
    assert edit_distance(first, second) == expected == edit_distance(second, first)


@given(SLUGS, SLUGS, st.integers(min_value=0, max_value=4))
def test_the_limited_edit_distance_is_exact_up_to_the_limit_and_limit_plus_one_beyond(
    first: str, second: str, limit: int
) -> None:
    assert edit_distance(first, second, limit) == min(reference_distance(first, second), limit + 1)


@given(SLUGS, SLUGS, SLUGS)
def test_the_edit_distance_keeps_the_triangle_inequality(first: str, second: str, third: str) -> None:
    assert edit_distance(first, third) <= edit_distance(first, second) + edit_distance(second, third)


@given(SLUGS)
def test_the_edit_distance_is_zero_only_to_itself(slug: str) -> None:
    assert edit_distance(slug, slug) == 0
    assert edit_distance(slug, slug + "x") == 1


# ---- WordPress's -N suffix -----------------------------------------------------------------------------------------


@given(st.text(alphabet="abc-", min_size=1, max_size=10), st.integers(min_value=2, max_value=10**6))
def test_a_slug_and_its_wordpress_suffix_form_are_a_pair_both_ways(slug: str, number: int) -> None:
    assert wp_suffix_pair(slug, f"{slug}-{number}")
    assert wp_suffix_pair(f"{slug}-{number}", slug)


@given(st.text(alphabet="abc-", min_size=1, max_size=10))
def test_a_suffix_of_one_or_with_a_leading_zero_is_not_wordpresss(slug: str) -> None:
    for suffix in ("-1", "-0", "-02", "-", "-x", "2"):
        assert not wp_suffix_pair(slug, slug + suffix)
    assert not wp_suffix_pair(slug, slug)
    assert not wp_suffix_pair("", "-2")


# ---- the normalised title ------------------------------------------------------------------------------------------


@given(st.text(max_size=40))
def test_normalising_a_title_is_idempotent_and_leaves_no_punctuation_or_double_space(title: str) -> None:
    once = normalise_title(title)
    assert normalise_title(once) == once
    assert "  " not in once and once == once.strip()


@given(st.text(alphabet=st.characters(categories=("L", "N", "Zs")), max_size=30))
def test_an_entity_encoded_title_normalises_like_the_plain_one(title: str) -> None:
    assert normalise_title(html.escape(title)) == normalise_title(title)


def test_titles_normalise_by_unescape_nfkc_casefold_and_punctuation() -> None:
    assert normalise_title("Form&nbsp;Mailer &amp; Add-on") == normalise_title("form mailer   add on")
    assert normalise_title("ＦＵＬＬ　WIDTH") == "full width"  # NFKC
    assert normalise_title("STRASSE") == normalise_title("Straße")  # casefold
    assert normalise_title("Theme – Pro!") == "theme pro"


def test_edition_words_are_kept() -> None:
    """m3.0 correction 7: "X Pro" and "X" are different products."""
    assert normalise_title("Lense Theme Pro") != normalise_title("Lense Theme")


# ---- linking -------------------------------------------------------------------------------------------------------


def test_a_product_joins_the_item_with_the_same_slug_on_another_store_and_none_on_this_one() -> None:
    known = [KnownLink(1, 1, 1294, "jupiterx", True)]
    plan = plan_links(2, [product(1373, "jupiterx")], known, {"jupiterx"})
    assert plan.new_items == [] and [(link.wc_id, link.item_id) for link in plan.links] == [(1373, 1)]


def test_an_item_already_on_this_store_is_not_joined_and_the_new_item_gets_no_taken_slug() -> None:
    known = [KnownLink(1, 1, 10, "alpha", True), KnownLink(1, 2, 20, "other", True)]
    plan = plan_links(2, [product(21, "alpha")], known, {"alpha"})
    assert [item.canonical_slug for item in plan.new_items] == [None]
    assert plan.links[0].new_item == 0


def test_only_a_present_product_on_this_store_stops_a_join() -> None:
    """Analyst finding 3: a gone link on this store doesn't block; a present one does."""
    known = [KnownLink(1, 1, 10, "foo", False), KnownLink(1, 2, 20, "foo", True)]
    assert plan_links(1, [product(11, "foo")], known, {"foo"}).links[0].item_id == 1
    blocked = [KnownLink(1, 1, 10, "foo", True), KnownLink(1, 2, 20, "foo", True)]
    assert plan_links(1, [product(11, "foo")], blocked, {"foo"}).links[0].item_id is None


@given(st.text(max_size=12))
def test_only_a_slug_in_the_canonical_pattern_becomes_a_canonical_slug(slug: str) -> None:
    """Analyst finding 5: the same rule as the slug edit and 0003's CHECK."""
    plan = plan_links(1, [product(1, slug)], [], set())
    canonical = plan.new_items[0].canonical_slug
    assert canonical == (slug if is_canonical_slug(slug) and is_linkable_slug(slug) else None)
    assert is_canonical_slug("a-b-1") and not is_canonical_slug("%e2%9c%93") and not is_canonical_slug("A")


def test_a_gone_product_on_another_store_is_not_joined() -> None:
    plan = plan_links(2, [product(5, "alpha")], [KnownLink(1, 1, 1, "alpha", False)], {"alpha"})
    assert plan.links[0].item_id is None and plan.new_items[0].canonical_slug is None


def test_already_linked_products_are_left_alone_whatever_their_slug_now() -> None:
    known = [KnownLink(1, 1, 1, "alpha", True), KnownLink(2, 2, 7, "renamed", True)]
    plan = plan_links(2, [product(7, "alpha")], known, {"alpha", "renamed"})
    assert plan.links == [] and plan.new_items == []


def test_trashed_and_empty_slugs_are_never_linked_and_get_no_canonical_slug() -> None:
    known = [KnownLink(1, 1, 1, "alpha__trashed", True), KnownLink(2, 1, 2, "", True)]
    plan = plan_links(2, [product(3, "alpha__trashed"), product(4, "")], known, set())
    assert [item.canonical_slug for item in plan.new_items] == [None, None]
    assert all(link.item_id is None for link in plan.links)
    assert not is_linkable_slug("") and not is_linkable_slug("x__trashed") and is_linkable_slug("x")


def test_when_two_items_qualify_the_lowest_id_is_joined_whatever_the_order() -> None:
    known = [KnownLink(9, 3, 30, "alpha", True), KnownLink(4, 1, 10, "alpha", True)]
    plan = plan_links(2, [product(5, "alpha")], list(reversed(known)), {"alpha"})
    assert plan.links[0].item_id == 4


def test_two_products_of_one_store_with_one_slug_get_two_items_and_one_slug() -> None:
    plan = plan_links(1, [product(2, "alpha"), product(1, "alpha")], [], set())
    assert [(item.canonical_slug, link.wc_id) for item, link in zip(plan.new_items, plan.links, strict=True)] == [
        ("alpha", 1),
        (None, 2),
    ]


# ---- near misses ---------------------------------------------------------------------------------------------------


def _placed(pairs: list[tuple[str, str, str]]) -> list[Placed]:
    rows: list[Placed] = []
    for index, (first, second, title) in enumerate(pairs):
        rows.append(Placed(100 + index, 1, 1000 + index, first, title))
        rows.append(Placed(200 + index, 2, 2000 + index, second, title))
    return rows


def test_the_three_pairs_of_01a_are_found_and_none_is_linked() -> None:
    """CAT-03: the 3 pairs (slugs from 01-A section 2, made-up titles) are suggestions; `near_misses` only returns
    them, and `plan_links` on the second store makes no link between them."""
    found = near_misses(_placed(NEAR_MISS_PAIRS))
    assert [(pair.first.slug, pair.second.slug, pair.rule) for pair in found] == [
        (NEAR_MISS_PAIRS[0][0], NEAR_MISS_PAIRS[0][1], "edit_distance"),
        (NEAR_MISS_PAIRS[1][0], NEAR_MISS_PAIRS[1][1], "edit_distance"),
        (NEAR_MISS_PAIRS[2][0], NEAR_MISS_PAIRS[2][1], "wp_suffix"),
    ]
    known = [KnownLink(100 + i, 1, 1000 + i, first, True) for i, (first, _, _) in enumerate(NEAR_MISS_PAIRS)]
    plan = plan_links(2, [product(2000 + i, second) for i, (_, second, _) in enumerate(NEAR_MISS_PAIRS)], known, set())
    assert all(link.item_id is None for link in plan.links)  # each got an item of its own: never linked silently


def test_near_identical_slugs_with_different_titles_are_not_candidates() -> None:
    rows = [Placed(1, 1, 1, "lense-theme", "Lense Theme"), Placed(2, 2, 2, "lense-theme-2", "Lense Theme Pro")]
    assert near_misses(rows) == []


def test_an_entity_encoded_title_still_matches_its_twin() -> None:
    rows = [Placed(1, 1, 1, "a-b-addon", "A &amp; B Add-on"), Placed(2, 2, 2, "a-b-add-on", "A & B Add-on")]
    assert [pair.rule for pair in near_misses(rows)] == ["edit_distance"]


def test_products_already_linked_on_two_stores_and_pairs_on_one_store_are_not_candidates() -> None:
    linked = [Placed(1, 1, 1, "alpha", "Alpha"), Placed(1, 2, 2, "alpha", "Alpha")]
    lonely = [Placed(2, 2, 3, "alpha-2", "Alpha")]  # near `alpha`, but `alpha`'s item is on both stores
    same_store = [Placed(3, 1, 4, "beta", "Beta"), Placed(4, 1, 5, "beta-2", "Beta")]
    assert near_misses(linked + lonely + same_store) == []


def test_slugs_more_than_two_edits_apart_are_not_candidates_and_trashed_ones_never() -> None:
    far = [Placed(1, 1, 1, "alpha-theme", "Alpha"), Placed(2, 2, 2, "alpha-thing", "Alpha")]
    trashed = [Placed(3, 1, 3, "beta__trashed", "Beta"), Placed(4, 2, 4, "beta__trashe", "Beta")]
    assert near_misses(far + trashed) == []


def test_an_empty_normalised_title_matches_nothing() -> None:
    assert near_misses([Placed(1, 1, 1, "a", "!!"), Placed(2, 2, 2, "b", "??")]) == []


def test_a_near_miss_names_the_lower_store_first() -> None:
    [pair] = near_misses([Placed(9, 2, 9, "a-b", "T"), Placed(8, 1, 8, "a-bc", "T")])
    assert isinstance(pair, NearMiss) and (pair.first.store_id, pair.second.store_id) == (1, 2)


# ---- slots ---------------------------------------------------------------------------------------------------------

MAIN = Download("m", "Download", "f-main")
DOCS = Download("d", "Documentation", "f-docs")


def test_the_main_download_is_the_one_named_like_the_stores_button() -> None:
    assert main_download((DOCS, MAIN), "Download") == (1, False)
    assert main_download((DOCS,), "Download") == (0, True)  # exactly one download: that one (Lead (proposed))
    assert main_download((DOCS, Download("x", "Extra", "f")), "Download") == (None, False)
    assert main_download((), "Download") == (None, False)


def test_new_slots_are_made_once_and_existing_ones_are_reused_by_kind_and_name() -> None:
    plan = plan_slots((MAIN, DOCS), "Download", [])
    assert [(slot.name, slot.is_main) for slot in plan.new_slots] == [("Download", True), ("Documentation", False)]
    again = plan_slots((DOCS, MAIN), "Download", [SlotRef(5, "Download", True), SlotRef(6, "Documentation", False)])
    assert again.new_slots == []
    assert [(a.download.id, a.slot_id) for a in again.assignments] == [("d", 6), ("m", 5)]


def test_a_store_with_another_button_name_fills_the_same_main_slot() -> None:
    plan = plan_slots((Download("p", "Get it", "f"),), "Get it", [SlotRef(5, "Download", True)])
    assert plan.new_slots == [] and plan.assignments[0].slot_id == 5 and not plan.main_by_single


def test_a_repeated_download_name_on_one_product_is_counted_not_slotted() -> None:
    plan = plan_slots(
        (MAIN, Download("m2", "Download", "g"), DOCS, Download("d2", "Documentation", "h")), "Download", []
    )
    assert plan.unslotted == 2 and [a.download.id for a in plan.assignments] == ["m", "d"]


def test_with_several_downloads_and_none_named_like_the_button_there_is_no_main_slot() -> None:
    plan = plan_slots((DOCS, Download("x", "Extra", "f")), "Download", [])
    assert all(not slot.is_main for slot in plan.new_slots) and len(plan.new_slots) == 2
