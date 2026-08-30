#!/usr/bin/env python3
"""The engine-embed input filelist must list every engine source.

Xcode decides whether to re-run the "Embed Fichero Server" phase from the
input filelist. That list is a SNAPSHOT, and on 2026-08-28 it had rotted
badly: 48 real source files were absent — `client_presence.py`, `view.py`,
`renditions.py` among them — so editing any of them left Xcode believing the
phase was up to date, and the app shipped a stale engine while the build went
green. 91 listed files no longer existed at all.

That is the mechanism behind a whole afternoon of "I fixed the backend but
the app still does the old thing". The fix is not `alwaysOutOfDate = 1`
(forbidden for the App Store target, #3991) — it is keeping this list honest,
which is what this check enforces.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
FILELIST = ROOT / "fichero/fichero.xcodeproj/xcshareddata/FicheroEngineEmbedInputs.xcfilelist"
ENGINE_SRC = ROOT / "fichero-server/src/fichero_server"
PREFIX = "$(SRCROOT)/../"


def listed_engine_sources() -> set[str]:
    entries = set()
    for line in FILELIST.read_text().splitlines():
        line = line.strip()
        if line.startswith(PREFIX + "fichero-server/src/"):
            entries.add(line[len(PREFIX):])
    return entries


def real_engine_sources() -> set[str]:
    return {
        str(path.relative_to(ROOT))
        for path in ENGINE_SRC.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.name != ".DS_Store"
    }


def main() -> int:
    if not FILELIST.exists():
        print(f"Engine embed filelist missing: {FILELIST.relative_to(ROOT)}")
        return 1

    listed, real = listed_engine_sources(), real_engine_sources()
    missing, stale = sorted(real - listed), sorted(listed - real)

    if not missing and not stale:
        print(f"✓ Engine embed filelist current — {len(real)} engine sources tracked.")
        return 0

    print("Engine embed filelist is STALE:\n")
    if missing:
        print(f"  {len(missing)} source(s) NOT listed — edits to these will not")
        print("  re-trigger the embed phase, so the app ships a stale engine:")
        for path in missing[:10]:
            print(f"      {path}")
        if len(missing) > 10:
            print(f"      ... {len(missing) - 10} more")
    if stale:
        print(f"\n  {len(stale)} listed file(s) no longer exist:")
        for path in stale[:5]:
            print(f"      {path}")
        if len(stale) > 5:
            print(f"      ... {len(stale) - 5} more")
    print("\nFix: rerun scripts/regen_engine_embed_filelist.py and commit the result.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
