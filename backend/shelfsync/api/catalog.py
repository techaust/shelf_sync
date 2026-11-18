"""The Catalog API (CAT-01, CAT-02, CAT-04, CAT-05): the items, one item with its slots, and the canonical slug edit.

Every route sits behind the guard in `secure/middleware.py` (a session, and Origin plus `X-ShelfSync: 1` for the
PATCH). A wrong shape is the fixed 422 `invalid_request` that never echoes the request.

    GET   /api/catalog        200 {items: [CatalogItem]}: every item in one answer (the screen searches in the browser)
    GET   /api/catalog/{id}   200 CatalogItemDetail; 404 not_found
    GET   /api/catalog/{id}/snapshots   200 SnapshotsResponse (m3.2, SYNC-03: the nights each of the item's store
                                        products can be restored to, local dates, newest first); 404 not_found
    PATCH /api/catalog/{id}   200 CatalogItem; 404 not_found; 409 slug_taken; 422 invalid_request

The PATCH changes the canonical slug only (CAT-04): lowercase `a-z`, `0-9` and `-`, 1 to 200 characters, no leading or
trailing `-`. It changes nothing on any store; S3 names use it from M5. Links and slots on removed stores aren't shown.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Path
from pydantic import BaseModel, ConfigDict, Field

from shelfsync.api.errors import ApiError, ErrorResponse
from shelfsync.catalog.names import CANONICAL_SLUG_PATTERN
from shelfsync.catalog.service import CatalogService, ItemSummary
from shelfsync.db.catalog import LinkRow, SlugTaken

CATALOG_PATH = "/api/catalog"
SLUG_PATTERN = CANONICAL_SLUG_PATTERN
ItemId = Annotated[int, Path(ge=1, le=2**63 - 1)]


class LinkModel(BaseModel):
    store_id: int
    wc_id: int
    slug: str  # the product's URL slug on that store now (it may differ from the canonical slug)
    status: str
    gone: bool  # the last full read no longer returned it


class CatalogItemModel(BaseModel):
    id: int
    canonical_slug: str | None  # null: the item has none (a draft, a trashed slug, or one another item holds)
    title: str
    type: str
    links: list[LinkModel]
    slot_count: int
    on_every_active_store: bool  # a present product on each store whose state is active


class CatalogResponse(BaseModel):
    items: list[CatalogItemModel]


class SlotDownloadModel(BaseModel):
    store_id: int
    wc_download_id: str
    file: str  # the download's file field as the store has it (the `[amazon_s3 object="…"]` shortcode)


class SlotModel(BaseModel):
    id: int
    name: str
    is_main: bool
    downloads: list[SlotDownloadModel]


class CatalogItemDetail(BaseModel):
    id: int
    canonical_slug: str | None
    title: str
    type: str
    created_at: str
    links: list[LinkModel]
    slots: list[SlotModel]


class StoreSnapshotsModel(BaseModel):
    store_id: int
    wc_id: int
    nights: list[str]  # local dates (`YYYY-MM-DD`) it can be restored to, newest first; empty: none yet


class SnapshotsResponse(BaseModel):
    item_id: int
    stores: list[StoreSnapshotsModel]  # one per store product of the item (stores that aren't removed)


class SlugRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    canonical_slug: Annotated[str, Field(min_length=1, max_length=200, pattern=SLUG_PATTERN)]


def _link(link: LinkRow) -> LinkModel:
    return LinkModel(store_id=link.store_id, wc_id=link.wc_id, slug=link.slug, status=link.status, gone=link.gone)


def item_model(summary: ItemSummary) -> CatalogItemModel:
    row = summary.item
    return CatalogItemModel(
        id=row.id,
        canonical_slug=row.canonical_slug,
        title=row.title,
        type=row.type,
        links=[_link(link) for link in summary.links],
        slot_count=summary.slot_count,
        on_every_active_store=summary.on_every_active_store,
    )


def make_catalog_router(service: CatalogService) -> APIRouter:
    router = APIRouter()
    errors: dict[int | str, dict[str, Any]] = {404: {"model": ErrorResponse}}

    @router.get(CATALOG_PATH, response_model=CatalogResponse)
    def list_catalog() -> CatalogResponse:
        return CatalogResponse(items=[item_model(summary) for summary in service.items()])

    @router.get(f"{CATALOG_PATH}/{{item_id}}", response_model=CatalogItemDetail, responses=errors)
    def get_item(item_id: ItemId) -> CatalogItemDetail:
        detail = service.item(item_id)
        if detail is None:
            raise ApiError(404, "not_found")
        row = detail.item
        return CatalogItemDetail(
            id=row.id,
            canonical_slug=row.canonical_slug,
            title=row.title,
            type=row.type,
            created_at=row.created_at,
            links=[_link(link) for link in detail.links],
            slots=[
                SlotModel(
                    id=slot.id,
                    name=slot.name,
                    is_main=slot.is_main,
                    downloads=[
                        SlotDownloadModel(store_id=d.store_id, wc_download_id=d.wc_download_id, file=d.file_url)
                        for d in slot.downloads
                    ],
                )
                for slot in detail.slots
            ],
        )

    @router.get(f"{CATALOG_PATH}/{{item_id}}/snapshots", response_model=SnapshotsResponse, responses=errors)
    def get_snapshots(item_id: ItemId) -> SnapshotsResponse:
        found = service.snapshots(item_id)
        if found is None:
            raise ApiError(404, "not_found")
        return SnapshotsResponse(
            item_id=item_id,
            stores=[
                StoreSnapshotsModel(store_id=entry.store_id, wc_id=entry.wc_id, nights=entry.nights) for entry in found
            ],
        )

    @router.patch(
        f"{CATALOG_PATH}/{{item_id}}",
        response_model=CatalogItemModel,
        responses={**errors, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    def set_slug(item_id: ItemId, body: SlugRequest) -> CatalogItemModel:
        try:
            summary = service.set_slug(item_id, body.canonical_slug)
        except SlugTaken:
            raise ApiError(409, "slug_taken") from None
        if summary is None:
            raise ApiError(404, "not_found")
        return item_model(summary)

    return router
