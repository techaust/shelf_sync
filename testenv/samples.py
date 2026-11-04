"""The sample products of the Laragon test site (m2.8; run file m2.8 §3 has the table and where each shape comes from).

Shaped like the real catalogue (01, 01-A): **no SKU** on any product or variation (the real stores have none), each
product's URL slug is its file key's stem (CAT-02 links twins by slug; CAT-04 names objects `<slug>-<version>.zip`),
and every download is the `[amazon_s3 object="<key>"]` shortcode (04 §5, SET-02; all 2400 real links are). Keys use
the layout seen in OmniSync's log, `productrepo/<slug>-<version>.zip` (01-B), plus one old unversioned key and one at
the bucket's root.

Each sample (and each variation) carries a marker, the meta entry `shelfsync_test_sample=<sample id>`, so `seed`
finds its own products again and `seed --reset` deletes only them (marker **and** slug must both match).

The list is data: `samples_for(site)` returns it, so later milestones can give a second site its twins and near-miss
samples. Names, slugs and headers are made up; no vendor code.
"""

import io
import zipfile
from dataclasses import dataclass
from typing import Literal

MARKER_KEY = "shelfsync_test_sample"
SHORTCODE = '[amazon_s3 object="{key}"]'
PRICE = "19.00"
ATTRIBUTE = "Licence"
DESCRIPTION = "A made-up sample for ShelfSync's test stack. No vendor code: its file holds only a made-up header."
STATUSES = ("publish", "draft", "pending", "private", "trash")
_ZIP_DATE = (1980, 1, 1, 0, 0, 0)


@dataclass(frozen=True)
class SampleFile:
    """One download: the S3 key, and the made-up header its tiny ZIP holds."""

    key: str
    kind: Literal["theme", "plugin"]
    title: str
    version: str

    @property
    def name(self) -> str:
        """The download's name on the store: the file name."""
        return self.key.rsplit("/", 1)[-1]

    @property
    def stem(self) -> str:
        """The file name without `.zip` and without `-<version>`: the slug part of `<slug>-<version>.zip`."""
        stem = self.name.removesuffix(".zip")
        return stem.removesuffix(f"-{self.version}")

    @property
    def shortcode(self) -> str:
        return SHORTCODE.format(key=self.key)

    def zip_bytes(self) -> bytes:
        """A tiny ZIP with only the header file, byte-for-byte the same on every run (fixed date and permissions), so
        a re-upload has the same MD5."""
        folder = self.stem
        if self.kind == "theme":
            path = f"{folder}/style.css"
            text = (
                f"/*\nTheme Name: {self.title}\nVersion: {self.version}\nAuthor: ShelfSync test stack\n"
                "Description: A made-up sample. No vendor code.\n*/\n"
            )
        else:
            path = f"{folder}/{folder}.php"
            text = (
                f"<?php\n/**\n * Plugin Name: {self.title}\n * Version: {self.version}\n"
                " * Author: ShelfSync test stack\n * Description: A made-up sample. No vendor code.\n */\n"
            )
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            info = zipfile.ZipInfo(path, date_time=_ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, text.encode("utf-8"))
        return buffer.getvalue()


@dataclass(frozen=True)
class SampleVariation:
    id: str  # its marker value
    option: str  # its value of the product's attribute
    files: tuple[SampleFile, ...]


@dataclass(frozen=True)
class Sample:
    id: str  # its marker value
    slug: str
    name: str
    status: str = "publish"
    files: tuple[SampleFile, ...] = ()
    variations: tuple[SampleVariation, ...] = ()

    @property
    def type(self) -> str:
        return "variable" if self.variations else "simple"

    @property
    def downloadable(self) -> bool:
        return bool(self.files)

    def all_files(self) -> tuple[SampleFile, ...]:
        return self.files + tuple(file for variation in self.variations for file in variation.files)

    def accepted_slugs(self) -> frozenset[str]:
        """The slugs this sample may have on the site: its own, WordPress's form for a trashed post
        (`<slug>__trashed`), and, for a draft or pending one, an empty slug (WordPress may not give those a slug;
        not confirmed for WooCommerce's REST API, so `seed` reports what the site stored)."""
        slugs = {self.slug, f"{self.slug}__trashed"}
        if self.status in ("draft", "pending"):
            slugs.add("")
        return frozenset(slugs)


def _theme(key: str, title: str, version: str) -> SampleFile:
    return SampleFile(key, "theme", title, version)


def _plugin(key: str, title: str, version: str) -> SampleFile:
    return SampleFile(key, "plugin", title, version)


_MOSAIC = _plugin("productrepo/mosaic-gallery-4.0.0.zip", "Mosaic Gallery", "4.0.0")

SAMPLES: tuple[Sample, ...] = (
    Sample(
        "aurora",
        "aurora",
        "Aurora (ShelfSync test)",
        files=(_theme("productrepo/aurora-2.4.1.zip", "Aurora", "2.4.1"),),
    ),
    Sample(
        "pixel-forms",
        "pixel-forms",
        "Pixel Forms (ShelfSync test)",
        files=(_plugin("productrepo/pixel-forms-1.8.0.zip", "Pixel Forms", "1.8.0"),),
    ),
    Sample(
        "northwind",
        "northwind",
        "Northwind (ShelfSync test)",
        files=(
            _theme("productrepo/northwind-5.0.2.zip", "Northwind", "5.0.2"),
            _plugin("productrepo/northwind-core-5.0.2.zip", "Northwind Core", "5.0.2"),
        ),
    ),
    Sample(
        "lumen-suite",
        "lumen-suite",
        "Lumen Suite (ShelfSync test)",
        variations=(
            SampleVariation(
                "lumen-suite/single-site",
                "Single site",
                (_plugin("productrepo/lumen-suite-3.1.0.zip", "Lumen Suite", "3.1.0"),),
            ),
            SampleVariation(
                "lumen-suite/unlimited",
                "Unlimited",
                (_plugin("productrepo/lumen-suite-pro-3.1.0.zip", "Lumen Suite Pro", "3.1.0"),),
            ),
        ),
    ),
    Sample("setup-service", "setup-service", "Setup Service (ShelfSync test)"),
    Sample(
        "harbor",
        "harbor",
        "Harbor (ShelfSync test)",
        status="draft",
        files=(_theme("productrepo/harbor-1.0.0.zip", "Harbor", "1.0.0"),),
    ),
    Sample(
        "quiet-cache",
        "quiet-cache",
        "Quiet Cache (ShelfSync test)",
        status="private",
        files=(_plugin("productrepo/quiet-cache-0.9.4.zip", "Quiet Cache", "0.9.4"),),
    ),
    Sample(
        "tidewater-seo",
        "tidewater-seo",
        "Tidewater SEO (ShelfSync test)",
        status="pending",
        files=(_plugin("productrepo/tidewater-seo-7.3.2.zip", "Tidewater SEO", "7.3.2"),),
    ),
    Sample(
        "old-slider",
        "old-slider",
        "Old Slider (ShelfSync test)",
        status="trash",
        files=(_plugin("productrepo/old-slider-6.2.0.zip", "Old Slider", "6.2.0"),),
    ),
    Sample("mosaic-gallery", "mosaic-gallery", "Mosaic Gallery (ShelfSync test)", files=(_MOSAIC,)),
    Sample(
        "mosaic-gallery-bundle", "mosaic-gallery-bundle", "Mosaic Gallery Bundle (ShelfSync test)", files=(_MOSAIC,)
    ),
    Sample(
        "emberline",
        "emberline",
        "Emberline (ShelfSync test)",
        files=(_theme("productrepo/emberline.zip", "Emberline", "1.0"),),
    ),
    Sample("lantern", "lantern", "Lantern (ShelfSync test)", files=(_plugin("lantern.zip", "Lantern", "2.0"),)),
)


def samples_for(host: str) -> tuple[Sample, ...]:
    """The samples a site gets. Every site gets the same list today; a second site's twins come later (M3)."""
    del host
    return SAMPLES


def unique_files(samples: tuple[Sample, ...]) -> tuple[SampleFile, ...]:
    """Each S3 object once (two samples share one key)."""
    seen: dict[str, SampleFile] = {}
    for sample in samples:
        for file in sample.all_files():
            seen.setdefault(file.key, file)
    return tuple(seen.values())
