"""Print the backend's OpenAPI schema as JSON, for openapi-typescript (frontend/scripts/schema.mjs).

The app serves no schema route (docs_url, redoc_url and openapi_url are all None), so the schema is read in code
from `create_app(...).openapi()`. The app is built with a throwaway in-memory token and no UI folder; nothing is
bound, started or written. Run from the repository root:
    PYTHONPATH=backend uv run python frontend/scripts/export_openapi.py
"""

import json
import sys

from shelfsync.api.app import create_app
from shelfsync.platform.secrets import MemorySecretStore
from shelfsync.secure.token import InstallToken


def main() -> int:
    app = create_app(47615, InstallToken(MemorySecretStore()), ui_dir=None)
    sys.stdout.write(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
