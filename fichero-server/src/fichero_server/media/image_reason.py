"""Why a page's original cannot be read, as a code and in words.

One classifier for the export (`export_service._why_image_unavailable`) and the thumbnail, display and source routes
(`api/routes/system/storage.py`). It looks at the file system only for the recorded path, and never puts the path in the
words (a drive's name is the one part it names).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fichero_server.models import Document

NO_RECORDED_FILE = "no_recorded_file"
VOLUME_NOT_MOUNTED = "volume_not_mounted"
MOVED_OR_DELETED = "moved_or_deleted"
ACCESS_NOT_GRANTED = "access_not_granted"
UNREADABLE = "unreadable"

#: The metadata keys `db.storage.resolve_source` tries after the document's own path, in its order.
PATH_KEYS = ("source_path", "full_path", "display_path", "local_path")


def _paths_of(doc: Document) -> list[str]:
    return [p for p in [doc.path, *((doc.metadata or {}).get(k) for k in PATH_KEYS)] if p and isinstance(p, str)]


def owner_of_source(doc: Document, db: Any = None) -> Document:
    """The document whose file this one's picture comes from: itself, or for a page with no path of its own (a PDF page,
    `db.storage.resolve_pdf_render_source`) its parent."""
    from fichero_server.models import DocType

    if db is not None and not _paths_of(doc) and doc.doc_type == DocType.page and doc.parent_id:
        parent = db.get_committed(Document, doc.parent_id)
        if parent is not None:
            return parent
    return doc


def _volume_of(path: Path) -> str | None:
    """The drive name when `path` is under /Volumes/<name> and /Volumes/<name> is not there; else None."""
    parts = path.parts
    if len(parts) >= 3 and parts[:2] == ("/", "Volumes") and not os.path.exists(Path("/Volumes") / parts[2]):
        return parts[2]
    return None


def classify_image_unavailable(doc: Document, package_path: Path | None = None, db: Any = None) -> tuple[str, str]:
    """(code, words) for the path `resolve_source` tries first: the document's own, then its metadata's, and for a page
    with none (given `db`) its parent's. A package-relative path ("files/…") is looked for under the package."""
    paths = _paths_of(owner_of_source(doc, db))
    if not paths:
        return NO_RECORDED_FILE, "no recorded file for this page"
    try:
        recorded = Path(paths[0]).expanduser()
        if not recorded.is_absolute() and package_path is not None:
            recorded = package_path / recorded
        os.stat(recorded)
    except FileNotFoundError:
        drive = _volume_of(recorded)
        if drive is not None:
            return VOLUME_NOT_MOUNTED, f"the drive '{drive}' is not connected"
        return MOVED_OR_DELETED, "not found at its recorded place (moved or deleted)"
    except PermissionError:
        return ACCESS_NOT_GRANTED, "this engine may not read it: grant access to its folder"
    except OSError as exc:
        return UNREADABLE, f"this engine could not open it ({exc.strerror or type(exc).__name__})"
    except (ValueError, RuntimeError):  # a NUL in the path; `~name` of a user that does not exist
        return UNREADABLE, "this engine could not open it (the recorded path is not usable)"
    return ACCESS_NOT_GRANTED, "this engine may not open files in that folder: grant access to the folder"
