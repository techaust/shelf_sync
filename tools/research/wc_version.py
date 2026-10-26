"""Read-only: print each store's WooCommerce and WordPress versions (docs/01-audit-appendix/A, 04-A V2).

Usage (run with OmniSync's Python and -B, see docs/runbooks/research-scripts.md):
    python -B wc_version.py <OmniSync folder>

It borrows OmniSync's store settings (omnisync.config, imported read-only), sends one GET per store to
/system_status, and prints only the version numbers (the rest of that report is never printed).
"""

import sys
from datetime import datetime, timezone

import requests


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -B wc_version.py <OmniSync folder>")
    sys.dont_write_bytecode = True
    sys.path.insert(0, sys.argv[1])
    from omnisync import config  # read-only: borrows the store settings

    print("UTC time:", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    for name in (config.STORE_A, config.STORE_B):
        store = config.STORES[name]
        base = (store.get("api_base") or "").rstrip("/")
        if not base:
            print(name, "no api_base in OmniSync's settings")
            continue
        try:
            r = requests.get(f"{base}/system_status", params={"_fields": "environment"},
                             auth=(store["consumer_key"], store["consumer_secret"]), timeout=60)
        except requests.RequestException as exc:
            print(name, "network error:", exc)
            continue
        if r.status_code != 200:
            print(name, f"HTTP {r.status_code}", repr(r.text[:200]))
            continue
        try:
            env = (r.json() or {}).get("environment") or {}
        except ValueError:
            print(name, "not JSON:", r.headers.get("content-type"), repr(r.text[:200]))
            continue
        print(name, "WooCommerce", env.get("version"), "| WordPress", env.get("wp_version"))


if __name__ == "__main__":
    main()
