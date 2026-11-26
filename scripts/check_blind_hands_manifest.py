#!/usr/bin/env python3
"""The committed blind-hands manifest must load, and must not name a private hand (#6966).

Loads scripts/blind_hands/manifest.json through `manifest.load`. When FICHERO_BLIND_HANDS_PRIVATE_MANIFEST names the
second manifest (kept outside the repository), also refuses a committed file that names one of its hands or pages.
Without that variable only the committed file is checked, and the output says so.

Usage:
    scripts/check_blind_hands_manifest.py
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRIVATE_ENV = "FICHERO_BLIND_HANDS_PRIVATE_MANIFEST"


def _manifest_module():
    path = ROOT / "scripts" / "blind_hands" / "manifest.py"
    spec = importlib.util.spec_from_file_location("blind_hands_manifest", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main(committed_path: Path | None = None) -> int:
    m = _manifest_module()
    try:
        committed = m.load(committed_path or m.COMMITTED)
        private_path = os.environ.get(PRIVATE_ENV)
        if private_path:
            m.check_committed(committed, m.load(Path(private_path), private=True))
    except (m.ManifestError, OSError, ValueError) as exc:
        print(f"FAIL: {exc}")
        return 1
    print("ok: committed manifest loads" + ("; no private hand named" if private_path else f"; {PRIVATE_ENV} unset, private check not run"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
