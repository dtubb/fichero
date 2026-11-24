"""Join Lines in the Same Row (`segment-editor.join-lines-in-the-same-row`).

The lines of a page that share a row become one line each, in one action and one undo. The grouping is
`media/line_join.rows`; the join of each group is `segment.merge` with its geometry joined and the other lines moved
into the first one's region (`segment-editor.merge-lines`). Each part that held no words becomes a word of the joined
line (`segment-editor.join-rows-keeps-parts-as-words`); a part's own words go to the joined line as `segment.merge`
moves them. `GET /segments/document/{doc_id}/join-rows-preview` answers what the action would do and writes nothing
(`segment-editor.join-rows-says-what-it-will-do`).
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from fichero_server.actions.registry import ActionContext, ChangeSpec, action
from fichero_server.api.main import get_library_database
from fichero_server.api.routes.document import segments as seg
from fichero_server.api.routes.document.segment_readings import _direction_of, _lines_are_vertical, direction_rungs
from fichero_server.core.timeutil import utc_now
from fichero_server.db import Database
from fichero_server.media import line_join
from fichero_server.models import Document, Segment, SegmentForwarding
from fichero_server.models.anchors import SourceAnchor
from fichero_server.models.segments import snapshot_segment_version

router = APIRouter(prefix="/segments")

ALONE = "no other line in its row"
OTHER_REGION = "its row-mates are in another region"
NO_OUTLINE = "it has no outline"
NOT_A_LINE = "it is not a line"


class SegmentJoinRowsParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segment_ids: list[str] = Field(min_length=1, description="The lines whose rows are joined: a selection, or every line of the page.")
    expected_versions: dict[str, int] = Field(description="Each segment's version as last read, {segment_id: version}; a changed segment is refused.")


def _plural(count: int) -> str:
    return f"{count} line" + ("" if count == 1 else "s")


def _plan(db: Database, segment_ids: list[str]) -> dict[str, Any]:
    """The groups the action would join, each in reading order with its kept id first, and the lines it leaves alone
    with the reason. Reads only."""
    rows: dict[str, Segment] = {}
    for segment_id in dict.fromkeys(segment_ids):
        seg._assert_not_provisional_http(segment_id, what="segment_id")
        row = db.get(Segment, segment_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Segment not found: {segment_id}")
        rows[segment_id] = row
    seg._same_pass_and_document(db, list(rows))
    for segment_id, row in rows.items():
        reason = seg.segment_liveness_reason(db, segment_id)
        if reason is not None:
            raise seg._as_http_error(seg.SegmentNotLive(segment_id, reason))
    left_alone: dict[str, str] = {}
    boxed: list[str] = []
    for segment_id, row in rows.items():
        outline = line_join.outline_of(row.anchor)
        if row.kind != "line":
            left_alone[segment_id] = NOT_A_LINE
        elif outline is None:
            left_alone[segment_id] = NO_OUTLINE
        else:
            boxed.append(segment_id)
    first = next(iter(rows.values()))
    document = db.get(Document, first.document_id)
    page = [row for row in db.query(Segment, pass_id=first.pass_id) if row.deleted_at is None]
    counted = seg._counting_readings(db, boxed[0]) if boxed else {}
    text = (counted.get("transcription") or next(iter(counted.values()), (None, "")))[1]
    direction, _level = _direction_of(
        rows[boxed[0]] if boxed else first, document, text, _lines_are_vertical(page, document), direction_rungs(db, document)
    )
    outlines = [line_join.outline_of(rows[sid].anchor) for sid in boxed]
    groups: list[list[str]] = []
    for group in line_join.rows([line_join.bounds(o) for o in outlines], direction):
        members = [boxed[i] for i in group]
        if len({rows[sid].parent_segment_id for sid in members}) > 1:
            left_alone.update({sid: OTHER_REGION for sid in members})
        else:
            groups.append(members)
    grouped = {sid for members in groups for sid in members}
    for sid in boxed:
        if sid not in grouped and sid not in left_alone:
            left_alone[sid] = ALONE
    return {
        "groups": groups,
        "left_alone": [{"segment_id": sid, "reason": left_alone[sid]} for sid in rows if sid in left_alone],
        "rows": rows,
    }


def _summary(plan: dict[str, Any]) -> str:
    joined = sum(len(group) for group in plan["groups"])
    alone = len(plan["left_alone"])
    if not joined:
        return "Nothing to join: no two of these lines share a row." + (f" {_plural(alone)} left alone." if alone else "")
    said = f"Joins {_plural(joined)} into {_plural(len(plan['groups']))}"
    return said + (f"; leaves {_plural(alone)} alone." if alone else ".")


@router.get("/document/{doc_id}/join-rows-preview")
def preview_join_rows(
    doc_id: str,
    segment_ids: list[str] = Query(..., min_length=1, description="The lines whose rows would be joined."),
    db: Database = Depends(get_library_database),
) -> dict[str, Any]:
    """What `segment.join_rows` would do to these lines, written nowhere."""
    plan = _plan(db, segment_ids)
    if any(row.document_id != doc_id for row in plan["rows"].values()):
        raise HTTPException(status_code=404, detail="a segment is not on this page")
    return {
        "groups": [{"kept_id": group[0], "segment_ids": group} for group in plan["groups"]],
        "left_alone": plan["left_alone"],
        "summary": _summary(plan),
    }


def _invert_join_rows(before, after, ctx: ActionContext):
    """Reads only `after`: each merge's own inverse, and the words the join made."""
    if not after or not after.get("merges"):
        return None
    unmerges = []
    for merge_after in after["merges"]:
        inverse = seg._invert_merge(None, merge_after, ctx)
        if inverse is None:
            return None
        unmerges.append(inverse[1])
    return ("segment.unjoin_rows", {"unmerges": unmerges, "word_versions": after.get("word_versions", {}),
                                    "representation_ids": after.get("word_representation_ids", [])})


@action("segment.join_rows", SegmentJoinRowsParams, domains=["segment"], undoable=True, invert=_invert_join_rows)
def _action_join_rows(db: Database, params: SegmentJoinRowsParams, ctx: ActionContext):
    missing = [sid for sid in params.segment_ids if sid not in params.expected_versions]
    if missing:
        raise HTTPException(status_code=422, detail=f"expected_versions is missing {missing}")
    plan = _plan(db, params.segment_ids)
    rows: dict[str, Segment] = plan["rows"]
    if not plan["groups"]:
        raise HTTPException(status_code=422, detail=_summary(plan))
    for sid, row in rows.items():
        if row.version != params.expected_versions[sid]:
            raise seg._as_http_error(seg.SegmentStale(
                sid, params.expected_versions[sid], row.version,
                seg._stale_changed_fields(db, sid, params.expected_versions[sid], row),
            ))
    joined: list[dict[str, Any]] = []
    merges: list[dict[str, Any]] = []
    word_versions: dict[str, int] = {}
    reading_ids: list[str] = []
    touched: list[str] = []
    for members in plan["groups"]:
        # What each part was, read before the merge changes the kept line.
        parts = []
        for sid in members:
            row = rows[sid]
            held = any(r.kind == "word" and r.parent_segment_id == sid and r.deleted_at is None
                       for r in db.query(Segment, pass_id=row.pass_id))
            counted = seg._counting_readings(db, sid)
            parts.append((sid, line_join.outline_of(row.anchor), None if held else counted))
        _result, merged = seg._action_merge(db, seg.SegmentMergeParams(
            segment_ids=members, keep_id=members[0], expected_versions={sid: params.expected_versions[sid] for sid in members},
            join_geometry=True, move_into_region=True,
        ), ctx)
        merges.append(merged.after)
        touched.extend(merged.target_ids)
        kept = db.get(Segment, members[0])
        word_ids = []
        for _sid, outline, counted in parts:
            if counted is None:
                continue
            x0, y0, x1, y1 = line_join.bounds(outline)
            word = seg._create_segment_impl(db, seg.SegmentCreateParams(
                document_id=kept.document_id, pass_id=kept.pass_id, kind="word", parent_segment_id=kept.id,
                anchor=SourceAnchor(document_id=kept.document_id, rect=[x0, y0, x1 - x0, y1 - y0], polygon=outline),
            ), ctx)
            word_ids.append(word.id)
            word_versions[word.id] = word.version
            touched.append(word.id)
            for kind, (_rid, text) in sorted(counted.items()):
                reading_ids.append(seg._derived_reading(
                    db, document_id=kept.document_id, segment_id=word.id, kind=kind, content=text, ctx=ctx))
        joined.append({"kept_id": members[0], "segment_ids": members, "word_ids": word_ids})
    first = next(iter(rows.values()))
    spec = ChangeSpec(
        domains=["segment"], target_ids=touched, before=None,
        after={"merges": merges, "word_versions": word_versions, "word_representation_ids": reading_ids,
               "versions": {sid: db.get(Segment, sid).version for sid in params.segment_ids}},
        emit_type="segment.merged", segment_ids=touched, pass_ids=[first.pass_id], document_ids=[first.document_id],
    )
    return {"joined": joined, "left_alone": plan["left_alone"]}, spec


class SegmentUnjoinRowsParams(BaseModel):
    """Internal: `segment.join_rows`'s inverse only -- every merge put back and the words it made removed, in one step."""

    model_config = ConfigDict(extra="forbid")

    unmerges: list[seg.SegmentUnmergeParams]
    word_versions: dict[str, int] = {}
    representation_ids: list[str] = []


@action("segment.unjoin_rows", SegmentUnjoinRowsParams, domains=["segment"], undoable=False)
def _action_unjoin_rows(db: Database, params: SegmentUnjoinRowsParams, ctx: ActionContext):
    audit_id = uuid.uuid4().hex
    touched: list[str] = []
    versions: dict[str, int] = {}
    pass_ids: set[str] = set()
    document_ids: set[str] = set()
    seg._retract_readings(db, params.representation_ids)
    now = utc_now()
    for word_id, expected in params.word_versions.items():
        row = db.get(Segment, word_id)
        if row is None or row.deleted_at is not None:
            raise seg._as_http_error(seg.SegmentPartGone(word_id))
        if row.version != expected:
            raise seg._as_http_error(seg.SegmentStale(word_id, expected, row.version, seg._stale_changed_fields(db, word_id, expected, row)))
        snapshot_segment_version(db, row, deleted=True, actor=ctx.actor, audit_id=audit_id)
        row.deleted_at, row.deleted_by = now, ctx.actor
        db.save(row)
        db.save(SegmentForwarding(
            document_id=row.document_id, old_segment_id=word_id, kind="deleted", new_segment_ids=[],
            actor=ctx.actor, audit_id=audit_id, sequence=db.next_forwarding_sequence(),
        ))
        touched.append(word_id)
        pass_ids.add(row.pass_id)
        document_ids.add(row.document_id)
    for unmerge in params.unmerges:
        _result, spec = seg._action_unmerge(db, unmerge, ctx)
        touched.extend(spec.target_ids)
        versions.update(spec.after["versions"])
        pass_ids.update(spec.pass_ids)
        document_ids.update(spec.document_ids)
    return {"segment_ids": touched}, ChangeSpec(
        audit_id=audit_id, domains=["segment"], target_ids=touched, before=None, after={"versions": versions},
        emit_type="segment.merged", segment_ids=touched, pass_ids=sorted(pass_ids), document_ids=sorted(document_ids),
    )
