"""Step 0: start our engine, list the libraries it knows, create THE test library, stop.

Refuses if the library already exists: it is never overwritten. A re-run names a fresh one
(`ACCEPTANCE_LIBRARY=...b.fichero`) beside the earlier run's, which is left alone.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _engine import LIBRARY, LIBRARY_ROOT, client, engine, save  # noqa: E402


def main() -> None:
    if LIBRARY.exists():
        raise SystemExit(f"refusing: {LIBRARY} exists; it is never overwritten")
    with engine():
        with client(library=False) as c:
            known = c.request("GET", "/api/registry")
            print("libraries this engine knows before:", known)
        LIBRARY_ROOT.mkdir(exist_ok=True)
        with client() as c:
            created = c.request("POST", "/api/library", json={"path": str(LIBRARY)})
            print("created:", created)
            save("library.json", {"known_before": known, "created": created})


if __name__ == "__main__":
    main()
