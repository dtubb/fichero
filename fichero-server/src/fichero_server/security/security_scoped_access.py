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

Two ways in, because there are two moments (#3773)
--------------------------------------------------
1. **At spawn** — ``activate_library_bookmarks()`` reads the env var above. This
   covers the libraries the app already knew about, and costs no round-trip on a
   cold start.
2. **At runtime** — ``grant_access()``, driven by ``POST /api/sandbox/security-scoped-access``.
   The env var is fixed at spawn, but the user picks libraries WHILE the engine
   runs (an open panel, an import), and the engine is never restarted. Without a
   runtime handoff those libraries stay unreadable until the app relaunches —
   which includes the very first library a new user ever picks. The app posts the
   freshly-minted bookmark; we resolve it on the live process.

Both funnel into the same ``start_access()``. Grants are idempotent and additive:
re-granting a path already held is a no-op that reports success, because the app
may legitimately re-send (a retry, a reopen, a relaunch of the engine under a
still-running app) and a second ``startAccessingSecurityScopedResource()`` on a
fresh NSURL for the same path would leak a redundant grant we never balance.
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

# Paths this process currently holds a grant for. Guards re-entry (#3773): the app
# may re-post a bookmark it already sent, and resolving it a second time would add
# another NSURL + another startAccessingSecurityScopedResource() that nothing ever
# balances. Success is reported either way — the caller asked "can you read this?",
# and the answer is yes.
_GRANTED: set[str] = set()


def granted_paths() -> frozenset[str]:
    """Paths this process can currently read. Snapshot, so callers cannot mutate it."""
    return frozenset(_GRANTED)


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
    _GRANTED.add(path)
    logger.info("Security-scoped access granted: %s", path)
    return True


def _readable_via_inherited_scope(path: str) -> bool:
    """Can this process ALREADY read ``path`` without resolving the bookmark?

    Why this exists (found live, 2026-08-08): an app-scoped security bookmark
    resolves only in the code identity that minted it. This engine is a
    DIFFERENT bundle (``…fichero_server``) running under
    ``com.apple.security.inherit`` — so ``NSURL`` resolution here fails with
    NSCocoaError 259 ("isn't in the correct format") even for perfectly good
    bookmarks, and every grant died on that error while the APP had already
    resolved the same bookmark and called
    ``startAccessingSecurityScopedResource()``. An inherit child SHARES the
    parent's sandbox, including the extensions that call turned on — so the
    right question is not "can I resolve this bookmark" but "can I read this
    directory".

    The probe is a real ``listdir``, not ``os.access``: ``os.access`` answers
    from uid/permission bits and can say yes while the SANDBOX still denies
    the open. A library is always a directory (a ``.fichero`` package or a
    picked folder), so listing is the honest capability test.
    """
    try:
        os.listdir(path)
    except OSError:
        return False
    return True


def _engine_is_sandboxed() -> bool:
    """Is THIS process inside an App Sandbox? The kernel's own signal —
    ``APP_SANDBOX_CONTAINER_ID`` is set by macOS in every sandboxed process
    and absent otherwise — the same check the app's SandboxEnvironment makes.
    """
    return bool(os.environ.get("APP_SANDBOX_CONTAINER_ID"))


def start_access_or_inherited(path: str, bookmark: bytes, foundation: Any) -> bool:
    """``start_access``, falling back to the inherited-sandbox probe above.

    One funnel for BOTH grant paths (spawn env + runtime route), so they can
    never disagree about what counts as granted.

    SECURITY (lane audit A1, 2026-08-09): a grant lands in ``_GRANTED``,
    which ``path_security`` spreads into the ALLOWED ROOTS — so the fallback
    changes what the allowlist means. Its entire justification is "an
    inherit child shares the parent's already-started extensions", so it
    runs ONLY when this process is actually sandboxed: there, ``listdir``
    can only succeed where the kernel already permits, and the fallback's
    reach is exactly what the app granted. In an UNSANDBOXED engine (Dev
    Local external, server deployments) ``listdir`` succeeds across the
    whole home, so the same fallback would let any caller holding the local
    token promote ANY readable directory to an allowed root — the allowlist
    would stop being a control. There, resolution failure stays fatal, as
    before 6d60cbf65.
    """
    if start_access(path, bookmark, foundation):
        return True
    if _engine_is_sandboxed() and _readable_via_inherited_scope(path):
        _GRANTED.add(path)
        logger.info(
            "Security-scoped access granted via inherited sandbox scope "
            "(bookmark unresolvable in this process): %s", path
        )
        return True
    return False


class BookmarkGrantError(Exception):
    """A runtime bookmark could not be turned into access. Carries a reason for the app."""


def grant_access(path: str, encoded: str) -> bool:
    """Grant access to ONE library, handed over while the engine is already running.

    This is the runtime half of the handoff (#3773) — the app calls it from
    ``POST /api/sandbox/security-scoped-access`` after the user picks a library that
    did not exist when the engine spawned.

    Returns True when this process may now read ``path``. Raises BookmarkGrantError
    with a reason when it may not. It RAISES rather than returning False silently:
    the caller is the app, which is about to open a library, and a library it
    cannot read must surface as an error the user sees — not as a grant that
    quietly did nothing (see the engine-wide rule against silent fallbacks).
    """
    if not path:
        raise BookmarkGrantError("path is required")

    if path in _GRANTED:
        # Idempotent: already held. Do NOT resolve again — a second NSURL for the
        # same path is a redundant, unbalanced grant.
        logger.debug("Security-scoped access already held: %s", path)
        return True

    try:
        bookmark = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise BookmarkGrantError(f"bookmark is not valid base64: {exc}") from exc
    if not bookmark:
        raise BookmarkGrantError("bookmark is empty")

    foundation = _load_foundation()
    if foundation is None:
        # Only reachable off-macOS or in a slim build. The sandboxed engine always
        # has PyObjC (pyobjc-framework-Cocoa is a dependency), so this is a real
        # misconfiguration, not a normal path — say so.
        raise BookmarkGrantError("PyObjC/Foundation unavailable — cannot resolve a security-scoped bookmark")

    if not start_access_or_inherited(path, bookmark, foundation):
        raise BookmarkGrantError(f"could not start security-scoped access to {path}")
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

    granted = [path for path, data in bookmarks.items() if start_access_or_inherited(path, data, foundation)]
    logger.info("Security-scoped access: %d of %d librar(ies) granted", len(granted), len(bookmarks))
    return granted
