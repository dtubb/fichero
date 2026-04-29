"""
Route the kreuzberg extraction cache to Fichero's app-data folder so it
stays out of the working directory of whichever process invokes it.

Without this shim, kreuzberg writes its msgpack/meta cache to `.kreuzberg/`
relative to cwd — which means running the backend or tests from the repo
root leaves `.kreuzberg/` polluting `git status` (#589).

Import this module for its side effect **before** importing or calling
kreuzberg. `document_loader` and `pdf_loader` both import it at the top
so any callsite that triggers an extraction has the env var set.
"""

import os
from pathlib import Path

# Mirrors the `MODELS_BASE` path in `fichero.local_models` — app-data
# root owned by Fichero, invisible to git, stable across relaunches.
_CACHE_ROOT = (
    Path.home() / "Library" / "Application Support" / "com.fichero.fichero"
)
_KREUZBERG_CACHE = _CACHE_ROOT / "kreuzberg"

# Only set if the operator hasn't already overridden via env — respects
# explicit user config (e.g. tests pointing to a tmpdir).
if not os.environ.get("KREUZBERG_CACHE_DIR"):
    _KREUZBERG_CACHE.mkdir(parents=True, exist_ok=True)
    os.environ["KREUZBERG_CACHE_DIR"] = str(_KREUZBERG_CACHE)
