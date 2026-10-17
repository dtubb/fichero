"""A split carries each line and its readings to the page it falls on (#5452).

Spec: `source.split.carries-readings-over`. Every split, the route's and the workflow's, calls
`carry_readings_over` once its halves exist. Each line of the spread, with every pass's readings, is
copied to the half its centre falls in, re-normalised to that half's region. A line that reaches past
its half is flagged (`metadata["crosses_gutter"]`) and clamped to the half, never cut in two. The
spread keeps its passes as history: nothing is moved, read again or paid for, and the halves have
passes of their own, so a recipe's "already done" sees the work.

A page's results that are not yet rows (a transcription's boxes in an artifact) are converted first,
the same conversion an edit makes, so the carry sees one kind of record. Regions above the lines
(kind `region`), word segments, and the spread's artifacts are not carried: the halves hold the
pass, its lines and their readings.
"""
from __future__ import annotations

import uuid
from typing import Any

from fichero_server.core.timeutil import utc_now
from fichero_server.models import (
    ContentRepresentation,
    ContentRepresentationRevision,
    Document,
    ReadingChoice,
    Segment,
    SegmentPass,
    SegmentPassChoice,
)
from fichero_server.models.anchors import SourceAnchor
from fichero_server.models.reading_orders import ReadingOrder, ReadingOrderEntry
from fichero_server.models.segments import bbox_and_tile_from_anchor

_TOLERANCE = 1e-6
#: The kind of segment that is a line; the spec carries "each line segment".
LINE = "line"


def _bounds(anchor: SourceAnchor) -> tuple[float, float, float, float]:
    """(x0, y0, x1, y1) of the anchor's outline, or its box."""
    if anchor.polygon:
        xs, ys = [p[0] for p in anchor.polygon], [p[1] for p in anchor.polygon]
        return min(xs), min(ys), max(xs), max(ys)
    if anchor.rect is None:
        raise ValueError(f"segment anchor on {anchor.document_id} has neither a polygon nor a box to place")
    x, y, w, h = anchor.rect
    return x, y, x + w, y + h


def _half_for(bounds: tuple[float, float, float, float], regions: dict[str, list[float]]) -> str | None:
    """The child whose region holds the centre of the bounds; None when none does."""
    cx, cy = (bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2
    for child_id, (x, y, w, h) in regions.items():
        if x <= cx <= x + w and y <= cy <= y + h:
            return child_id
    return None


def _renormalised(point: list[float], region: list[float]) -> list[float]:
    x, y, w, h = region
    return [min(1.0, max(0.0, (point[0] - x) / w)), min(1.0, max(0.0, (point[1] - y) / h))]


def _anchor_in(anchor: SourceAnchor, region: list[float], child_id: str) -> SourceAnchor:
    """The anchor as a fraction of the half: its box, its outline and its shapes' points."""
    rect = None
    if anchor.rect is not None and not anchor.shapes:
        (x0, y0), (x1, y1) = (_renormalised([anchor.rect[0], anchor.rect[1]], region),
                              _renormalised([anchor.rect[0] + anchor.rect[2], anchor.rect[1] + anchor.rect[3]], region))
        rect = [x0, y0, x1 - x0, y1 - y0]
    update: dict[str, Any] = {
        "document_id": child_id, "page_id": None, "rect": rect,
        "polygon": [_renormalised(p, region) for p in anchor.polygon] if anchor.polygon else None,
        "shapes": [s.model_copy(update={"points": [_renormalised(p, region) for p in s.points]}) if s.points else s
                   for s in anchor.shapes] if anchor.shapes else None,
    }
    return SourceAnchor.model_validate({**anchor.model_dump(), **update})


def _convert_results(db: Any, parent_id: str) -> None:
    """The spread's results with boxes that are not rows yet, made into passes (the conversion an edit makes)."""
    from fichero_server.api.routes.document.segment_conversion import (
        _artifacts_to_convert,
        _convert_one,
    )

    for artifact in _artifacts_to_convert(db, parent_id):
        _convert_one(db, artifact)


def carry_readings_over(db: Any, parent: Document, children: list[Document]) -> dict[str, Any]:
    """Carry the spread's lines and their readings to `children`. Returns what was done:
    `{"passes": n, "lines": n, "crossing": n, "unplaced": [segment ids], "no_region": [child ids]}`."""
    report: dict[str, Any] = {"passes": 0, "lines": 0, "crossing": 0, "unplaced": [], "no_region": []}
    regions: dict[str, list[float]] = {}
    for child in children:
        if child.region_in_parent is None:
            report["no_region"].append(child.id)
        else:
            regions[child.id] = list(child.region_in_parent.rect)
    if not regions:
        return report
    _convert_results(db, parent.id)
    now = utc_now()
    new_pass: dict[tuple[str, str], str] = {}  # (old pass id, child id) -> the half's pass
    new_segment: dict[str, dict[str, Segment]] = {}  # old segment id -> {child id: its copy}
    for pass_row in [p for p in db.query(SegmentPass, document_id=parent.id) if p.deleted_at is None]:
        for segment in [s for s in db.query(Segment, pass_id=pass_row.id) if s.deleted_at is None and s.kind == LINE]:
            if segment.anchor.rendition_id is not None:
                raise ValueError(
                    f"line {segment.id} is measured on rendition {segment.anchor.rendition_id}, not on the "
                    "page's own frame, so its place in a half cannot be worked out from the split's regions")
            bounds = _bounds(segment.anchor)
            child_id = _half_for(bounds, regions)
            if child_id is None:
                report["unplaced"].append(segment.id)
                continue
            region = regions[child_id]
            if (key := (pass_row.id, child_id)) not in new_pass:
                twin = pass_row.model_copy(update={"id": uuid.uuid4().hex, "document_id": child_id, "created_at": now})
                db.save(twin)
                new_pass[key] = twin.id
                report["passes"] += 1
            anchor = _anchor_in(segment.anchor, region, child_id)
            crossing = (bounds[0] < region[0] - _TOLERANCE or bounds[1] < region[1] - _TOLERANCE
                        or bounds[2] > region[0] + region[2] + _TOLERANCE
                        or bounds[3] > region[1] + region[3] + _TOLERANCE)
            bbox_x, bbox_y, bbox_w, bbox_h, tile = bbox_and_tile_from_anchor(anchor)
            twin_segment = segment.model_copy(update={
                "id": uuid.uuid4().hex, "document_id": child_id, "pass_id": new_pass[key],
                "parent_segment_id": None, "anchor": anchor,
                "baseline": [_renormalised(p, region) for p in segment.baseline] if segment.baseline else None,
                "bbox_x": bbox_x, "bbox_y": bbox_y, "bbox_w": bbox_w, "bbox_h": bbox_h, "tile": tile,
                "doc_kind": f"{child_id}:{segment.kind}", "version": 1, "created_at": now, "updated_at": now,
                "metadata": {**segment.metadata, "carried_from_segment_id": segment.id,
                             **({"crosses_gutter": True} if crossing else {})},
            })
            db.save(twin_segment)
            new_segment.setdefault(segment.id, {})[child_id] = twin_segment
            report["lines"] += 1
            report["crossing"] += crossing
    _carry_readings(db, new_segment, now)
    _carry_orders(db, new_pass, new_segment)
    for (old_pass_id, child_id), pass_id in new_pass.items():
        for choice in db.query(SegmentPassChoice, pass_id=old_pass_id):
            if choice.superseded_at is None:
                db.save(choice.model_copy(update={"id": uuid.uuid4().hex, "document_id": child_id, "pass_id": pass_id}))
    return report


def _carry_readings(db: Any, new_segment: dict[str, dict[str, Segment]], now: Any) -> None:
    """Every reading of a carried line, its revisions, and the person's choice among them."""
    for old_id, twins in new_segment.items():
        for child_id, segment in twins.items():
            copied: dict[str, str] = {}
            for reading in db.query(ContentRepresentation, segment_id=old_id):
                old = reading.source_anchor
                anchor = segment.anchor.model_copy(update={
                    "segment_id": segment.id, "char_start": old.char_start, "char_end": old.char_end})
                twin = reading.model_copy(update={
                    "id": uuid.uuid4().hex, "document_id": child_id, "segment_id": segment.id,
                    "source_anchor": anchor, "created_at": now})
                db.save(twin)
                copied[reading.id] = twin.id
                for revision in db.query(ContentRepresentationRevision, representation_id=reading.id):
                    db.save(revision.model_copy(update={"id": uuid.uuid4().hex, "representation_id": twin.id}))
            for choice in db.query(ReadingChoice, segment_id=old_id):
                if choice.superseded_at is None and choice.representation_id in copied:
                    db.save(choice.model_copy(update={
                        "id": uuid.uuid4().hex, "document_id": child_id, "segment_id": segment.id,
                        "representation_id": copied[choice.representation_id]}))


def _carry_orders(db: Any, new_pass: dict[tuple[str, str], str], new_segment: dict[str, dict[str, Segment]]) -> None:
    """Each live reading order of a carried pass, over the lines that went to the half, in the same order."""
    for (old_pass_id, child_id), pass_id in new_pass.items():
        for order in [o for o in db.query(ReadingOrder, pass_id=old_pass_id) if o.deleted_at is None]:
            twin = order.model_copy(update={"id": uuid.uuid4().hex, "document_id": child_id, "pass_id": pass_id})
            db.save(twin)
            db.save_many([
                entry.model_copy(update={"id": uuid.uuid4().hex, "order_id": twin.id,
                                         "segment_id": new_segment[entry.segment_id][child_id].id,
                                         "parent_entry_id": None})
                for entry in db.query(ReadingOrderEntry, order_id=order.id)
                if child_id in new_segment.get(entry.segment_id, {})
            ])
