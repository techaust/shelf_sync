# ADR 0001: Python + FastAPI + SQLite backend, React + TypeScript UI

- **Status:** Accepted (owner, with plan Draft 3, 2026-10-25)
- **Date:** 2026-10-25

## Context
ShelfSync runs on one Windows PC for one user. It reads ZIPs (locally and from S3 by range reads), talks to WooCommerce and S3, and needs a friendly UI with live progress. It must be easy to maintain and cost nothing.

## Decision
- **Backend:** Python 3.12, FastAPI on uvicorn, an in-process job worker, SQLite in WAL mode, boto3 and httpx.
- **ZIPs:** Python's `zipfile` over a small seekable range-reader for files in S3 (our own class over boto3 range GETs); filename encodings handled (UTF-8 flag, else cp437).
- **UI:** React + TypeScript built with Vite into static files the backend serves; server-sent events for live progress.
- No separate services (no Redis, no Docker at run time).

## Alternatives considered
| Option | Why not |
|---|---|
| Electron or Tauri desktop app | A second runtime and an unsigned native binary to ship; a browser tab on localhost does the same job |
| Node.js backend | Python's `zipfile`, boto3 and the OmniSync experience fit the ZIP and S3 work better |
| PyInstaller single exe | Unsigned, often flagged by antivirus ([ADR 0002](0002-embedded-python-nsis.md)) |
| WebSockets instead of SSE | Progress only flows one way; SSE is simpler and reconnects by itself |

## Consequences
- One process, one database file, one log folder.
- The UI shares its component approach and tokens with the TecHaust admin ([ADR 0006](0006-techaust-product-brand.md)).
