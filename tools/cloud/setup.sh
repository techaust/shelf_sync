#!/bin/bash
# Setup script for ShelfSync's cloud environment (docs/runbooks/cloud-sessions.md). The owner loads this file into the
# environment's "Setup script" box once; it runs as root on the Ubuntu 24.04 VM before Claude Code starts, and the
# result is cached for about 7 days. It installs exactly what CI uses (.github/workflows/checks.yml), because the image
# has neither: Python 3.14.8 (the GitHub build actions/setup-python installs; uv has no 3.14.8 download for Linux),
# Node 24.19.0 and uv 0.12.19. Each download is checked against a pinned SHA-256 before anything is unpacked; a
# mismatch stops the script, and the session doesn't start (owner, 2026-10-29; docs/11).
# tools/cloud/session-start.sh puts these first on PATH for every command in the session.
set -euo pipefail

PY_URL="https://github.com/actions/python-versions/releases/download/3.14.8-36806082737/python-3.14.8-linux-24.04-x64.tar.gz"
PY_SHA="fa74abc70a55c10f6631967784878704eef81bbde9b8ec27469534f6ba997cb3" # computed 2026-10-29 (the release publishes none)
PY_DIR="/opt/hostedtoolcache/Python/3.14.8/x64" # the same folder setup-python uses on GitHub's runners
NODE_URL="https://nodejs.org/dist/v24.19.0/node-v24.19.0-linux-x64.tar.xz"
NODE_SHA="14b342e71204f811bde6153be8e04b62aef63c236fef92b55f9c83154b409647" # nodejs.org SHASUMS256.txt
NODE_DIR="/opt/node-v24.19.0"
UV_URL="https://files.pythonhosted.org/packages/76/71/b47cec536d8ee7b09017c1d9db211dfc2e7ce5c87d0482918d8b3411ec48/uv-0.12.19-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl"
UV_SHA="a63d18a0aa38ee9f21a5406afbbaeb41303bcd954be9d6b7c1b95ac275e53958" # PyPI's digest for this wheel
UV_DIR="/opt/uv-0.12.19/bin"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# fetch <url> <sha256> <file>: download, then refuse the file unless its hash matches.
fetch() {
  curl -fsSL --retry 3 -o "$3" "$1"
  echo "$2  $3" | sha256sum --check --status || { echo "[setup] SHA-256 mismatch for $1" >&2; return 1; }
}

fetch "$PY_URL" "$PY_SHA" "$TMP/python.tgz" &
py=$!
fetch "$NODE_URL" "$NODE_SHA" "$TMP/node.tar.xz" &
node=$!
fetch "$UV_URL" "$UV_SHA" "$TMP/uv.whl" &
uv=$!
wait "$py"
wait "$node"
wait "$uv"

# Python: unpacked as setup-python does, without its pip upgrade (nothing unpinned is fetched).
rm -rf "$PY_DIR" && mkdir -p "$PY_DIR"
tar -xzf "$TMP/python.tgz" -C "$PY_DIR"
rm -f "$PY_DIR/setup.sh"
ln -sf python3.14 "$PY_DIR/bin/python"

rm -rf "$NODE_DIR" && mkdir -p "$NODE_DIR"
tar -xJf "$TMP/node.tar.xz" -C "$NODE_DIR" --strip-components=1

# uv: the wheel is a zip; take its one binary.
mkdir -p "$UV_DIR"
"$PY_DIR/bin/python3.14" -I -c '
import sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as z:
    name = next(n for n in z.namelist() if n.endswith(".data/scripts/uv"))
    open(sys.argv[2], "wb").write(z.read(name))
' "$TMP/uv.whl" "$UV_DIR/uv"
chmod 755 "$UV_DIR/uv"

"$PY_DIR/bin/python3.14" --version
"$NODE_DIR/bin/node" --version
"$UV_DIR/uv" --version
