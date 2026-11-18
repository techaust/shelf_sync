"""SYNC-01, SYNC-04: change detection for m3.3 (`catalog/changes.py`) and the watermark (`catalog/watermark.py`), pure
functions, with property tests."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from hypothesis import given
from hypothesis import strategies as st

from shelfsync.catalog.changes import CHANGE_FIELDS, ProductState, compare, counts, detect
from shelfsync.catalog.model import Download
from shelfsync.catalog.watermark import modified_after, next_watermark
from tests.catalog_support import product

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)

words = st.sampled_from(["publish", "draft", "private", "trash"])
downloads = st.lists(
    st.builds(Download, st.sampled_from(["a", "b"]), st.sampled_from(["Download", "Pro"]), st.sampled_from(["x", "y"])),
    max_size=2,
).map(tuple)
states = st.builds(
    ProductState,
    st.just(7),
    st.sampled_from(["alpha", "beta"]),
    words,
    st.sampled_from(["simple", "variable"]),
    downloads,
    st.booleans(),  # downloadable (F8)
    st.sampled_from([(), (("latest_version", "1.0"),), (("latest_version", "1.1"),)]),  # version (F11)
)


def test_the_change_fields_include_the_flag_and_the_version() -> None:
    assert CHANGE_FIELDS == ("downloads", "slug", "status", "type", "downloadable", "version")
    change = compare(1, state(downloadable=True), state(downloadable=False), "incremental")
    assert change is not None and (change.kind, change.fields) == ("changed", ("downloadable",))
    one, two = (("latest_version", "1"),), (("latest_version", "2"),)
    edited = compare(1, state(version=one), state(version=two), "snapshot")
    assert edited is not None and edited.fields == ("version",)


def test_the_watermark_steps_back_by_the_reads_duration_and_ignores_unicode_digits() -> None:
    """F3, F7."""
    dated = [replace(product(1), modified_gmt="2026-11-12T00:03:00")]
    assert next_watermark(None, dated, NOW, 180) == "2026-11-12T00:00:00"
    assert next_watermark("2026-11-12T00:01:00", dated, NOW, 180) == "2026-11-12T00:01:00"  # never back
    assert next_watermark(None, [replace(product(1), modified_gmt="٢٠٢٦-11-12T00:03:00")], NOW) is None
    with pytest.raises(ValueError):
        modified_after("２０２６-11-12T00:03:00")


def state(**changes: object) -> ProductState:
    base = {"wc_id": 7, "slug": "alpha", "status": "publish", "type": "simple", "downloads": ()}
    return ProductState(**{**base, **changes})  # type: ignore[arg-type]


@given(states)
def test_a_product_compared_with_itself_has_no_change(same: ProductState) -> None:
    assert compare(1, same, same, "snapshot") is None


@given(states, states)
def test_the_fields_named_are_exactly_the_ones_that_differ(before: ProductState, after: ProductState) -> None:
    change = compare(1, before, after, "incremental")
    differ = tuple(name for name in CHANGE_FIELDS if getattr(before, name) != getattr(after, name))
    assert (change.fields if change is not None else ()) == differ
    if change is not None:
        trashed = after.status == "trash" and before.status != "trash"
        assert change.kind == ("trashed" if trashed else "changed")


def test_trash_restored_is_a_change_not_a_trashing() -> None:
    change = compare(1, state(status="trash"), state(status="publish"), "snapshot")
    assert change is not None and (change.kind, change.fields) == ("changed", ("status",))


def test_detect_reports_changes_and_deletions_in_id_order_and_never_a_new_product() -> None:
    before = {3: state(wc_id=3), 1: state(wc_id=1), 2: state(wc_id=2)}
    after = {1: state(wc_id=1, slug="moved"), 2: state(wc_id=2), 9: state(wc_id=9)}
    found = detect(4, before, after, "snapshot", deleted=[3])
    assert [(change.wc_id, change.kind) for change in found] == [(1, "changed"), (3, "deleted")]
    assert found[1].after is None and found[1].fields == () and found[1].store_id == 4
    assert counts(found) == {"changed": 1, "trashed": 0, "deleted": 1}


def test_detect_refuses_a_deletion_that_isnt_one() -> None:
    with pytest.raises(ValueError):
        detect(1, {1: state(wc_id=1)}, {1: state(wc_id=1)}, "snapshot", deleted=[1])
    with pytest.raises(ValueError):
        compare(1, state(wc_id=1), state(wc_id=2), "snapshot")


# ---- the watermark -------------------------------------------------------------------------------------------------


def test_modified_after_is_two_minutes_before_the_watermark_across_midnight() -> None:
    assert modified_after("2026-11-18T00:01:00") == "2026-11-17T23:59:00"
    assert modified_after("2026-01-01T00:00:30") == "2025-12-31T23:58:30"


@given(st.datetimes(min_value=datetime(2000, 1, 1), max_value=datetime(2100, 1, 1)))
def test_modified_after_always_keeps_the_store_dates_form(moment: datetime) -> None:
    text = moment.strftime("%Y-%m-%dT%H:%M:%S")
    earlier = modified_after(text)
    assert len(earlier) == 19 and earlier < text


def test_next_watermark_takes_the_largest_store_date_and_never_the_clock() -> None:
    assert next_watermark(None, [], NOW) is None
    assert next_watermark("2026-11-10T00:00:00", [], NOW) == "2026-11-10T00:00:00"
    assert next_watermark("2026-11-01T00:00:00", [product(1)], NOW) == "2026-11-01T00:00:00"  # 2026-10-25 is older
    dated = [
        replace(product(1), modified_gmt="2026-11-12T00:00:00"),
        replace(product(2), modified_gmt="2026-11-19T11:59:59"),  # within a day ahead of the PC's clock
        replace(product(3), modified_gmt="2026-11-19T12:00:01"),  # past it: never the watermark
        replace(product(4), modified_gmt=None),
    ]
    assert next_watermark("2026-11-15T00:00:00", dated, NOW) == "2026-11-19T11:59:59"
    assert next_watermark("2026-11-20T00:00:00", dated[:1], NOW) == "2026-11-20T00:00:00"  # never back
