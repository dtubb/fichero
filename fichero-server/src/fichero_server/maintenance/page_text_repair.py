"""Give back the page text a classifier overwrote (`source.read.metadata-tools-never-write-page-text`).

Until this fix, `vision_base._propagate_to_page_children` wrote every tool's per-page answer onto the page child's
`page_content`, so Classify Script over a PDF left each page's text as its `{script_type, confidence, notes}` JSON.
Run by the open library's engine, once per open, after an update: a page whose text IS such JSON gets its transcription
back (the newest transcription artifact on the page, else the PDF's own text layer). A page with neither keeps its current text
and is FLAGGED (`read_flag`, kind `needs-re-reading`, the mark a flagged read already carries) so a person can re-read it: a page
is never blanked.
A text a person saved is never touched. Idempotent: a repaired page no longer matches. It counts first (`dry_run`), and
what it did is one audited action in the app database (never a standalone script on a library).
"""
from __future__ import annotations

import json
import logging
from typing import Any

from fichero_server.core.timeutil import utc_now
from fichero_server.llm.read_guard import READ_FLAG_KEY

logger = logging.getLogger(__name__)

NEEDS_REREADING = "needs-re-reading"
_KEYS = {"script_type", "confidence", "notes", "needs_human_selection"}
_TRANSCRIBING = ("transcription", "handwriting")


def clear_needs_rereading(doc: Any) -> None:
    """A successful read wrote this page's text: the repair's `needs-re-reading` mark no longer holds, so it goes (only that
    kind: a flag some other check put on the page is that check's to clear)."""
    meta = getattr(doc, "metadata", None)
    kept = without_needs_rereading(meta)
    if kept is not meta:
        doc.metadata = kept


def without_needs_rereading(meta: Any) -> Any:
    """`meta` without the repair's flag (the same object when it carries none): for a writer that builds the metadata itself."""
    flag = meta.get(READ_FLAG_KEY) if isinstance(meta, dict) else None
    if isinstance(flag, dict) and flag.get("kind") == NEEDS_REREADING:
        return {k: v for k, v in meta.items() if k != READ_FLAG_KEY}
    return meta


def is_classification_json(text: Any) -> bool:
    """True when the whole text is a classifier's answer: a JSON object with `script_type` and `confidence` and nothing else a
    transcription would carry."""
    body = (text or "").strip() if isinstance(text, str) else ""
    if body.startswith("```"):
        body = "\n".join(ln for ln in body.splitlines() if not ln.strip().startswith("```")).strip()
    if not body.startswith("{"):
        return False
    try:
        parsed = json.loads(body)
    except ValueError:
        return False
    return isinstance(parsed, dict) and {"script_type", "confidence"} <= set(parsed) and set(parsed) <= _KEYS


def _transcription_of(db: Any, doc: Any) -> tuple[str, str]:
    """(text, where it came from) for a page whose text was overwritten; ("", "") when nothing can be recovered."""
    from fichero_server.models import Artifact, Document
    from fichero_server.workflows.tools.llm_base import split_script_classification

    arts = [a for a in db.query(Artifact, document_id=doc.id)
            if (a.artifact_type or "") in _TRANSCRIBING or (a.artifact_type or "").startswith("transcription")]
    for art in sorted(arts, key=lambda a: a.created_at or 0, reverse=True):
        text, _note = split_script_classification(art.content or "")
        if text.strip() and not is_classification_json(text):
            return text, f"its newest {art.artifact_type} ({art.id})"
    parent = db.get(Document, doc.parent_id) if getattr(doc, "parent_id", None) else None
    # the file the page was cut from: the import records where it came from (`source_path`), else the document's path
    path = ((getattr(parent, "metadata", None) or {}).get("source_path") or getattr(parent, "path", None) or "")
    if path.lower().endswith(".pdf") and doc.sequence:
        try:
            import fitz

            with fitz.open(path) as pdf:
                layer = pdf[int(doc.sequence) - 1].get_text() or ""
            if layer.strip():
                return layer, "the PDF's own text layer"
        except Exception:  # noqa: BLE001 -- a missing or unreadable file: the page has nothing to restore from and is flagged
            logger.info("page text repair: no text layer for %s", doc.id, exc_info=True)
    return "", ""


def repair_classification_page_text(db: Any, *, dry_run: bool = False) -> dict[str, Any]:
    """Restore the pages whose text is a classifier's JSON. Returns the counts and ids (`restored`, `flagged`, `left_edited`); `flagged` pages are marked unless `dry_run`."""
    from fichero_server.models import Document
    from fichero_server.workflows.curation_guard import page_content_is_user_edited

    restored: list[str] = []
    flagged: list[str] = []
    newly_flagged: list[str] = []
    left_edited: list[str] = []
    rows = db.execute_fetchall(
        "SELECT id FROM documents WHERE page_content LIKE '%script_type%' AND deleted_at IS NULL")
    for (doc_id,) in rows:
        doc = db.get(Document, doc_id)
        if doc is None or not is_classification_json(doc.page_content):
            continue
        if page_content_is_user_edited(doc):
            left_edited.append(doc_id)
            continue
        text, _where = _transcription_of(db, doc)
        if not text:  # nothing to restore from: the page keeps its text and carries a needs-re-reading flag
            flagged.append(doc_id)
            if READ_FLAG_KEY not in (doc.metadata if isinstance(doc.metadata, dict) else {}):
                newly_flagged.append(doc_id)
                if not dry_run:
                    doc.metadata = {**(doc.metadata or {}), READ_FLAG_KEY: {
                        "kind": NEEDS_REREADING, "measure": {},
                        "reason": "a classifier's answer had replaced this page's text and no transcription or text layer is left "
                                  "to restore it from: read the page again"}}
                    db.save(doc)
            continue
        restored.append(doc_id)
        if dry_run:
            continue
        doc.page_content = text
        db.save(doc)
    if restored and not dry_run:  # queued, never run inline at open: the embed is a job a scheduler runs (Activity, pause, quit)
        try:
            from fichero_server.actions.page_text_cache import queue_reembed

            queue_reembed(db, restored)
        except Exception:  # noqa: BLE001 -- the text is back; search catches up at the next embed of the page
            logger.warning("page text repair: could not queue the re-embed of %d page(s)", len(restored), exc_info=True)
    return {"restored": restored, "flagged": flagged, "newly_flagged": newly_flagged, "left_edited": left_edited, "dry_run": dry_run}


def _record_finished_row(db: Any, restored: int, flagged: int) -> None:
    """One finished row in Activity, the record a finished job uses, so the app shows what the repair did with no new screen:
    "3 pages restored, 1 needs re-reading". Only when it changed something."""
    if restored + flagged == 0:
        return
    import uuid

    from fichero_server.execution import jobs

    words = f"{restored} page{'s' if restored != 1 else ''} restored, {flagged} need{'s' if flagged == 1 else ''} re-reading"
    try:
        job_id = f"repair-page-text-{uuid.uuid4().hex[:12]}"
        jobs._record(db, job_id, kind="workflow", subject=job_id, parent_id=None, state="done", reason=words,
                     name="Page text repair")
    except Exception:  # noqa: BLE001 -- the repair stands; the row is a courtesy
        logger.exception("page text repair: could not record its Activity row")


def repair_on_open(db: Any) -> dict[str, Any]:
    """Count first; when any page needs it, repair, say so in the log, and audit it (one action, ids capped)."""
    counted = repair_classification_page_text(db, dry_run=True)
    if not (counted["restored"] or counted["newly_flagged"]):
        return counted
    done = repair_classification_page_text(db)
    logger.warning(
        "Page text repair (classifier JSON had replaced page text): restored %d from a transcription or the PDF's text layer, "
        "flagged %d for re-reading (nothing to restore from; their text is kept): %s, left %d a person saved",
        len(done["restored"]), len(done["flagged"]), done["flagged"][:20], len(done["left_edited"]))
    _record_finished_row(db, len(done["restored"]), len(done["newly_flagged"]))
    try:
        from fichero_server.db.app import get_app_db
        from fichero_server.models import ActionAudit

        get_app_db().save_action_audit(ActionAudit(
            action_name="repair.classification-page-text", actor="engine",
            target_ids=(done["restored"] + done["flagged"])[:200],
            params={"restored": len(done["restored"]), "flagged": len(done["flagged"]),
                    "left_edited": len(done["left_edited"])},
            created_at=utc_now()))
    except Exception:  # noqa: BLE001 -- the repair stands; the audit failure is logged
        logger.exception("page text repair: could not write its audit")
    return done
