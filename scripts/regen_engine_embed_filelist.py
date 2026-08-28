#!/usr/bin/env python3
"""Regenerate the engine-embed input filelist from the real source tree.

Non-engine entries (scripts, pyproject) are preserved verbatim; only the
`fichero-server/src/` block is rebuilt. See check_engine_embed_filelist.py
for why this matters.
"""
from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
FILELIST = ROOT / "fichero/fichero.xcodeproj/xcshareddata/FicheroEngineEmbedInputs.xcfilelist"
PREFIX = "$(SRCROOT)/../"

keep = [
    line for line in FILELIST.read_text().splitlines()
    if line.strip() and not line.strip().startswith(PREFIX + "fichero-server/src/")
]
sources = sorted(
    str(path.relative_to(ROOT))
    for path in (ROOT / "fichero-server/src/fichero_server").rglob("*")
    if path.is_file() and "__pycache__" not in path.parts and path.name != ".DS_Store"
)
FILELIST.write_text("\n".join(keep + [PREFIX + s for s in sources]) + "\n")
print(f"Regenerated {FILELIST.relative_to(ROOT)}: {len(keep) + len(sources)} entries")
