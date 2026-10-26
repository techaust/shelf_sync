"""Read-only: look up one product URL slug on both stores (docs/runbooks/research-scripts.md).

Usage (run with OmniSync's Python and -B):
    python -B lookup_slug.py <OmniSync folder> <slug>

It borrows OmniSync's store settings (omnisync.config, imported read-only) and only sends GET requests.
"""

import sys

import requests


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: python -B lookup_slug.py <OmniSync folder> <slug>")
    sys.dont_write_bytecode = True
    sys.path.insert(0, sys.argv[1])
    from omnisync import config  # read-only: borrows the store settings

    slug = sys.argv[2]
    for name in (config.STORE_A, config.STORE_B):
        store = config.STORES[name]
        base = (store.get("api_base") or "").rstrip("/")
        if not base:
            print(name, "no api_base in OmniSync's settings")
            continue
        try:
            r = requests.get(
                f"{base}/products",
                params={"slug": slug, "status": "any", "_fields": "id,name,status,permalink"},
                auth=(store["consumer_key"], store["consumer_secret"]),
                timeout=30,
            )
        except requests.RequestException as exc:
            print(name, "network error:", exc)
            continue
        if r.status_code != 200:
            print(name, f"HTTP {r.status_code}", repr(r.text[:200]))
            continue
        try:
            items = r.json()
        except ValueError:
            print(name, r.status_code, "not JSON:", r.headers.get("content-type"), repr(r.text[:200]))
            continue
        print(name, r.status_code, [(p["id"], p["status"], p["name"], p["permalink"]) for p in items])


if __name__ == "__main__":
    main()
