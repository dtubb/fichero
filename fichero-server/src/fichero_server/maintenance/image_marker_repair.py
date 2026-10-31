"""Give back the text a reading's metadata field held before the image marker replaced it (#6296 follow-up).

From 2026-10-30 until the fix, `save_artifact` stored `{"image_read": "<signature>"}` in a document's `description`, `caption`
and the like, in place of the reading's text. The reading's artifact kept its content, so the field is put back from the newest
artifact of the same type on the page (the first 1000 characters, as the field was always written). No model is called. A field
with no such artifact is left as it is and counted. Idempotent: a repaired field no longer matches.
"""
from __future__ import annotations

import logging
from typing import Any

from fichero_server.media.current_image import IMAGE_READ

logger = logging.getLogger(__name__)


def repair_image_marker_fields(db: Any) -> dict[str, int]:
    """Replace every `{image_read}`-only metadata field with its artifact's text; `{"repaired": n, "left": n}`."""
    from fichero_server.models import Artifact, Document

    repaired = left = 0
    ids = [r[0] for r in db.execute_fetchall(
        "SELECT id FROM documents WHERE CAST(metadata AS VARCHAR) LIKE ? AND deleted_at IS NULL", [f"%{IMAGE_READ}%"])]
    for doc_id in ids:
        doc = db.get(Document, doc_id)
        meta = doc.metadata if doc is not None and isinstance(doc.metadata, dict) else {}
        broken = [k for k, v in meta.items() if isinstance(v, dict) and set(v) == {IMAGE_READ}]
        if not broken:
            continue
        arts = sorted(db.query(Artifact, document_id=doc_id), key=lambda a: a.created_at or 0, reverse=True)
        for key in broken:
            art = next((a for a in arts if a.artifact_type == key and (a.content or "").strip()), None)
            if art is None:
                left += 1
                continue
            meta[key] = art.content[:1000]
            repaired += 1
        doc.metadata = meta
        db.save(doc)
    if repaired or left:
        logger.warning("Image-marker repair: put %d metadata field(s) back from their reading's text; left %d with no reading to "
                       "restore from", repaired, left)
    return {"repaired": repaired, "left": left}
