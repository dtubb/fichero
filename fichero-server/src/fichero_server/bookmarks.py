"""
macOS Security-Scoped Bookmarks for Fichero.

Bookmarks are better than paths because they:
- Survive file moves/renames
- Work in sandboxed apps
- Track files across volumes
- Maintain security-scoped access to user files

Usage:
    from fichero_server.bookmarks import create_bookmark, resolve_bookmark

    # Create bookmark for external file
    bookmark = create_bookmark(Path("/Users/bob/docs/letter.jpg"))
    doc.set_bookmark(bookmark)
    db.save(doc)

    # Resolve bookmark later
    path = resolve_bookmark(doc.bookmark)

    # Stop accessing when done (for sandboxed apps)
    stop_accessing(path)
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off"}

# Try to import Rubicon ObjC for macOS APIs
try:
    from rubicon.objc import ObjCClass, autoreleasepool

    NSURL = ObjCClass("NSURL")
    NSData = ObjCClass("NSData")
    _HAS_RUBICON = True
except ImportError:
    _HAS_RUBICON = False
    NSURL = None
    NSData = None


# =============================================================================
# Bookmark Constants (from NSURL.h)
# =============================================================================

# NSURLBookmarkCreationOptions - flags for bookmarkDataWithOptions:
_BOOKMARK_CREATION_WITH_SECURITY_SCOPE = (
    1 << 11
)  # NSURLBookmarkCreationWithSecurityScope
_BOOKMARK_CREATION_SECURITY_SCOPE_ALLOW_ONLY_READ_ACCESS = (
    1 << 12
)  # NSURLBookmarkCreationSecurityScopeAllowOnlyReadAccess

# NSURLBookmarkResolutionOptions - flags for URLByResolvingBookmarkData:
_BOOKMARK_RESOLUTION_WITH_SECURITY_SCOPE = (
    1 << 10
)  # NSURLBookmarkResolutionWithSecurityScope


# =============================================================================
# Bookmark Functions
# =============================================================================


def create_bookmark(path: Path, read_only: bool = False) -> bytes | None:
    """Create a security-scoped bookmark for a file.

    Args:
        path: Path to file
        read_only: If True, bookmark allows read-only access.
                   If False (default), allows read-write access.

    Returns:
        Bookmark data as bytes, or None on failure

    Note:
        On non-macOS systems, returns None.
    """
    if not is_available():
        logger.debug("Rubicon not available - bookmarks disabled")
        return None

    if not path.exists():
        logger.warning("Cannot create bookmark for non-existent path: %s", path)
        return None

    try:
        # Autorelease pool (2026-08-09): this runs PER FILE on a worker
        # thread with NO pool — every NSURL/NSData created here leaked for
        # the process lifetime, and `ctypes.string_at` read the autoreleased
        # NSData's buffer with nothing keeping it alive (a use-after-free
        # candidate for the no-traceback crash class). The pool bounds the
        # objects' lifetime; the bytes are COPIED before the pool drains.
        with autoreleasepool():
            url = NSURL.fileURLWithPath_(str(path.resolve()))

            # Build options
            options = _BOOKMARK_CREATION_WITH_SECURITY_SCOPE
            if read_only:
                options |= _BOOKMARK_CREATION_SECURITY_SCOPE_ALLOW_ONLY_READ_ACCESS

            # Create bookmark
            # Method signature: bookmarkDataWithOptions:includingResourceValuesForKeys:relativeToURL:error:
            bookmark_data = url.bookmarkDataWithOptions_includingResourceValuesForKeys_relativeToURL_error_(
                options,
                None,  # No resource keys
                None,  # Not relative
                None,  # No error pointer
            )

            if bookmark_data:
                # Convert NSData to bytes — copied INSIDE the pool, while the
                # NSData is guaranteed alive.
                try:
                    import ctypes

                    length = bookmark_data.length
                    if callable(length):
                        length = length()
                    if length > 0:
                        ptr = bookmark_data.bytes
                        if callable(ptr):
                            ptr = ptr()
                        return ctypes.string_at(ptr, length)
                except (TypeError, AttributeError, OSError) as e:
                    logger.warning("Error extracting bookmark data: %s", e)

            logger.warning("Failed to create bookmark for %s", path)
            return None

    except Exception as e:
        logger.warning("Bookmark creation error for %s: %s", path, e)
        return None


def resolve_bookmark(bookmark_data: bytes) -> Path | None:
    """Resolve a security-scoped bookmark to a path.

    Also starts security-scoped access to the resource.
    Call stop_accessing() when done.

    Args:
        bookmark_data: Raw bookmark bytes

    Returns:
        Path if bookmark is valid and file exists, None otherwise
    """
    if not is_available():
        return None

    if not bookmark_data:
        return None

    try:
        # Convert bytes to NSData
        data = NSData.dataWithBytes_length_(bookmark_data, len(bookmark_data))

        # Resolve bookmark
        # Method signature: URLByResolvingBookmarkData:options:relativeToURL:bookmarkDataIsStale:error:
        # Returns (url, is_stale, error) but we handle it differently in Rubicon
        result = NSURL.URLByResolvingBookmarkData_options_relativeToURL_bookmarkDataIsStale_error_(
            data,
            _BOOKMARK_RESOLUTION_WITH_SECURITY_SCOPE,
            None,  # Not relative
            None,  # is_stale out parameter
            None,  # error out parameter
        )

        # Rubicon returns the URL directly (other params are out params)
        url = result
        if url is None:
            logger.debug("Bookmark resolution returned None")
            return None

        # Get path from URL
        path_str = url.path
        if not path_str:
            logger.debug("Resolved bookmark URL has no path")
            return None

        path = Path(str(path_str))

        if not path.exists():
            logger.debug("Resolved bookmark path does not exist: %s", path)
            return None

        # Start security-scoped access
        success = url.startAccessingSecurityScopedResource()
        if not success:
            logger.warning("Failed to start security scope access for %s", path)
            # Still return path - it might work without security scope

        logger.debug("Resolved bookmark to: %s", path)
        return path

    except Exception as e:
        logger.warning("Bookmark resolution error: %s", e)
        return None


def stop_accessing(path: Path) -> None:
    """Stop accessing a security-scoped resource.

    Call this when done accessing a file that was resolved from a bookmark.

    Args:
        path: Path to stop accessing
    """
    if not is_available():
        return

    try:
        url = NSURL.fileURLWithPath_(str(path.resolve()))
        url.stopAccessingSecurityScopedResource()
        logger.debug("Stopped security scope access for: %s", path)
    except Exception as e:
        logger.debug("Error stopping security scope access: %s", e)


def is_bookmark_stale(bookmark_data: bytes) -> bool:
    """Check if a bookmark is stale and needs to be recreated.

    A bookmark becomes stale when the file is modified in certain ways.

    Args:
        bookmark_data: Raw bookmark bytes

    Returns:
        True if stale, False otherwise
    """
    if not bookmark_data:
        return True

    if not is_available():
        # Without bookmark resolution support, treat unknown bookmark payloads
        # conservatively as stale.
        return True

    try:
        data = NSData.dataWithBytes_length_(bookmark_data, len(bookmark_data))

        # Create a boolean pointer to receive is_stale
        # In Rubicon, we need to check differently - by attempting to resolve
        result = NSURL.URLByResolvingBookmarkData_options_relativeToURL_bookmarkDataIsStale_error_(
            data, _BOOKMARK_RESOLUTION_WITH_SECURITY_SCOPE, None, None, None
        )

        # If resolution fails, consider it stale
        return result is None

    except Exception:
        return True


def refresh_bookmark(path: Path, old_bookmark: bytes | None = None) -> bytes | None:
    """Create a fresh bookmark for a path.

    Use this to update stale bookmarks.

    Args:
        path: Path to file
        old_bookmark: Previous bookmark (unused, for API symmetry)

    Returns:
        New bookmark data, or None on failure
    """
    return create_bookmark(path, read_only=False)


# =============================================================================
# Context Manager
# =============================================================================


class BookmarkAccess:
    """Context manager for security-scoped bookmark access.

    Usage:
        with BookmarkAccess(bookmark_data) as path:
            if path:
                process_file(path)
        # Access automatically stopped when exiting
    """

    def __init__(self, bookmark_data: bytes | None):
        self.bookmark_data = bookmark_data
        self.path: Path | None = None

    def __enter__(self) -> Path | None:
        if self.bookmark_data:
            self.path = resolve_bookmark(self.bookmark_data)
        return self.path

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.path:
            stop_accessing(self.path)
        return False  # Don't suppress exceptions


# =============================================================================
# Convenience
# =============================================================================


def is_available() -> bool:
    """Check if security-scoped bookmarks should be used by this engine.

    Returns:
        True if running on macOS with Rubicon available, unless disabled with
        FICHERO_ENABLE_MAC_BOOKMARKS=0/false/no/off. Remote engines can set
        the env var false to fail closed on Mac bookmark metadata.
    """
    configured = os.environ.get("FICHERO_ENABLE_MAC_BOOKMARKS")
    if configured is not None:
        value = configured.strip().lower()
        if value in _FALSY:
            return False
        if value in _TRUTHY:
            return sys.platform == "darwin" and _HAS_RUBICON
        logger.warning(
            "Ignoring invalid FICHERO_ENABLE_MAC_BOOKMARKS=%r; using auto mode",
            configured,
        )
    return sys.platform == "darwin" and _HAS_RUBICON


__all__ = [
    "create_bookmark",
    "resolve_bookmark",
    "stop_accessing",
    "is_bookmark_stale",
    "refresh_bookmark",
    "BookmarkAccess",
    "is_available",
]
