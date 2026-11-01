"""Give back the text a reading's metadata field lost to the artifact's provenance (#6320, `preview.edit.reading-field-keeps-its-text`).

A reading's artifact carries `data` that says how it was made (`image_read`, `episode_id`, `thinking`...). Until the fix, a save with
a `metadata_field` stored that data in the document's field (`description`, `caption`...) whenever it was not empty, so the field held
`{"episode_id": ...}` (from 2026-08-12) or `{"image_read": ..., "episode_id": ...}` (from 2026-10-30) in place of the text. This puts the
text back from the newest artifact of the field's type on the page: no model is called.

It is a background job, queued by the open and marked done in `librarysettings` when it has finished; the open itself reads one
setting. It works a chunk at a time, steps aside for people, saves a page only when a field changed, and says in Activity how many
fields it put back and how many it could not (a field no artifact of its type was found for is left as it is, and counted).
"""
from __future__ import annotations

import json
import logging
from typing import Any

from fichero_server.execution import jobs
from fichero_server.media.current_image import NOT_THE_FIELD_KEYS, PROVENANCE_KEYS

logger = logging.getLogger(__name__)

KIND = "repair-reading-fields"
SUBJECT = "reading-fields"
DONE_SETTING = "reading_fields_repaired"
CHUNK = 50
IDS_CAP = 200  # ids kept in the row and the audit; the counts are exact
#: A field named for something other than its artifact type (the vision tools whose `metadata_field` differs from their `artifact_type`).
ARTIFACT_TYPE_OF_FIELD = {"doc_type": "classification", "script_type": "script_classification"}


def register_job_kinds() -> None:
    if KIND not in jobs.KINDS or jobs.KINDS[KIND].run is None:
        jobs.register_kind(KIND, lambda db, subject: run(db, subject), model=None, lane="database",
                           name="Put back the text of reading fields (repair)")


def is_done(db: Any) -> bool:
    return db.execute_fetchone("SELECT 1 FROM librarysettings WHERE id = ?", [DONE_SETTING]) is not None


def _mark_done(db: Any) -> None:
    db.execute("INSERT INTO librarysettings (id, value, updated_at) VALUES (?, '1', now()) ON CONFLICT (id) DO NOTHING", [DONE_SETTING])


def queue_if_needed(db: Any) -> str | None:
    """At open: one setting read. Empty library: marked done, nothing queued. Otherwise, not marked done: queue the job (an earlier waiting one is reused). Returns its id."""
    try:
        if is_done(db):
            return None
        if db.execute_fetchone("SELECT 1 FROM documents LIMIT 1") is None:  # nothing to damage, and no new page can be (the writer is fixed)
            _mark_done(db)
            return None
        register_job_kinds()
        return jobs.enqueue(db, KIND, SUBJECT)
    except Exception:  # noqa: BLE001 -- a library that cannot queue it still opens; the next open tries again
        logger.exception("Could not queue the reading-field repair")
        return None


def is_provenance_only(value: Any) -> bool:
    """A field the data replaced: a dict whose every key is provenance and that has a key a run's field write left (`image_read` or
    `episode_id`). A person's text (a string), a tool's own structured answer (other keys) and a dict of only `segment_id` (a segment
    read never wrote a field) never match."""
    return isinstance(value, dict) and bool(value) and set(value) <= PROVENANCE_KEYS and bool({"image_read", "episode_id"} & set(value))


def candidates(db: Any) -> list[str]:
    """The documents (trashed ones too: a restored page must not keep the damage) whose metadata mentions a provenance key: a coarse prefilter, each is checked."""
    return [r[0] for r in db.execute_fetchall(
        "SELECT id FROM documents WHERE (CAST(metadata AS VARCHAR) LIKE '%image_read%' "
        "OR CAST(metadata AS VARCHAR) LIKE '%episode_id%') ORDER BY id")]


def repair_document(db: Any, doc_id: str) -> tuple[int, int]:
    """`(put back, left)` for one document; saved only when a field changed."""
    from fichero_server.models import Artifact, Document

    doc = db.get(Document, doc_id)
    meta = dict(doc.metadata) if doc is not None and isinstance(doc.metadata, dict) else {}
    broken = [key for key, value in meta.items() if is_provenance_only(value)]
    fixed = left = 0
    for key in broken:
        # a flagged read or a compare arm was never the page's reading (H2)
        arts = [a for a in db.query(Artifact, document_id=doc_id, artifact_type=ARTIFACT_TYPE_OF_FIELD.get(key, key))
                if (a.content or "").strip() and not NOT_THE_FIELD_KEYS & set(a.data or {})]
        if not arts:
            left += 1
            continue
        meta[key] = max(arts, key=lambda a: a.created_at.timestamp() if a.created_at else 0).content[:1000]
        fixed += 1
    if fixed:
        doc.metadata = meta
        db.save(doc)
    return fixed, left


def _why_step_aside() -> str | None:
    from fichero_server.execution import throttle

    if jobs.is_paused():
        return "Paused by you"
    if jobs._scheduler.someone_is_waiting("database"):
        return "Stepped aside for work someone is waiting for"
    return throttle.why_wait(person_waiting=False)


def _resume(db: Any, job_id: str | None) -> dict[str, Any]:
    """What an earlier pass of this job row saved: counts, ids and the cursor (M3). A stop or a defer carries on from there."""
    try:
        row = jobs.read_job(db, job_id) if job_id else None
        state = json.loads(row["detail"]) if row and row.get("detail") else {}
    except Exception:  # noqa: BLE001 -- no readable state: start from the top, the work is idempotent
        state = {}
    return state if isinstance(state, dict) else {}


def run(db: Any, subject: str) -> dict[str, Any]:
    """Work through the candidates a chunk at a time, in id order; deferred (back to waiting, nothing lost) whenever it should step
    aside. The counts, the ids and a cursor are kept in the row's detail, so a resume neither recounts nor rescans what it did."""
    job_id = getattr(jobs._current, "job_id", None)
    state = _resume(db, job_id)
    fixed, left = int(state.get("put_back") or 0), int(state.get("left") or 0)
    put_ids, left_ids = list(state.get("put_ids") or []), list(state.get("left_ids") or [])
    after = state.get("after") or ""
    ids = [i for i in candidates(db) if i > after]
    for start in range(0, len(ids), CHUNK):
        why = _why_step_aside()
        if why:
            raise jobs.JobDeferred(why)
        chunk = ids[start:start + CHUNK]
        for doc_id in chunk:
            got, missed = repair_document(db, doc_id)
            fixed, left = fixed + got, left + missed
            if got and len(put_ids) < IDS_CAP:
                put_ids.append(doc_id)
            if missed and len(left_ids) < IDS_CAP:
                left_ids.append(doc_id)
        if job_id:
            jobs.save_detail(db, job_id, _detail(fixed, left, put_ids, left_ids, chunk[-1]),
                             reason=f"Put back {fixed} reading field{'s' if fixed != 1 else ''} so far")
    _mark_done(db)
    return finish(db, job_id, fixed, left, put_ids, left_ids)


def _detail(fixed: int, left: int, put_ids: list[str], left_ids: list[str], after: str = "") -> str:
    return json.dumps({"put_back": fixed, "left": left, "put_ids": put_ids, "left_ids": left_ids, "after": after})


def _say(db: Any, job_id: str, detail: str, words: str) -> bool:
    try:
        jobs.save_detail(db, job_id, detail, reason=words)
        return True
    except Exception:  # noqa: BLE001 -- the fields are repaired; the row is a courtesy
        logger.exception("reading-field repair: could not write its Activity words")
        return False


def _audit(db: Any, fixed: int, left: int, put_ids: list[str], left_ids: list[str]) -> bool:
    try:
        from fichero_server.core.timeutil import utc_now
        from fichero_server.db.app import get_app_db
        from fichero_server.models import ActionAudit

        get_app_db().save_action_audit(ActionAudit(
            action_name="repair.reading-fields", actor="engine", target_ids=put_ids[:IDS_CAP],
            params={"put_back": fixed, "left": left, "left_ids": left_ids[:IDS_CAP], "library": str(getattr(db, "path", ""))},
            created_at=utc_now()))
        return True
    except Exception:  # noqa: BLE001 -- the repair stands; the audit failure is logged
        logger.exception("reading-field repair: could not write its audit")
        return False


def finish(db: Any, job_id: str | None, fixed: int, left: int, put_ids: list[str] | None = None,
           left_ids: list[str] | None = None) -> dict[str, Any]:
    """Say it in Activity (the job's own row) and audit it; a failure to record never undoes the repair. The pages it could not
    repair are named in the row's detail, the log and the audit (M2)."""
    put_ids, left_ids = put_ids or [], left_ids or []
    words = (f"{fixed} reading field{'s' if fixed != 1 else ''} put back from the reading's text"
             + (f"; {left} could not be: no reading of their type was found" if left else ""))
    jobs.note_done(words)  # the scheduler writes the row's reason from this when the job ends `done`; save_detail's words are overwritten (H3)
    said = _say(db, job_id, _detail(fixed, left, put_ids, left_ids), words) if job_id else False
    if fixed or left:
        logger.warning("Reading-field repair: %s%s", words, f" (left: {left_ids[:20]})" if left_ids else "")
        _audit(db, fixed, left, put_ids, left_ids)
    return {"put_back": fixed, "left": left, "said": said}
