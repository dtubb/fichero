"""What a tool is given besides the picture: some segments, as compact lines (#5026, ruled 2026-09-26).

`source.tool.scope-is-a-segment-selection`: a tool is given a SET OF SEGMENTS -- a page, a region, a
line -- never a size word; a region brings the lines inside it. `source.tool.text-follows-the-working-pass`:
the text is what the page's derived text says (`document_text`: the working pass, each line's
counting reading, in reading order), so this never answers "which reading counts" a second way.
Each line is marked by its maker. `source.tool.budget-reports-itself` (its first half): the
statement says how much is sent, and a page with nothing to send says so -- the tool then works
from the picture alone.

One line per segment: `<segment id> | x y w h | maker | text`, the box as fractions of the page.
The id is the real one, so an answer can name the segments it read.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: How a reading's `provenance_kind` is written in a line. A person's line outranks a machine's
#: (the trust order the ruling settled); the mark lets the model see which is which. Read from the
#: SERVER-SET `provenance_kind`, never `created_by`: a reading written in a run carries the name of
#: the person who started the run there, which would pass a machine's line off as a person's
#: (#4868/#4869). A row that recorded nothing is never called a person's.
MAKER = {
    "human": "person",
    "agent": "agent",
    "workflow": "machine",
    "external_import": "file",
}


@dataclass
class ToolContext:
    text: str
    segment_ids: list[str] = field(default_factory=list)
    characters: int = 0
    pass_id: str | None = None
    statement: str = ""
    #: True when the page has no segments and `text` is its text as one block, with no boxes.
    plain: bool = False
    #: A second review that settles (`review_mode` both, #6257): the first review's version of each line it changed.
    first_review: dict[str, str] = field(default_factory=dict)


def _maker(reading: Any) -> str:
    kind = getattr(reading, "provenance_kind", None)
    kind = getattr(kind, "value", kind)
    if kind in MAKER:
        return MAKER[kind]
    return "machine" if (getattr(reading, "producer_tool", None) or getattr(reading, "producer_model", None)) else "unrecorded"


def line_of_word(row: Any, shapes: dict[str, Any]) -> Any:
    """The line a word sits in (its parent, a line), or None (#5648)."""
    parent = shapes.get(getattr(row, "parent_segment_id", None) or "")
    return parent if getattr(row, "kind", None) == "word" and getattr(parent, "kind", None) == "line" else None


def _grouped_into_lines(rows: list[tuple[str, Any, Any, str]], shapes: dict[str, Any]) -> list[tuple[str, Any, Any, str]]:
    """A page read as words that sit in lines, listed one row per line, the line's words joined in order (ruled
    2026-10-17, #5648): 656 word rows become the page's ~40 lines. Rows that are not all such words stay as they are."""
    if not rows or not all(line_of_word(row, shapes) is not None for _id, row, _r, _t in rows):
        return rows
    grouped: dict[str, list] = {}
    for _id, row, reading, text in rows:
        line = line_of_word(row, shapes)
        entry = grouped.setdefault(line.id, [line.id, line, reading, []])
        entry[3].append(text)
    return [(line_id, line, reading, " ".join(texts)) for line_id, line, reading, texts in grouped.values()]


#: How a second Review the reading model takes the first's work (#6257, owner 2026-10-29): `in-turn` reviews the first's
#: result (what a page's reading is once the first review is on it); `compare` reviews the reading the first review
#: started from, on its own; `both` is given that reading and the first review's version of it, reviews it itself and settles the two.
IN_TURN, COMPARE, BOTH = "in-turn", "compare", "both"
REVIEW_MODES = (IN_TURN, COMPARE, BOTH)


def reading_before_reviews(db: Any, reading: Any) -> Any:
    """The reading a line had before any review changed it: a review's correction names the reading it corrects
    (`derived_from_representation_id`), so walk back while the reading came from a review's artifact. The reading
    itself when no review made it, or when the trail is broken (never a guess)."""
    from fichero_server.models import Artifact, ContentRepresentation

    current, seen = reading, set()
    while current is not None and current.id not in seen:
        seen.add(current.id)
        artifact = db.get(Artifact, current.derived_from_artifact_id) if current.derived_from_artifact_id else None
        if artifact is None or artifact.artifact_type != "transcription_review":
            return current
        parent = db.get(ContentRepresentation, current.derived_from_representation_id) \
            if current.derived_from_representation_id else None
        if parent is None:
            return reading
        current = parent
    return reading


def tool_context(db: Any, document_id: str, segment_ids: list[str] | None = None, *,
                 confidence: bool = False, review_mode: str = IN_TURN) -> ToolContext:
    """The compact lines for `segment_ids` on one page (None: the whole page). With `confidence`, each line
    also states the machine's certainty about its reading (`-` when none was stated), after the maker. With a
    `review_mode` other than in-turn, a line a review changed is shown as it was before (`reading_before_reviews`)."""
    if review_mode not in REVIEW_MODES:
        raise ValueError(f"a review's mode is {', '.join(REVIEW_MODES)}; not {review_mode!r}")
    from fichero_server.api.routes.document.segment_readings import document_text
    from fichero_server.models import ContentRepresentation, Segment

    derived = document_text(db, document_id, include_furniture=True)
    shapes = {row.id: row for row in db.query(Segment, document_id=document_id)}
    wanted = set(segment_ids) if segment_ids is not None else None

    def in_scope(segment_id: str) -> bool:
        seen: set[str] = set()
        while segment_id and segment_id not in seen:
            if segment_id in wanted:
                return True
            seen.add(segment_id)
            row = shapes.get(segment_id)
            segment_id = row.parent_segment_id if row else None
        return False

    readings = {
        r.id: r for r in db.query_in(
            ContentRepresentation, "id", [s.representation_id for s in derived.spans if s.representation_id]
        )
    }
    rows: list[tuple[str, Any, Any, str]] = []  # (segment id, its row, its reading, its text)
    first_review: dict[str, str] = {}
    for span in derived.spans:
        if span.representation_id is None or (wanted is not None and not in_scope(span.segment_id)):
            continue
        reading, text = readings.get(span.representation_id), derived.text[span.start:span.end].replace("\n", " ")
        before = reading_before_reviews(db, reading) if review_mode != IN_TURN else reading
        if before is not reading and before is not None and before.content.strip() != text.strip():
            first_review[span.segment_id] = text
            reading, text = before, before.content.replace("\n", " ")
        rows.append((span.segment_id, shapes.get(span.segment_id), reading, text))
    rows = _grouped_into_lines(rows, shapes)
    lines, ids = [], []
    for segment_id, row, reading, text in rows:
        box = " ".join(f"{v:.3f}" for v in (row.bbox_x, row.bbox_y, row.bbox_w, row.bbox_h)) if row else "- - - -"
        sure = getattr(reading, "machine_confidence", None)
        shown = f" | {'-' if sure is None else f'{sure:.2f}'}" if confidence else ""
        lines.append(f"{segment_id} | {box} | {_maker(reading)}{shown} | {text}")
        ids.append(segment_id)
    if not lines and wanted is None:
        block, came_from = _text_without_segments(db, document_id)
        if block:
            return ToolContext(
                text=block, characters=len(block), plain=True,
                statement=f"no segments on the page: its text as one block, {len(block)} characters, from {came_from}",
            )
    characters = sum(len(line) for line in lines)
    where = "the page" if wanted is None else f"{len(wanted)} selected segment(s)"
    statement = (
        f"{len(lines)} line(s) of {where}, {characters} characters, from pass {derived.pass_id} in reading order"
        if lines else f"no reading on {where} yet: the tool works from the picture alone"
    )
    return ToolContext(text="\n".join(lines), segment_ids=ids, characters=characters, pass_id=derived.pass_id,
                       statement=statement, first_review=first_review if review_mode == BOTH else {})


def _text_without_segments(db: Any, document_id: str) -> tuple[str, str]:
    """A page with no segments still has text a tool should see: its page text, else its newest
    transcription (a Transcribe run writes an artifact and no segments). What the old
    `_existing_transcription_context` sent, so a review of such a page keeps its draft."""
    from fichero_server.models import Artifact, Document

    page = db.get(Document, document_id)
    if page is not None and (page.page_content or "").strip():
        return page.page_content, "the page text"
    transcriptions = [
        a for a in db.query(Artifact, document_id=document_id)
        if (a.artifact_type or "").startswith("transcription") and (a.content or "").strip()
    ]
    if transcriptions:
        newest = max(transcriptions, key=lambda a: a.created_at)
        return newest.content, f"its newest {newest.artifact_type} ({newest.id})"
    return "", ""


def as_prompt_context(context: ToolContext, *, confidence: bool = False) -> str:
    """The context as the model reads it: what it is, then the lines."""
    if context.plain:
        return f"The page's existing text ({context.statement}):\n{context.text}"
    if not context.segment_ids:
        return f"This page has {context.statement}."
    settle = ""
    if context.first_review:
        settle = (
            "\n\nAnother reviewer already changed these lines (id | its version). Review the reading above yourself, "
            "then settle each of these between your version and theirs: answer with the one you judge right, and mark "
            "the line `uncertain` when you cannot settle it, so a person can look:\n"
            + "\n".join(f"{i} | {t}" for i, t in context.first_review.items()))
    return (
        "The page's existing reading, one line per segment: id | x y w h (fractions of the page) | "
        f"who made it | {'how sure the machine was (0 to 1, - if not stated) | ' if confidence else ''}text. "
        f"A person's line outranks a machine's. ({context.statement}.)\n"
        + context.text + settle
    )


def with_page_context(
    context: str | list | None, documents: list, files: list, library_path: str, *, confidence: bool = False,
    review_mode: str = IN_TURN
) -> str | list | None:
    """A vision tool's per-file context: what is WIRED IN wins (a draft from the step before is the
    thing to work on); a file with nothing wired gets its page's lines. files[i] pairs with
    documents[i], as `process_vision` pairs them."""
    if not library_path or not documents:
        return context
    import logging

    from fichero_server.db import db_manager

    log = logging.getLogger(__name__)
    db = db_manager.get_database(library_path)
    out: list[str | None] = []
    for index in range(len(files)):
        doc = documents[index] if index < len(documents) else None
        doc_id = doc.get("id") if isinstance(doc, dict) else getattr(doc, "id", None)
        wired = (context[index] if isinstance(context, list) and index < len(context)
                 else context if isinstance(context, str) else None)
        if wired or not doc_id:
            out.append(wired or None)
            continue
        built = tool_context(db, str(doc_id), confidence=confidence, review_mode=review_mode)
        log.info("page context for %s: %s", doc_id, built.statement)   # says what it sends
        out.append(as_prompt_context(built, confidence=confidence))
    return out
