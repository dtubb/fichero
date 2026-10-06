"""One line pass per page, read many times (`source.model.one-line-pass`, #5487, ruled 2026-10-05, #5467).

A page has one canonical set of lines: those of its working pass (`segment_readings.working_pass`, the one
ranking every surface reads). Finding lines makes that pass; every reader afterwards (a Kraken reader, a
vision model reading line by line, the page text tied to the lines, #5444) reads THOSE lines and adds its
words to them as readings (`representation.create`), never as a second pass of the same lines. Which reading
of a line counts is the counting rule's (`models.readings.resolve_counting`), not this module's: a later
machine reading is the newest, and a person's reading still outranks every machine's.

Here: the working pass's lines (`working_lines`), their outline and baseline in an image's pixels
(`in_pixels`, `as_geometry`, what a reader is handed), and the readings written onto them
(`write_readings`), all through the audited action layer under the run that read them.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Kept on a reading's page artifact (`Artifact.data`): the pass whose lines the reading was written onto.
#: Its text is the lines' text joined, so it is never itself a page reading to tie to the lines (#5444).
READ_ONTO_PASS = "read_onto_pass"
#: Where a line with no baseline of its own (Apple Vision's boxes give none) is read along: this far down its
#: box, the usual place of a baseline in a line's box.
BASELINE_AT = 0.75


@dataclass(frozen=True)
class WorkingLines:
    """The page's working pass and its live lines, in the pass's reading order."""

    pass_row: Any
    lines: list[Any]


def working_lines(db: Any, document_id: str, *, model: str | None = None) -> WorkingLines | None:
    """The lines a reader reads: the first pass, in the page's working-pass ranking (`ranked_passes`), that
    has shapes on the image and live stored lines. `model` keeps only passes of that model. None when the
    page has no lines yet (the caller finds them first). A result not yet made a pass is not offered: every
    new result becomes a pass as it is saved (`convert_new_results`)."""
    from fichero_server.api.routes.document.segment_readings import (
        is_unconverted_pass,
        ordered_lines,
        passes_with_shapes,
        ranked_passes,
    )
    from fichero_server.models.segments import SegmentPass

    shaped = passes_with_shapes(db, document_id)
    for answer in ranked_passes(db, document_id):
        if answer.pass_id is None or answer.pass_id not in shaped or is_unconverted_pass(answer.pass_id):
            continue
        row = db.get(SegmentPass, answer.pass_id)
        if row is None or row.deleted_at is not None or (model is not None and row.model != model):
            continue
        lines = ordered_lines(db, row.id)
        if lines:
            return WorkingLines(row, lines)
    return None


def _scale(points: list[list[float]] | None, width: float, height: float) -> list[list[float]]:
    return [[float(x) * width, float(y) * height] for x, y in (points or [])]


def in_pixels(row: Any, width: float, height: float) -> dict[str, Any]:
    """One line as a reader takes it: `{"id", "polygon", "baseline"}` in the pixels of a `width` x `height`
    image of the page (the stored shapes are fractions of the page). A line drawn as a box gets the box's
    corners as its outline; one with no baseline is read along `BASELINE_AT` of its box."""
    anchor = row.anchor
    polygon = anchor.polygon
    rect = anchor.rect or [row.bbox_x, row.bbox_y, row.bbox_w, row.bbox_h]
    x, y, w, h = (float(v) for v in rect)
    if not polygon or len(polygon) < 3:
        polygon = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
    baseline = row.baseline if row.baseline and len(row.baseline) >= 2 else [
        [x, y + h * BASELINE_AT], [x + w, y + h * BASELINE_AT]]
    return {"id": row.id, "polygon": _scale(polygon, width, height), "baseline": _scale(baseline, width, height)}


def as_geometry(found: WorkingLines, width: float, height: float, *, provider: str, model: str) -> Any:
    """The lines as the shared geometry a line reader reads (`line_reader.read_lines`): one LINE box per
    line, its outline and baseline in pixels, and the segment it is (`segment_id`) so each reading comes
    back to its own line."""
    from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryLevel, OCRGeometryResult

    boxes = []
    for row in found.lines:
        line = in_pixels(row, width, height)
        boxes.append(OCRGeometryBox(
            text="", bbox=[row.bbox_x, row.bbox_y, row.bbox_w, row.bbox_h], level=OCRGeometryLevel.LINE,
            provider=provider, model=model, source="working-pass",
            metadata={"segment_id": row.id, "polygon_px": line["polygon"], "baseline_px": line["baseline"],
                      "pixel_frame": {"width": width, "height": height}}))
    return OCRGeometryResult(text="", provider=provider, model=model, boxes=boxes, source="working-pass",
                             metadata={"pixel_frame": {"width": width, "height": height},
                                       READ_ONTO_PASS: found.pass_row.id})


def write_readings(
    db: Any,
    *,
    document_id: str,
    readings: list[tuple[str, str]],
    artifact_id: str | None,
    run_id: str,
    actor: str = "system",
    kind: str = "transcription",
    library_path: str | None = None,
) -> list[str]:
    """Each `(segment_id, text)` written as a reading of that line (`representation.create`), derived from
    the reader's page artifact (whose provider and model say who read it), under `run_id`: a machine's
    reading, `workflow`, never a person's. An empty text writes nothing: a line read as nothing has not
    been given words. Returns the readings' ids."""
    import fichero_server.api.routes.document.content_representations  # noqa: F401  (representation.create)
    from fichero_server.actions.registry import ActionContext, registry

    ctx = ActionContext(actor=actor, run_id=run_id, library_path=library_path, is_bootstrap=True)
    made = []
    for segment_id, text in readings:
        if not (text or "").strip():
            continue
        made.append(registry.invoke(db, "representation.create", {
            "document_id": document_id, "segment_id": segment_id, "kind": kind, "content": text.strip(),
            "derived_from_artifact_id": artifact_id}, ctx).result["id"])
    return made
