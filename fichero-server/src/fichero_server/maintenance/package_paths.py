"""A project's own files are stored relative to its package (#7093).

A path that points inside an earlier location of this package (an absolute path through a `.fichero` folder into its
`files` or `storage` folder) bakes that location in: copied to another Mac or renamed, the project lost every original.
On open, such a path whose tail exists in THIS package becomes `files/<tail>` (or `storage/<tail>`), resolved against
wherever the package is opened (`db.storage.resolve_source`). Run on every open in one pass over the documents (paths are stat-ed only where they match): a rewritten path is relative and no
longer matches, so a second run changes nothing. A tail with a `..` segment, or one that resolves outside the package, is never rewritten. Only a document's `path` and its path-valued metadata change; ids never
do. A path outside any package (a linked original) or whose tail is not in this package is left alone. What it did is
one audited action.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from fichero_server.core.timeutil import utc_now

logger = logging.getLogger(__name__)

#: The part of a path a package keeps whatever its location: `files/...` or `storage/...` after a `.fichero` folder.
_INSIDE = re.compile(r"\.fichero/((?:files|storage)/.+)$")
_PATH_KEYS = ("source_path", "full_path", "display_path", "local_path")


def _relative(value: Any, package: Path) -> str | None:
    """The package-relative spelling of an absolute path into some earlier location of this package, else None."""
    if not isinstance(value, str) or not value.startswith("/"):
        return None
    found = _INSIDE.search(value)
    if found is None:
        return None
    tail = found.group(1)
    if ".." in tail.split("/"):
        return None
    inside = (package / tail).resolve()
    if not inside.is_relative_to(package.resolve()) or not inside.exists():
        return None
    return tail


def relativize_package_paths(db: Any) -> dict[str, Any]:
    """Rewrite the documents' absolute package paths to relative ones; returns `rewritten` (document ids)."""
    from fichero_server.models import Document

    package = Path(db.path).parent
    changes: list[tuple[Any, str | None, dict[str, str]]] = []
    for doc in db.query(Document):
        path = _relative(doc.path, package)
        meta = doc.metadata if isinstance(doc.metadata, dict) else {}
        moved = {k: r for k in _PATH_KEYS if (r := _relative(meta.get(k), package))}
        if path is not None or moved:
            changes.append((doc, path, moved))
    for doc, path, moved in changes:
        if path is not None:
            doc.path = path
        if moved:
            doc.metadata = {**doc.metadata, **moved}
        db.save(doc)
    return {"rewritten": [doc.id for doc, _, _ in changes]}


def relativize_on_open(db: Any) -> dict[str, Any]:
    """One pass over the documents; audit only when something was rewritten."""
    done = relativize_package_paths(db)
    if not done["rewritten"]:
        return done
    logger.warning("Package paths: %d document(s) pointed into an earlier location of this package; now relative: %s",
                   len(done["rewritten"]), done["rewritten"][:20])
    try:
        from fichero_server.db.app import get_app_db
        from fichero_server.models import ActionAudit

        get_app_db().save_action_audit(ActionAudit(
            action_name="repair.package-files-relative", actor="engine", target_ids=done["rewritten"][:200],
            params={"rewritten": len(done["rewritten"])}, created_at=utc_now()))
    except Exception:  # noqa: BLE001 -- the rewrite stands; the audit failure is logged
        logger.exception("package paths: could not write its audit")
    return done
