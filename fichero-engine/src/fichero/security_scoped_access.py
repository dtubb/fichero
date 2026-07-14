"""Resolve the app's security-scoped bookmarks so the sandboxed engine can open
the user's library (#3747).

Why this exists
---------------
Under the Mac App Store build the engine runs inside the app's App Sandbox via
``com.apple.security.inherit``. Inheritance passes only the **static** rights in
the parent's entitlements — **not** the dynamic Powerbox grant the user creates by
picking a folder in an open panel. So a library in ``~/Documents`` is unreachable
to this process: a plain ``open()`` fails, and DuckDB fails with it.

The app (which owns the Powerbox grant) mints an **app-scoped security-scoped
bookmark** for the library folder and hands it to us at spawn. We resolve it and
call ``startAccessingSecurityScopedResource()``, which grants THIS process access
for as long as we hold the URL. Only then may DuckDB touch the file.

Transport: ``FICHERO_LIBRARY_BOOKMARKS`` — a JSON object of
``{"<library path>": "<base64 bookmark data>"}``. A JSON map (not a bare string)
because a user can have several libraries open, and each needs its own grant.

This is a no-op — never an error — when there is nothing to do: not macOS, PyObjC
absent, env var unset, or the app is unsandboxed (the DMG build, where the engine
already has plain filesystem access). The engine must keep working in all of those.

KNOWN LIMIT — libraries added AFTER the engine starts
-----------------------------------------------------
The payload is an environment variable, so it is fixed at spawn: it grants the
libraries the app knew about when it launched the engine. If the user picks a NEW
library mid-session (an open panel, an import), the app mints a bookmark and
stores it, but this process never sees it — the engine keeps running, and its
environment cannot change. That library stays unreadable until the app restarts.

That is a real gap, not a design choice, and it is tracked separately: closing it
needs a runtime handoff (an endpoint the app posts the new bookmark to, which
calls ``start_access`` on the live process) rather than a spawn-time env var.
Until then the failure is LOUD, not silent — DuckDB raises a permission error the
app surfaces — which is the intended behaviour: better a clear error than a
library that half-opens.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

ENV_VAR = "FICHERO_LIBRARY_BOOKMARKS"

# The resolved NSURLs MUST outlive this function: access lasts only while the URL
# object is alive, so releasing it would revoke the grant mid-run. Held for the
# process lifetime, deliberately.
_ACTIVE_URLS: list[Any] = []


def _load_foundation() -> Any | None:
    """PyObjC Foundation, or None where it does not exist (Linux, or a slim build)."""
    try:
        import Foundation  # type: ignore
    except ImportError:
        return None
    return Foundation


def parse_bookmarks(raw: str | None) -> dict[str, bytes]:
    """Parse the env payload into ``{path: bookmark bytes}``.

    Pure, so it is unit-testable without a sandbox. Malformed input is dropped with
    a loud log rather than raising: a corrupt bookmark must not stop the engine from
    booting — it degrades to "that library is unreadable", which the app surfaces.
    """
    if not raw or not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("%s is not valid JSON — ignoring all bookmarks", ENV_VAR)
        return {}
    if not isinstance(payload, dict):
        logger.error("%s must be a JSON object of {path: base64}, got %s", ENV_VAR, type(payload).__name__)
        return {}

    out: dict[str, bytes] = {}
    for path, encoded in payload.items():
        if not isinstance(path, str) or not isinstance(encoded, str):
            logger.error("%s: skipping non-string entry", ENV_VAR)
            continue
        try:
            out[path] = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            logger.error("%s: bookmark for %s is not valid base64 — skipping", ENV_VAR, path)
    return out


def start_access(path: str, bookmark: bytes, foundation: Any) -> bool:
    """Resolve one bookmark and start security-scoped access to it.

    Returns True when this process may now read/write ``path``.
    """
    url, stale, error = foundation.NSURL.URLByResolvingBookmarkData_options_relativeToURL_bookmarkDataIsStale_error_(
        bookmark,
        foundation.NSURLBookmarkResolutionWithSecurityScope,
        None,
        None,
        None,
    )
    if error is not None or url is None:
        logger.error("Could not resolve security-scoped bookmark for %s: %s", path, error)
        return False
    if stale:
        # Still usable; the APP must re-mint it (only the app holds the Powerbox
        # grant). We log rather than fail so the user keeps working this session.
        logger.warning("Security-scoped bookmark for %s is STALE — the app should re-create it", path)

    if not url.startAccessingSecurityScopedResource():
        logger.error("startAccessingSecurityScopedResource() DENIED for %s", path)
        return False

    _ACTIVE_URLS.append(url)  # keep alive — access ends when the URL is released
    logger.info("Security-scoped access granted: %s", path)
    return True


def activate_library_bookmarks(raw: str | None = None) -> list[str]:
    """Resolve every bookmark the app handed us. Returns the paths now accessible.

    Call BEFORE any DuckDB open. A no-op when there is nothing to do.
    """
    raw = os.environ.get(ENV_VAR) if raw is None else raw
    bookmarks = parse_bookmarks(raw)
    if not bookmarks:
        return []

    foundation = _load_foundation()
    if foundation is None:
        logger.error(
            "%s was set but PyObjC/Foundation is unavailable — cannot open a sandboxed library", ENV_VAR
        )
        return []

    granted = [path for path, data in bookmarks.items() if start_access(path, data, foundation)]
    logger.info("Security-scoped access: %d of %d librar(ies) granted", len(granted), len(bookmarks))
    return granted
