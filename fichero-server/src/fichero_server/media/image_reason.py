"""Why a page's original cannot be read, as a code and in words.

One classifier for the export (`export_service._why_image_unavailable`) and the thumbnail, display and source routes
(`api/routes/system/storage.py`). It looks at the file system only for the recorded path.
"""

from __future__ import annotations

import os
from pathlib import Path

from fichero_server.models import Document

NO_RECORDED_FILE = "no_recorded_file"
VOLUME_NOT_MOUNTED = "volume_not_mounted"
MOVED_OR_DELETED = "moved_or_deleted"
ACCESS_NOT_GRANTED = "access_not_granted"
UNREADABLE = "unreadable"


def _volume_of(path: Path) -> str | None:
    """The drive name when `path` is under /Volumes/<name> and /Volumes/<name> is not there; else None."""
    parts = path.parts
    if len(parts) >= 3 and parts[:2] == ("/", "Volumes") and not os.path.exists(Path("/Volumes") / parts[2]):
        return parts[2]
    return None


def classify_image_unavailable(doc: Document, package_path: Path | None = None) -> tuple[str, str]:
    """(code, words). A package-relative path ("files/…") is looked for under the package, not the process's directory."""
    if not doc.path:
        return NO_RECORDED_FILE, "no recorded file for this page"
    recorded = Path(doc.path).expanduser()
    if not recorded.is_absolute() and package_path is not None:
        recorded = package_path / recorded
    try:
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
    return ACCESS_NOT_GRANTED, "this engine may not open files in that folder: grant access to the folder"
