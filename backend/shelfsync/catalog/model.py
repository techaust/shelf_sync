"""What one product looks like once the catalog reader has checked it (`apply/catalog_read.py`). Only the fields the
reader asks a store for, each within the limits below (the same limits as migration 0003's CHECKs, so a checked
product always fits its table)."""

from dataclasses import dataclass

# The limits a store's answer must keep (Lead (proposed), m3.1; L1 measures the real data). A longer value fails the
# whole read with `bad_response` and nothing is saved.
SLUG_MAX = 200  # WordPress's `post_name` is varchar(200)
TITLE_MAX = 1000  # after `html.unescape`
WORD_MAX = 40  # a type or a status (`simple`, `publish`, ...)
DOWNLOADS_MAX = 50  # downloads on one product (the real stores have 1 or 2)
DOWNLOAD_ID_MAX = 64  # WooCommerce's download ids are an md5 or a uuid (32 or 36 characters)
DOWNLOAD_NAME_MAX = 200
DOWNLOAD_FILE_MAX = 2048
META_KEY_MAX = 255  # WordPress's `meta_key` is varchar(255)
META_VALUE_MAX = 200
META_KEPT_MAX = 50  # `latest_version*` entries kept on one product
META_PREFIX = "latest_version"


@dataclass(frozen=True)
class Download:
    """One of a product's downloads: its WooCommerce download id, its name (the button's words) and its file (on the
    real stores an `[amazon_s3 object="<key>"]` shortcode)."""

    id: str
    name: str
    file: str


@dataclass(frozen=True)
class Product:
    """One product as a full read returned it. `title` has had `html.unescape` applied; `meta` holds only the meta
    entries whose key starts with `latest_version`, in the order the store gave them."""

    wc_id: int
    slug: str
    title: str
    type: str
    status: str
    modified_gmt: str | None
    downloads: tuple[Download, ...]
    meta: tuple[tuple[str, str], ...]
