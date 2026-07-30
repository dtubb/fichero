"""DRAFT (not wired in) — `_load_lance_extension(conn)` for db/__init__.py.

Landing target: add this as a method on `Database` and call it at the end of
`Database._connect()` (and inside `_reconnect_after_invalidated()`), so every
DuckDB connection this process opens has the `lance` extension loaded from the
BUNDLED signed binary — never over the network (sandbox blocks INSTALL).

DO NOT wire this in until GATE-0.md reads GO. Kept out of the package so it is
not imported and cannot break the live `lancedb`-client path.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import duckdb  # already a top-level import in db/__init__.py

logger = logging.getLogger(__name__)

# Env override lets Dev/CI point at a locally built extension; the embedded
# Release app sets this (or the bundle-relative default below) to the signed
# osx_arm64 binary shipped in Resources.
LANCE_EXT_PATH_ENV = "FICHERO_LANCE_EXTENSION_PATH"

# Allow an unsigned/locally-built extension ONLY when explicitly opted in
# (Dev). MUST stay false/unset in the sandboxed MAS build — see GATE-0 §B.
LANCE_EXT_ALLOW_UNSIGNED_ENV = "FICHERO_LANCE_EXTENSION_ALLOW_UNSIGNED"


def _bundled_lance_extension_path() -> Path | None:
    """Resolve the bundled extension path.

    Order: explicit env override → bundle-relative Resources location. Returns
    None if neither exists so the caller can fail loudly rather than silently
    fall back to the network (which the sandbox would deny anyway).
    """
    override = os.getenv(LANCE_EXT_PATH_ENV, "").strip()
    if override:
        p = Path(override)
        return p if p.is_file() else None

    # Bundle-relative default. The embedded engine ships the extension next to
    # the local models / Resources; adjust to the real briefcase layout once
    # GATE-0 G1 fixes the bundle location.
    try:
        from fichero.local_models import MODELS_BASE

        candidate = MODELS_BASE.parent / "duckdb_extensions" / "lance.duckdb_extension"
        if candidate.is_file():
            return candidate
    except Exception:  # noqa: BLE001 — resolution is best-effort
        pass
    return None


def _load_lance_extension(conn: duckdb.DuckDBPyConnection) -> None:
    """Load the bundled `lance` DuckDB extension onto ``conn`` (offline).

    Idempotent: DuckDB no-ops a second LOAD of an already-loaded extension.
    Raises RuntimeError with an actionable message if the bundled binary is
    missing or refuses to load — we NEVER silently fall back to `INSTALL`
    (network), which the app sandbox blocks (prefer-raise-over-silent-fallback).
    """
    path = _bundled_lance_extension_path()
    if path is None:
        raise RuntimeError(
            "Bundled lance.duckdb_extension not found. Set "
            f"{LANCE_EXT_PATH_ENV} or ship it in Resources. Refusing to INSTALL "
            "over the network (blocked under the app sandbox)."
        )

    allow_unsigned = os.getenv(LANCE_EXT_ALLOW_UNSIGNED_ENV, "").strip().lower() in {
        "1", "true", "yes", "on",
    }
    try:
        if allow_unsigned:
            # Dev-only escape hatch for locally built (unsigned) binaries.
            conn.execute("SET allow_unsigned_extensions = true")
        conn.execute(f"LOAD '{str(path)}'")
    except duckdb.Error as exc:
        raise RuntimeError(
            f"Failed to LOAD lance extension from {path}. Likely an ABI "
            "mismatch (extension built for a different DuckDB version) or an "
            "unsigned binary without allow_unsigned_extensions. See GATE-0.md."
        ) from exc

    logger.info("Loaded lance DuckDB extension from %s", path)
