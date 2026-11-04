"""`python -m testenv.laragon seed`: the sample products on the Laragon test site, and their files on moto (m2.8).

- **Writes go through `SeedClient`**, a testenv-only client: ShelfSync's own `WooClient` stays GET-only. It uses the
  harness's transport (every socket to 127.0.0.1, TLS trusting the site's certificate only), `trust_env=False`, no
  redirects followed (a 3xx stops the run), HTTP Basic with the site's read/write pair in the header only, and
  query-string names that can never carry a key. An error says WooCommerce's error code (a strict pattern) and the
  HTTP status, never a body or a header.
- **Idempotent.** Every product is listed (trash too), and each sample is found by its marker
  (`samples.MARKER_KEY`). A sample that matches is left alone (no request); one that differs gets a `PUT` of only the
  differing fields, keeping the download IDs where name and file match; one of the wrong type, or in or out of the
  trash when it shouldn't be, is force-deleted and created again. A second run writes nothing.
- **`--reset`** force-deletes only a product whose marker names a sample in the list **and** whose slug is that
  sample's (or WordPress's `__trashed` form), re-reading it just before; anything else is kept and reported.
- **The files** go to the moto S3 server first, on every run (moto keeps them in memory only, so a rerun after a restart
  puts them back), through ShelfSync's own S3 client (`testenv.moto_s3.s3_client`). Without moto, `seed` says so and
  still seeds the products.
"""

import base64
import hashlib
import re
import socket
import ssl
import time
from collections.abc import Callable, Sequence
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx

from shelfsync import __version__
from shelfsync.platform.secrets import SecretStore
from testenv.laragon import (
    SPACING_MS,
    HarnessError,
    Site,
    TransportFactory,
    pairs_for,
    read_pair,
    say,
    tls_context,
)
from testenv.samples import (
    ATTRIBUTE,
    DESCRIPTION,
    MARKER_KEY,
    PRICE,
    Sample,
    SampleFile,
    SampleVariation,
    samples_for,
    unique_files,
)

PRODUCTS = "/wp-json/wc/v3/products"
LIST_FIELDS = "id,name,slug,status,type,regular_price,virtual,downloadable,downloads,attributes,meta_data"
VARIATION_FIELDS = "id,status,attributes,regular_price,virtual,downloadable,downloads,meta_data"
MAX_BODY_BYTES = 4 * 1024 * 1024
SPACING_S = SPACING_MS / 1000  # between two requests, as Settings spaces them (read when sent: tests set it to 0)
_CODE = re.compile(r"[a-z0-9_]{1,64}")
_HOST = re.compile(r"[a-z0-9.-]{1,253}")
_SHOWN = re.compile(r"[A-Za-z0-9_./-]{0,64}")


class SeedError(HarnessError):
    """The run stopped; the message says why and never holds a key, a body or a header."""


def _shown(value: object) -> str:
    """A value from the site, safe to print: quoted if it is short and plain, else a placeholder."""
    text = str(value)
    return repr(text) if _SHOWN.fullmatch(text) else "(an unusual value)"


class SeedClient:
    """Requests to one test site with its read/write pair. One client, one transport, one site."""

    def __init__(
        self,
        site: Site,
        key: str,
        secret: str,
        transport: httpx.BaseTransport,
        *,
        sleep: Callable[[float], None] | None = None,
        spacing_s: float | None = None,
    ) -> None:
        self._base = site.url
        self._sleep = sleep
        self._spacing = spacing_s
        self._sent = 0
        self._client = httpx.Client(
            transport=transport,
            auth=httpx.BasicAuth(key, secret),
            headers={
                "User-Agent": f"ShelfSync-TestStack/{__version__}",
                "Accept": "application/json",
                "Accept-Encoding": "identity",
            },
            follow_redirects=False,
            trust_env=False,
            timeout=httpx.Timeout(30.0, connect=10.0),
        )

    def __enter__(self) -> SeedClient:
        return self

    def __exit__(self, *_: object) -> None:
        self._client.close()

    def call(
        self, method: str, path: str, params: dict[str, str] | None = None, body: dict[str, Any] | None = None
    ) -> tuple[Any, httpx.Headers]:
        params = params or {}
        if any(name.lower().startswith("consumer_") or "key" in name.lower() for name in params):
            raise ValueError("credentials never go in a query string")
        if self._sent:
            (self._sleep or time.sleep)(SPACING_S if self._spacing is None else self._spacing)
        self._sent += 1
        try:
            with self._client.stream(method, self._base + path, params=params, json=body) as response:
                status = response.status_code
                if 300 <= status < 400:
                    host = httpx.URL(response.headers.get("location", "")).host.lower()
                    where = f" ({host})" if _HOST.fullmatch(host) else ""
                    raise SeedError(
                        f"The site sent {method} {path} to another address{where} (HTTP {status}); seed never "
                        "follows that. Nothing more was written."
                    )
                data = b""
                for chunk in response.iter_raw():
                    data += chunk
                    if len(data) > MAX_BODY_BYTES:
                        raise SeedError(f"The answer to {method} {path} was too long.")
                parsed = _json(data)
                if not 200 <= status < 300:
                    code = parsed.get("code") if isinstance(parsed, dict) else None
                    named = f"{code}, " if isinstance(code, str) and _CODE.fullmatch(code) else ""
                    raise SeedError(f"WooCommerce refused {method} {path} ({named}HTTP {status}).")
                return parsed, response.headers
        except httpx.TimeoutException:
            raise SeedError(f"The site took too long to answer {method} {path}.") from None
        except httpx.TransportError as error:
            if _is_tls(error):
                raise SeedError("The site's security certificate wasn't accepted. Nothing was written.") from None
            raise SeedError("Couldn't reach the site. Is Laragon running?") from None


def _json(data: bytes) -> Any:
    try:
        return httpx.Response(200, content=data).json() if data else None
    except ValueError:
        return None


def _is_tls(error: BaseException) -> bool:
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        if isinstance(current, ssl.SSLError):
            return True
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return False


# ---------- reading the site ----------


def marker_of(entity: Any) -> str | None:
    meta = entity.get("meta_data") if isinstance(entity, dict) else None
    for entry in meta if isinstance(meta, list) else []:
        if isinstance(entry, dict) and entry.get("key") == MARKER_KEY and isinstance(entry.get("value"), str):
            value: str = entry["value"]
            return value
    return None


def list_products(client: SeedClient) -> list[dict[str, Any]]:
    """Every product, trash included: `status=any` leaves trash out, `include_status=trash` lists it (04-A V1)."""
    found: dict[int, dict[str, Any]] = {}
    for selector in ({"status": "any"}, {"include_status": "trash"}):
        page = 1
        while True:
            params = {**selector, "per_page": "100", "page": str(page), "_fields": LIST_FIELDS}
            data, headers = client.call("GET", PRODUCTS, params)
            if not isinstance(data, list):
                raise SeedError("The product list wasn't what seed expected.")
            for product in data:
                if isinstance(product, dict) and isinstance(product.get("id"), int):
                    found[product["id"]] = product
            pages = headers.get("x-wp-totalpages", "1")
            if not (pages.isascii() and pages.isdigit()) or page >= int(pages):
                break
            page += 1
    return list(found.values())


def _index(products: list[dict[str, Any]], samples: Sequence[Sample]) -> dict[str, dict[str, Any]]:
    """Each sample's product, by marker. Refuses two products with one marker, and a product that isn't the sample
    but holds a sample's slug (seed would get `<slug>-2` and change nothing of the other product)."""
    ids = {sample.id for sample in samples}
    marked: dict[str, list[dict[str, Any]]] = {}
    for product in products:
        marker = marker_of(product)
        if marker in ids:
            marked.setdefault(marker, []).append(product)
    for marker, found in marked.items():
        if len(found) > 1:
            numbers = ", ".join(f"#{product['id']}" for product in found)
            raise SeedError(f"Products {numbers} are all marked as sample {marker}. Delete the extra ones by hand.")
    for sample in samples:
        for product in products:
            if product.get("slug") == sample.slug and marker_of(product) != sample.id:
                raise SeedError(
                    f"Product #{product['id']} isn't the sample {sample.id} but uses its slug {sample.slug!r}. "
                    "seed changes nothing: rename or delete that product first."
                )
    return {marker: found[0] for marker, found in marked.items()}


# ---------- what a sample should look like ----------


def _downloads(files: tuple[SampleFile, ...], current: Any) -> list[dict[str, str]]:
    """The downloads to send, keeping the ID of each current one whose name and file match (WooCommerce's download
    IDs are what `object_ref.wc_download_id` holds)."""
    ids: dict[tuple[object, object], str] = {}
    for entry in current if isinstance(current, list) else []:
        if isinstance(entry, dict) and isinstance(entry.get("id"), str) and entry["id"]:
            ids[(entry.get("name"), entry.get("file"))] = entry["id"]
    out = []
    for file in files:
        download = {"name": file.name, "file": file.shortcode}
        known = ids.get((file.name, file.shortcode))
        if known is not None:
            download["id"] = known
        out.append(download)
    return out


def _same_downloads(files: tuple[SampleFile, ...], current: Any) -> bool:
    pairs = (
        [(entry.get("name"), entry.get("file")) for entry in current if isinstance(entry, dict)]
        if isinstance(current, list)
        else None
    )
    return pairs == [(file.name, file.shortcode) for file in files]


def _same_price(current: Any) -> bool:
    try:
        return Decimal(str(current)) == Decimal(PRICE)
    except InvalidOperation:
        return False


def _attributes(sample: Sample) -> list[dict[str, Any]]:
    options = [variation.option for variation in sample.variations]
    return [{"name": ATTRIBUTE, "variation": True, "visible": True, "options": options}]


def _same_attributes(sample: Sample, current: Any) -> bool:
    for entry in current if isinstance(current, list) else []:
        if isinstance(entry, dict) and entry.get("name") == ATTRIBUTE:
            options = [variation.option for variation in sample.variations]
            return entry.get("options") == options and entry.get("variation") is True
    return False


def new_product(sample: Sample) -> dict[str, Any]:
    body: dict[str, Any] = {
        "name": sample.name,
        "slug": sample.slug,
        "type": sample.type,
        "status": "publish" if sample.status == "trash" else sample.status,  # trashed after it's made
        "description": DESCRIPTION,
        "meta_data": [{"key": MARKER_KEY, "value": sample.id}],
    }
    if sample.type == "variable":
        body["attributes"] = _attributes(sample)
    else:
        body |= {
            "regular_price": PRICE,
            "virtual": True,
            "downloadable": sample.downloadable,
            "downloads": _downloads(sample.files, None),
        }
    return body


def changes(sample: Sample, current: dict[str, Any]) -> dict[str, Any]:
    """The fields that differ from the sample (the description is set at creation only)."""
    out: dict[str, Any] = {}
    if current.get("name") != sample.name:
        out["name"] = sample.name
    if current.get("slug") not in sample.accepted_slugs():
        out["slug"] = sample.slug
    if sample.status != "trash" and current.get("status") != sample.status:
        out["status"] = sample.status
    if sample.type == "variable":
        if not _same_attributes(sample, current.get("attributes")):
            out["attributes"] = _attributes(sample)
        return out
    if not _same_price(current.get("regular_price")):
        out["regular_price"] = PRICE
    if current.get("virtual") is not True:
        out["virtual"] = True
    if current.get("downloadable") is not sample.downloadable:
        out["downloadable"] = sample.downloadable
    if not _same_downloads(sample.files, current.get("downloads")):
        out["downloads"] = _downloads(sample.files, current.get("downloads"))
    return out


def new_variation(variation: SampleVariation) -> dict[str, Any]:
    return {
        "status": "publish",
        "regular_price": PRICE,
        "virtual": True,
        "downloadable": True,
        "attributes": [{"name": ATTRIBUTE, "option": variation.option}],
        "downloads": _downloads(variation.files, None),
        "meta_data": [{"key": MARKER_KEY, "value": variation.id}],
    }


def variation_changes(variation: SampleVariation, current: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if current.get("status") != "publish":
        out["status"] = "publish"
    if not _same_price(current.get("regular_price")):
        out["regular_price"] = PRICE
    if current.get("virtual") is not True:
        out["virtual"] = True
    if current.get("downloadable") is not True:
        out["downloadable"] = True
    options = [
        (entry.get("name"), entry.get("option")) for entry in current.get("attributes") or [] if isinstance(entry, dict)
    ]
    if options != [(ATTRIBUTE, variation.option)]:
        out["attributes"] = [{"name": ATTRIBUTE, "option": variation.option}]
    if not _same_downloads(variation.files, current.get("downloads")):
        out["downloads"] = _downloads(variation.files, current.get("downloads"))
    return out


# ---------- writing ----------


def _seed_variations(client: SeedClient, sample: Sample, product_id: int, existing: list[dict[str, Any]]) -> bool:
    path = f"{PRODUCTS}/{product_id}/variations"
    marked: dict[str, list[dict[str, Any]]] = {}
    for current in existing:
        marked.setdefault(marker_of(current) or "", []).append(current)
    wrote = False
    for variation in sample.variations:
        found = marked.pop(variation.id, [])
        if len(found) > 1:
            raise SeedError(f"Sample {sample.id} has {len(found)} variations marked {variation.id}; delete the extras.")
        if not found:
            client.call("POST", path, body=new_variation(variation))
            wrote = True
            continue
        update = variation_changes(variation, found[0])
        if update:
            client.call("PUT", f"{path}/{found[0]['id']}", body=update)
            wrote = True
    for leftovers in marked.values():
        for current in leftovers:
            say(f"  Left variation #{current.get('id')} of {sample.id} as it is: it isn't one of the sample's.")
    return wrote


def _variations(client: SeedClient, product_id: int) -> list[dict[str, Any]]:
    params = {"per_page": "100", "_fields": VARIATION_FIELDS}
    data, _ = client.call("GET", f"{PRODUCTS}/{product_id}/variations", params)
    if not isinstance(data, list):
        raise SeedError("The variation list wasn't what seed expected.")
    return [entry for entry in data if isinstance(entry, dict)]


def _create(client: SeedClient, sample: Sample) -> int:
    created, _ = client.call("POST", PRODUCTS, body=new_product(sample))
    if not isinstance(created, dict) or not isinstance(created.get("id"), int):
        raise SeedError(f"WooCommerce's answer to creating {sample.id} had no product ID.")
    product_id: int = created["id"]
    if sample.variations:
        _seed_variations(client, sample, product_id, [])
    if sample.status == "trash":
        client.call("DELETE", f"{PRODUCTS}/{product_id}")  # no `force`: to the trash
    slug = created.get("slug")
    if slug not in sample.accepted_slugs():
        say(f"  Note: WooCommerce stored the slug {_shown(slug)} for {sample.id}, not {sample.slug!r}.")
    return product_id


def seed_one(client: SeedClient, sample: Sample, current: dict[str, Any] | None) -> tuple[str, int]:
    """Bring one sample to its shape. Returns what was done and the product ID."""
    if current is not None:
        product_id: int = current["id"]
        in_trash = current.get("status") == "trash"
        update = changes(sample, current)
        # The wrong type, in or out of the trash when it shouldn't be, or a trashed one that differs: made again
        # (editing a trashed product, or taking one out of the trash, through REST isn't confirmed).
        if current.get("type") != sample.type or in_trash != (sample.status == "trash") or (in_trash and update):
            client.call("DELETE", f"{PRODUCTS}/{product_id}", {"force": "true"})
            return "Recreated", _create(client, sample)
        wrote = False
        if update:
            client.call("PUT", f"{PRODUCTS}/{product_id}", body=update)
            wrote = True
        if sample.variations and _seed_variations(client, sample, product_id, _variations(client, product_id)):
            wrote = True
        return ("Updated" if wrote else "Unchanged"), product_id
    return "Created", _create(client, sample)


def _read_write_client(
    site: Site, cert: Path, secrets: SecretStore, transport_factory: TransportFactory, **kw: Any
) -> SeedClient:
    pair = read_pair(secrets, pairs_for(site)[1])
    if pair is None:
        raise SeedError(f"No read/write key pair is saved for {site.host}. Run the keys command first.")
    context = tls_context(cert)
    return SeedClient(site, pair[0], pair[1], transport_factory(context, site.host), **kw)


def run_seed(
    site: Site,
    cert: Path,
    secrets: SecretStore,
    moto: str,
    bucket: str,
    region: str,
    transport_factory: TransportFactory,
    *,
    samples: Sequence[Sample] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> int:
    chosen = tuple(samples) if samples is not None else samples_for(site.host)
    with _read_write_client(site, cert, secrets, transport_factory, sleep=sleep) as client:
        upload_files(moto, bucket, region, chosen)
        index = _index(list_products(client), chosen)
        done: dict[str, int] = {}
        for sample in chosen:
            word, product_id = seed_one(client, sample, index.get(sample.id))
            done[word] = done.get(word, 0) + 1
            trashed = " (in the trash)" if sample.status == "trash" else ""
            say(f"{word} {sample.id} (#{product_id}){trashed}.")
    counts = ", ".join(
        f"{done.get(word, 0)} {word.lower()}" for word in ("Created", "Updated", "Unchanged", "Recreated")
    )
    say(f"{len(chosen)} samples on {site.host}: {counts}.")
    return 0


def run_reset(
    site: Site,
    cert: Path,
    secrets: SecretStore,
    transport_factory: TransportFactory,
    *,
    samples: Sequence[Sample] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> int:
    by_id = {sample.id: sample for sample in (samples if samples is not None else samples_for(site.host))}

    def is_sample(product: Any) -> Sample | None:
        sample = by_id.get(marker_of(product) or "")
        return sample if sample is not None and product.get("slug") in sample.accepted_slugs() else None

    deleted = 0
    with _read_write_client(site, cert, secrets, transport_factory, sleep=sleep) as client:
        for product in list_products(client):
            marker = marker_of(product)
            if marker is None:
                continue
            sample = is_sample(product)
            if sample is None:
                say(f"Kept #{product['id']}: marked {_shown(marker)}, but it isn't one of the samples as listed.")
                continue
            again, _ = client.call("GET", f"{PRODUCTS}/{product['id']}", {"_fields": "id,slug,meta_data"})
            if is_sample(again) is not sample:
                say(f"Kept #{product['id']}: it changed while reset ran.")
                continue
            client.call("DELETE", f"{PRODUCTS}/{product['id']}", {"force": "true"})
            deleted += 1
            say(f"Deleted {sample.id} (#{product['id']}).")
        left = [product for product in list_products(client) if is_sample(product) is not None]
    say(f"Deleted {deleted} sample products from {site.host}.")
    if left:
        say(f"Still there: {', '.join('#' + str(product['id']) for product in left)}.")
        return 1
    return 0


# ---------- the files on moto ----------


def upload_files(moto: str, bucket: str, region: str, samples: Sequence[Sample]) -> int:
    """Put every sample's file in the moto bucket (every run: moto keeps nothing after a restart), through ShelfSync's
    own S3 client; each `put_object` carries `ContentMD5` and is checked with `head_object`. Returns how many were
    uploaded; 0 (and a message) when the S3 server isn't running or has no such bucket."""
    from botocore.exceptions import BotoCoreError, ClientError

    from testenv.moto_s3 import s3_client

    not_there = (
        f"The S3 server isn't running at {moto} (or has no bucket {bucket}), so the sample files weren't "
        "uploaded; the products are still seeded. Start it (runbook section 1) and run seed again."
    )
    url = httpx.URL(moto)  # already checked: http on 127.0.0.1 or localhost, with a port
    try:  # a quick look first: botocore would retry a refused connection for seconds
        with socket.create_connection((url.host, url.port or 80), timeout=0.5):
            pass
    except OSError:
        say(not_there)
        return 0
    files = unique_files(tuple(samples))
    client = s3_client(moto, region)
    try:
        try:
            client.head_bucket(Bucket=bucket)
        except BotoCoreError, ClientError:
            say(not_there)
            return 0
        for file in files:
            body = file.zip_bytes()
            digest = base64.b64encode(hashlib.md5(body).digest()).decode("ascii")  # Content-MD5, not security
            client.put_object(Bucket=bucket, Key=file.key, Body=body, ContentType="application/zip", ContentMD5=digest)
            head = client.head_object(Bucket=bucket, Key=file.key)
            if head.get("ContentLength") != len(body):
                raise SeedError(f"The S3 server kept {file.key} with the wrong size.")
    finally:
        client.close()
    say(f"Uploaded {len(files)} sample files to {bucket} at {moto}.")
    return len(files)
