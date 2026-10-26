"""Read-only: downloadable variations and the forms download links take, on both stores (04-A V30).

Usage (run with OmniSync's Python and -B, see docs/runbooks/research-scripts.md):
    python -B downloads_check.py <OmniSync folder>

It borrows OmniSync's store settings (omnisync.config, imported read-only) and only sends GET requests.
"""

import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone

import requests

PER_PAGE = 100
SPACING_S = 0.15  # same default as ShelfSync's APL-12
RETRY_STATUSES = {429, 500, 502, 503, 504, 520, 521, 522, 523, 524, 525, 526, 527}


def get(session: requests.Session, url: str, params: dict) -> requests.Response:
    """GET with 3 tries and backoff on rate limits, server and Cloudflare errors."""
    for attempt in range(3):
        try:
            r = session.get(url, params=params, timeout=90)
        except requests.RequestException as exc:
            if attempt == 2:
                raise SystemExit(f"Network error on {url}: {exc}") from exc
        else:
            if r.status_code not in RETRY_STATUSES or attempt == 2:
                return r
        time.sleep(2 ** (attempt + 1))
    raise AssertionError("unreachable")


def pages(name: str, session: requests.Session, url: str, params: dict) -> list[dict]:
    out: list[dict] = []
    page, total_pages = 1, 1
    while page <= total_pages:
        r = get(session, url, {**params, "per_page": PER_PAGE, "page": page})
        if r.status_code != 200:
            raise SystemExit(f"{name}: HTTP {r.status_code} on {url} page {page}: {r.text[:200]!r}")
        try:
            out += r.json()
        except ValueError:
            raise SystemExit(f"{name}: not JSON ({r.headers.get('content-type')}): {r.text[:200]!r}") from None
        total_pages = int(r.headers.get("X-WP-TotalPages", total_pages))
        page += 1
        time.sleep(SPACING_S)
    return out


def form(file_field: str) -> str:
    """How a download's file field refers to its file, without printing the value."""
    f = (file_field or "").strip()
    if not f:
        return "empty"
    if f.startswith("[amazon_s3"):
        return "shortcode [amazon_s3 ...]"
    if f.startswith("["):
        return "other shortcode"
    if re.match(r"https?://[^/]*amazonaws\.com/", f):
        return "direct S3 URL"
    if re.match(r"https?://", f):
        return "other URL"
    return "other"


def check(name: str, store: dict) -> None:
    base = (store.get("api_base") or "").rstrip("/")
    if not base:
        raise SystemExit(f"{name}: no api_base in OmniSync's settings")
    session = requests.Session()
    session.auth = (store["consumer_key"], store["consumer_secret"])

    fields = {"_fields": "id,type,downloadable,downloads"}
    products = pages(name, session, f"{base}/products", {"status": "any", **fields})
    # status=any leaves out trash (04-A V1), so trashed products are read separately
    trashed = pages(name, session, f"{base}/products", {"status": "trash", **fields})
    products += trashed
    forms = Counter(form(d.get("file", "")) for p in products for d in (p.get("downloads") or []))
    print(f"\n[{name}] products (status=any, plus {len(trashed)} in trash): {len(products)}")
    print("  by type:", dict(Counter(p.get("type") for p in products)))
    print("  download link forms on products:", dict(forms))

    variable = [p["id"] for p in products if p.get("type") == "variable"]
    with_dl, dl_forms, total_var = [], Counter(), 0
    for pid in variable:
        variations = pages(name, session, f"{base}/products/{pid}/variations",
                           {"_fields": "id,downloadable,downloads"})
        total_var += len(variations)
        files = [d for v in variations if v.get("downloadable") for d in (v.get("downloads") or [])]
        if files:
            with_dl.append(pid)
            dl_forms.update(form(d.get("file", "")) for d in files)
    print(f"  variable products: {len(variable)}, their variations: {total_var}")
    print(f"  variable products with downloadable variations that have files: {len(with_dl)} {with_dl[:10]}")
    if dl_forms:
        print("  download link forms on variations:", dict(dl_forms))


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -B downloads_check.py <OmniSync folder>")
    sys.dont_write_bytecode = True
    sys.path.insert(0, sys.argv[1])
    from omnisync import config  # read-only: borrows the store settings

    print("UTC time:", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    for name in (config.STORE_A, config.STORE_B):
        check(name, config.STORES[name])


if __name__ == "__main__":
    main()
