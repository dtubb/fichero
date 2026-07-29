"""
Route the kreuzberg extraction cache to ~/Library/Caches/com.fichero.fichero/kreuzberg/
so it stays out of the working directory of whichever process invokes it.

Without this shim, kreuzberg writes its msgpack/meta cache to `.kreuzberg/`
relative to cwd — which means running the backend or tests from the repo
root leaves `.kreuzberg/` polluting `git status` (#589).

Import this module for its side effect **before** importing or calling
kreuzberg. `document_loader` and `pdf_loader` both import it at the top
so any callsite that triggers an extraction has the env var set.
"""

import os
import shutil
from pathlib import Path

# ~/Library/Caches per Apple HIG: this is regenerable derived data, not user
# content. OS may prune it under disk pressure; Time Machine skips it.
_KREUZBERG_CACHE = (
    Path.home() / "Library" / "Caches" / "com.fichero.fichero" / "kreuzberg"
)

# One-time migration from the previous Application Support location.
# Safe to remove this block after 0.0.3 ships.
_LEGACY_CACHE = (
    Path.home()
    / "Library"
    / "Application Support"
    / "com.fichero.fichero"
    / "kreuzberg"
)
if _LEGACY_CACHE.exists() and not _KREUZBERG_CACHE.exists():
    _KREUZBERG_CACHE.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(_LEGACY_CACHE), str(_KREUZBERG_CACHE))

# Only set if the operator hasn't already overridden via env — respects
# explicit user config (e.g. tests pointing to a tmpdir).
if not os.environ.get("KREUZBERG_CACHE_DIR"):
    _KREUZBERG_CACHE.mkdir(parents=True, exist_ok=True)
    os.environ["KREUZBERG_CACHE_DIR"] = str(_KREUZBERG_CACHE)
