"""One line pass per page, read many times (`source.model.one-line-pass`, #5487, ruled 2026-10-05, #5467).

A page has one canonical set of lines: those of its working pass (`segment_readings.working_pass`, the one
ranking every surface reads). Finding lines makes that pass; every reader afterwards (a Kraken reader, a
vision model reading line by line, the page text tied to the lines, #5444) reads THOSE lines and adds its
words to them as readings (`representation.create`), never as a second pass of the same lines. Which reading
of a line counts is the counting rule's (`models.readings.resolve_counting`), not this module's: among
machine readings a checked one, then the better reader measured on the project, then the newest (#5558),
and a person's reading still outranks every machine's.

Here: the working pass's lines (`working_lines`), their outline and baseline in an image's pixels
(`in_pixels`, `as_geometry`, what a reader is handed), and the readings written onto them
(`write_readings`), all through the audited action layer under the run that read them.
"""
from __future__ import annotations

import re

from dataclasses import dataclass
from typing import Any

#: Kept on a reading's page artifact (`Artifact.data`): the pass whose lines the reading was written onto.
#: Its text is the lines' text joined, so it is never itself a page reading to tie to the lines (#5444).
READ_ONTO_PASS = "read_onto_pass"
#: The result's list of the lines a reader looked at and found no writing on (a ruled or blank line), and the
#: mark it leaves on each segment so a second Start does not read it again (#5758).
NO_WRITING_KEY = "lines_looked_no_writing"
NO_WRITING_MARK = "read_no_writing"
#: Where a line with no baseline of its own (Apple Vision's boxes give none) is read along: this far down its
#: box, the usual place of a baseline in a line's box.
BASELINE_AT = 0.75
#: A page read mostly empty (`source.read.line-with-no-writing-is-read`): of at least this many lines, more than half.
MOSTLY_EMPTY_MIN_LINES = 5


def reads_mostly_nothing(empty: int, found: int) -> bool:
    """Whether a Kraken reader failed a page: it gave no text for every line, or, on a page of at least
    `MOSTLY_EMPTY_MIN_LINES`, for more than half. Such a page's empty lines are not 'no writing' (a hand it cannot
    read is not a blank page); they stay unread so a second Start or another reader takes them."""
    return found > 0 and (empty == found or (found >= MOSTLY_EMPTY_MIN_LINES and empty * 2 > found))


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
    readings: list[tuple[str | None, str] | tuple[str | None, str, float | None]],
    artifact_id: str | None,
    run_id: str | None,
    actor: str = "system",
    kind: str = "transcription",
    level: str | None = None,
    library_path: str | None = None,
    derived_from: dict[str | None, str] | None = None,
) -> list[str]:
    """Each `(segment_id, text)` written as a reading of that line (`representation.create`), derived from
    the reader's page artifact (whose provider and model say who read it), under `run_id`: a machine's
    reading, `workflow`, never a person's. A segment id of None is a reading of the node itself (a
    translation of a page with no lines, a folder's description, #5599). An empty text writes nothing: a
    line read as nothing has not been given words. `level` is the level the reader read at
    (`source.reading.levels`): a reader that expands abbreviations writes `expanded`, which counts beside
    the line as written, never over it; unset, no level is recorded, as before. `derived_from` names, per segment,
the reading a new one was made from (a correction names the reading it corrects, `correct`). A reading's third
value, where given, is the reader's certainty about it (`machine_confidence`, #5694). Returns the readings' ids."""
    import fichero_server.api.routes.document.content_representations  # noqa: F401  (representation.create)
    from fichero_server.actions.registry import ActionContext, registry

    ctx = ActionContext(actor=actor, run_id=run_id, library_path=library_path, is_bootstrap=True)
    from fichero_server.models import ContentRepresentation

    # A reading this result already wrote on the line is not written again (#5707: one stored twice, 40 ms apart).
    have = {(r.segment_id, r.kind, r.content, r.derived_from_artifact_id, r.level)
            for r in db.query(ContentRepresentation, document_id=document_id)
            if artifact_id and r.derived_from_artifact_id == artifact_id and not r.retracted_at}
    made = []
    for segment_id, text, *certainty in readings:
        if not (text or "").strip():
            continue
        if (segment_id, kind, text.strip(), artifact_id, level) in have:
            continue
        made.append(registry.invoke(db, "representation.create", {
            "document_id": document_id, "segment_id": segment_id, "kind": kind, "content": text.strip(),
            "derived_from_artifact_id": artifact_id, "level": level,
            "machine_confidence": certainty[0] if certainty else None,
            "derived_from_representation_id": (derived_from or {}).get(segment_id)}, ctx).result["id"])
    return made


def mark_no_writing(db: Any, segment_ids: list[str], *, model: str | None, run_id: str | None = None,
                    library_path: str | None = None) -> None:
    """Record 'looked, no writing' on each line, by the model that looked, through `segment.update` (versioned and
    audited): the line counts as read for that reader and a different one looks again (#5758)."""
    import fichero_server.api.routes.document.segments  # noqa: F401  (segment.update)
    from fichero_server.actions.registry import ActionContext, registry
    from fichero_server.models.segments import Segment

    ctx = ActionContext(actor="system", run_id=run_id, library_path=library_path, is_bootstrap=True)
    for segment_id in segment_ids:
        segment = db.get(Segment, segment_id)
        if segment is None or segment.deleted_at is not None or (segment.metadata or {}).get(NO_WRITING_MARK) == {
                "model": model or ""}:
            continue
        registry.invoke(db, "segment.update", {"segment_id": segment_id, "expected_version": segment.version,
                                                "no_writing_model": model or ""}, ctx)


def mark_unread_reasons(db: Any, reasons: dict[str, str], *, run_id: str | None = None,
                        library_path: str | None = None) -> None:
    """Say on each line why a model left it without a reading (a refusal, or an answer that was not a reading), through
    `segment.update` (versioned and audited). The line stays unread; its reason replaces "no reader has answered for
    it" (#5894, `source.recipe.kraken-lines-cloud-reads`)."""
    import fichero_server.api.routes.document.segments  # noqa: F401  (segment.update)
    from fichero_server.actions.registry import ActionContext, registry
    from fichero_server.models.segments import Segment

    ctx = ActionContext(actor="system", run_id=run_id, library_path=library_path, is_bootstrap=True)
    for segment_id, reason in reasons.items():
        segment = db.get(Segment, segment_id)
        if segment is None or segment.deleted_at is not None or (segment.metadata or {}).get("unread_reason") == reason:
            continue
        registry.invoke(db, "segment.update", {"segment_id": segment_id, "expected_version": segment.version,
                                                "unread_reason": reason}, ctx)


class _Lines(list):
    """The shown rows regrouped by line, with the lines that hold a person's word (left as the person read them)."""
    people: set[str]


def _as_lines(db: Any, shown: list[tuple[str, str | None, str]], answer: list[str]) -> _Lines | None:
    """When the page's words were listed by their lines (`tool_context._grouped_into_lines`) and the answer names those
    lines, the rows as lines: (line id, None, the words' text joined). A line's correction is then a reading of the
    line, derived from no word's reading, and the words keep theirs. None otherwise."""
    from fichero_server.models import ContentRepresentation, Segment
    from fichero_server.tool_context import line_of_word

    words = {row.id: row for row in db.query_in(Segment, "id", [sid for sid, _, _ in shown])}
    parents = {row.id: row for row in db.query_in(
        Segment, "id", [w.parent_segment_id for w in words.values() if w.parent_segment_id])}
    lines = {sid: line_of_word(words.get(sid), parents) for sid, _, _ in shown}
    if not shown or any(line is None for line in lines.values()):
        return None
    named = {answer_line(a)[0] for a in answer}
    if not named & {line.id for line in lines.values()}:
        return None
    by_line: dict[str, list[str]] = {}
    for sid, _rid, text in shown:
        by_line.setdefault(lines[sid].id, []).append(text)
    out = _Lines((line_id, None, " ".join(texts)) for line_id, texts in by_line.items())
    reps = db.query_in(ContentRepresentation, "id", [rid for _, rid, _ in shown if rid])
    out.people = {lines[r.segment_id].id for r in reps
                  if getattr(r.provenance_kind, "value", r.provenance_kind) == "human" and r.segment_id in lines}
    return out


#: What a correcting step's per-page result says when its text cannot be put onto the page's lines.
NOT_TIED = "not tied to lines"
#: The flag a review gives each line (`source.job.review-is-segment-native`).
LINE_FLAGS = ("certain", "uncertain", "unreadable")
#: Where a line's short note starts: ` | note: ...` at its end (#5724).
_BOX = re.compile(r"^-?[\d.]+(\s+-?[\d.]+){3}$")
_NOTE = re.compile(r"\s*\|\s*note:\s*(.*)$", re.IGNORECASE)


def answer_line(line: str) -> tuple[str, str, str, str]:
    """(segment id, flag or '', text, note or '') of one answer line, `<id> | [<flag> |] <text> [| note: <note>]`.
    Only the leading id and flag are split off, so a `|` or `||` in diplomatic text stays in the text, and a
    note is only what follows `| note:`, so a dropped flag never makes the note the text (#5724)."""
    head, bar, rest = line.partition("|")
    if not bar:
        return line.strip(), "", "", ""
    flag, bar, tail = rest.partition("|")
    flag = flag.strip().lower()
    if not bar and flag in LINE_FLAGS:  # a bare `<id> | unreadable`: a flag with no text, never the text (#5724)
        return head.strip(), flag, "", ""
    text = tail if bar and flag in LINE_FLAGS else rest
    if bar and _BOX.match(flag):  # the lines echoed as shown, `id | x y w h | maker | [confidence |] text`
        text = rest.rpartition("|")[2]
    note = _NOTE.search(text)
    return (head.strip(), flag if text is tail and bar else "", (text[:note.start()] if note else text).strip(),
            note.group(1).strip() if note else "")


def correct_lines(
    db: Any,
    *,
    document_id: str,
    text: str,
    artifact_id: str,
    run_id: str | None,
    level: str = "as_written",
    library_path: str | None = None,
) -> tuple[list[str], str]:
    """A correcting step's text (the paleographer's review, `correct`, #5654) put onto the page's lines.

    The step was shown the page's lines in reading order (`tool_context`: one line per segment, `id | box |
    maker | text`). Its answer is matched back to them: by segment id when every line it gave starts with
    one, else line for line when it gave as many lines as it was shown. Each line whose text it changed
    gets a reading of the answer (`write_readings`: a transcription at `level`, derived from the step's
    artifact, whose model made it, and from the line's counting reading, which it corrects). A line it left
    unchanged gets nothing; a line whose counting reading is a person's gets nothing (a run never writes
    over a person). An answer that cannot be matched writes nothing and says why, starting `NOT_TIED`: the
    artifact stays the step's only output, never guessed onto the lines. Returns (readings made, what was
    done, in words). The page's text cache follows from the readings (`actions/page_text_cache.py`)."""
    from fichero_server.api.routes.document.segment_readings import document_text
    from fichero_server.models import ContentRepresentation

    if any(r.derived_from_artifact_id == artifact_id
           for r in db.query(ContentRepresentation, document_id=document_id)):
        return [], "already on the lines"
    derived = document_text(db, document_id, include_furniture=True)
    shown = [(s.segment_id, s.representation_id, derived.text[s.start:s.end]) for s in derived.spans
             if s.representation_id]
    if not shown:
        return [], f"{NOT_TIED}: the page has no read lines; kept as the page's review"
    answer = [line.strip() for line in (text or "").splitlines() if line.strip()]
    grouped = _as_lines(db, shown, answer)
    if grouped is not None:  # the words were listed by their lines: a correction is a reading of the line (#5648)
        shown = grouped
    ids = {segment_id for segment_id, _, _ in shown}
    by_id: dict[str, str] = {}
    unreadable: set[str] = set()
    uncertain: set[str] = set()
    for line in answer:
        segment_id, flag, said_text, _note = answer_line(line)
        if segment_id in ids and "|" in line:
            by_id[segment_id] = said_text
            if flag == "unreadable":
                unreadable.add(segment_id)
            elif flag == "uncertain":
                uncertain.add(segment_id)
    if answer and len(by_id) == len(answer):
        corrected = dict(by_id)
    elif len(answer) == len(shown):
        corrected = {segment_id: new for (segment_id, _, _), new in zip(shown, answer)}
    else:
        return [], (f"{NOT_TIED}: the review gave {len(answer)} line(s) for the page's {len(shown)}; "
                    "kept as the page's review")
    counting = {r.id: r for r in db.query_in(ContentRepresentation, "id", [rid for _, rid, _ in shown if rid])}
    people_lines = getattr(grouped, "people", set()) if grouped is not None else set()
    readings, derived_from, people = [], {}, 0
    for segment_id, representation_id, old in shown:
        new = corrected.get(segment_id)
        if not new or segment_id in unreadable or " ".join(new.split()) == " ".join(old.split()):
            continue
        if representation_id is None and segment_id in people_lines:
            people += 1
            continue
        kind = getattr(counting.get(representation_id), "provenance_kind", None)
        if getattr(kind, "value", kind) == "human":
            people += 1
            continue
        # an uncertain correction is no surer than the reading it corrects (#5694)
        sure = getattr(counting.get(representation_id), "machine_confidence", None) if segment_id in uncertain else None
        readings.append((segment_id, new, sure))
        derived_from[segment_id] = representation_id
    made = write_readings(db, document_id=document_id, readings=readings, artifact_id=artifact_id,
                          run_id=run_id, level=level, library_path=library_path, derived_from=derived_from)
    said = f"{len(made)} of {len(shown)} line(s) corrected"
    said += f"; {len(unreadable)} line(s) flagged unreadable, left as read" if unreadable else ""
    return made, said + (f"; {people} line(s) a person read kept" if people else "")
