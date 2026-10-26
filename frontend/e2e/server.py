"""The real backend serving frontend/dist on 127.0.0.1, for the Playwright checks and for looking at the built UI.

It is the app `server.py` runs (create_app with the guard, the CSP and the sign-in routes, uvicorn with the same
settings), with two test-only differences: the install token is a throwaway held in memory (from the environment
variable SHELFSYNC_E2E_TOKEN, made fresh by playwright.config.ts for each run; Credential Manager is never
touched), and nothing else from start-up runs (no database, no runtime.json, no tray). No check is loosened: the
tests get their tickets the way the launcher does, from POST /api/session/ticket with the token and no Origin.

Run from the repository root:  PYTHONPATH=backend uv run python frontend/e2e/server.py
"""

import os
import sys

import uvicorn

from shelfsync.api.app import UI_DIR, create_app
from shelfsync.platform.secrets import MemorySecretStore
from shelfsync.secure.token import INSTALL_TOKEN_NAME, MIN_TOKEN_LENGTH, InstallToken
from shelfsync.server import make_uvicorn_config


def main() -> int:
    port = int(os.environ.get("SHELFSYNC_E2E_PORT", "47699"))
    token = os.environ.pop("SHELFSYNC_E2E_TOKEN", "")
    if len(token) < MIN_TOKEN_LENGTH:
        sys.stderr.write("SHELFSYNC_E2E_TOKEN must hold a test token of at least 32 characters\n")
        return 2
    if not (UI_DIR / "index.html").is_file():
        sys.stderr.write("frontend/dist isn't built: run `npm run build` in frontend/ first\n")
        return 2
    store = MemorySecretStore()
    store.set(INSTALL_TOKEN_NAME, token)
    app = create_app(port, InstallToken(store))
    uvicorn.Server(make_uvicorn_config(app, port)).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
