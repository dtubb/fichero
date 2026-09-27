#!/usr/bin/env python3
"""Regenerate the engine-embed input filelist from the real source tree.

Non-engine entries (scripts, pyproject) are preserved verbatim; only the
`fichero-server/src/` block is rebuilt. See check_engine_embed_filelist.py
for why this matters. The source set comes from that check's own
`real_engine_sources()`, so regenerating and checking cannot disagree.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_engine_embed_filelist import FILELIST, PREFIX, ROOT, real_engine_sources  # noqa: E402

keep = [
    line for line in FILELIST.read_text().splitlines()
    if line.strip() and not line.strip().startswith(PREFIX + "fichero-server/src/")
]
sources = sorted(real_engine_sources())
FILELIST.write_text("\n".join(keep + [PREFIX + s for s in sources]) + "\n")
print(f"Regenerated {FILELIST.relative_to(ROOT)}: {len(keep) + len(sources)} entries")
