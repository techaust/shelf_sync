"""Read-only: compare downloadable products across the two stores (docs/01-audit-appendix/A).

Usage (run with OmniSync's Python and -B, see docs/runbooks/research-scripts.md):
    python -B slug_overlap.py <OmniSync folder>

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
EDITION_WORDS = {"pro", "premium", "plus", "ultimate", "extended", "addon", "lite", "free", "core", "child"}


def get(session: requests.Session, url: str, params: dict) -> requests.Response:
    """GET with 3 tries and backoff on rate limits, server and Cloudflare errors."""
    for attempt in range(3):
        try:
            r = session.get(url, params=params, timeout=90)
        except requests.RequestException as exc:
            if attempt == 2:
                raise SystemExit(f"Network error on {url}: {exc}") from exc
        else:
            if r.status_code not in RETRY_STATUSES:
                return r
            if attempt == 2:
                return r
        time.sleep(2 ** (attempt + 1))
    raise AssertionError("unreachable")


def fetch(name: str, store: dict) -> list[dict]:
    base = (store.get("api_base") or "").rstrip("/")
    if not base:
        raise SystemExit(f"{name}: no api_base in OmniSync's settings")
    session = requests.Session()
    session.auth = (store["consumer_key"], store["consumer_secret"])
    out: list[dict] = []
    page, pages, total = 1, 1, None
    while page <= pages:
        r = get(
            session,
            f"{base}/products",
            {"downloadable": "true", "status": "any", "per_page": PER_PAGE, "page": page,
             "_fields": "id,slug,name,sku,status,downloads"},
        )
        if r.status_code != 200:
            raise SystemExit(f"{name}: HTTP {r.status_code} on page {page}: {r.text[:200]!r}")
        try:
            batch = r.json()
        except ValueError:
            raise SystemExit(f"{name}: not JSON ({r.headers.get('content-type')}): {r.text[:200]!r}") from None
        pages = int(r.headers.get("X-WP-TotalPages", pages))
        if "X-WP-Total" in r.headers:
            total = int(r.headers["X-WP-Total"])
        out += batch
        page += 1
        time.sleep(SPACING_S)
    if total is None:
        print(f"WARNING {name}: no X-WP-Total header, so the count can't be checked")
    elif len(out) != total:
        print(f"WARNING {name}: fetched {len(out)} but X-WP-Total says {total}")
    return out


def norm_title(title: str) -> str:
    # "add-on" / "add on" become one edition word, so "add" and "on" elsewhere are kept
    words = re.findall(r"[a-z0-9]+", re.sub(r"\badd[\s-]+on\b", "addon", title.lower()))
    return " ".join(w for w in words if w not in EDITION_WORDS)


def edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def report_store(name: str, products: list[dict]) -> Counter:
    slugs = Counter(p["slug"] for p in products)
    print(f"\n[{name}] products: {len(products)}")
    print("  by status:", dict(Counter(p.get("status") for p in products)))
    print("  with SKU:", sum(1 for p in products if (p.get("sku") or "").strip()))
    multi = [p["id"] for p in products if len(p.get("downloads") or []) > 1]
    print("  with more than one download:", len(multi), multi[:10])
    # A store that ignored downloadable=true would return products with no download (04-A V27)
    none = [p["id"] for p in products if not p.get("downloads")]
    print("  with no download:", len(none), none[:10])
    print("  slugs repeated within this store:", [s for s, n in slugs.items() if n > 1][:10])
    return slugs


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -B slug_overlap.py <OmniSync folder>")
    sys.dont_write_bytecode = True
    sys.path.insert(0, sys.argv[1])
    from omnisync import config  # read-only: borrows the store settings

    print("UTC time:", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    a_name, b_name = config.STORE_A, config.STORE_B
    a, b = fetch(a_name, config.STORES[a_name]), fetch(b_name, config.STORES[b_name])
    sa, sb = report_store(a_name, a), report_store(b_name, b)

    both = set(sa) & set(sb)
    only_a, only_b = sorted(set(sa) - set(sb)), sorted(set(sb) - set(sa))
    print(f"\nslugs on both stores: {len(both)}")
    print(f"only {a_name}: {len(only_a)} {only_a[:10]}")
    print(f"only {b_name}: {len(only_b)} {only_b[:10]}")
    ta = {p["slug"]: p["name"] for p in a}
    tb = {p["slug"]: p["name"] for p in b}
    print("same slug, different title:", sum(1 for s in both if ta[s].strip().lower() != tb[s].strip().lower()))

    print("\nnear-miss candidates (edit distance <= 2 or a -N suffix, same normalised title):")
    for sa_slug in only_a:
        for sb_slug in only_b:
            if norm_title(ta[sa_slug]) != norm_title(tb[sb_slug]):  # cheap check first
                continue
            if re.sub(r"-\d+$", "", sa_slug) == re.sub(r"-\d+$", "", sb_slug) or edit_distance(sa_slug, sb_slug) <= 2:
                print(f"  {sa_slug}  <->  {sb_slug}")


if __name__ == "__main__":
    main()
