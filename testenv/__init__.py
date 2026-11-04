"""ShelfSync's local test stack (04 section 10, 07 section 5): developer tooling, never shipped with the app.

`python -m testenv.<command>` imports this package first, so `backend/` (ShelfSync's import root; the app runs from
source and isn't installed into the environment) is put on the path here, for the commands that use ShelfSync's own
clients (`testenv.laragon`).
"""

import sys
from pathlib import Path

_BACKEND = str(Path(__file__).resolve().parent.parent / "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
