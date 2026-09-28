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
#: (the trust order the ruling settled); the mark lets the model see which is which.
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


def _maker(reading: Any) -> str:
    kind = getattr(reading, "provenance_kind", None)
    kind = getattr(kind, "value", kind)
    if kind in MAKER:
        return MAKER[kind]
    return "machine" if (getattr(reading, "producer_tool", None) or getattr(reading, "producer_model", None)) else "unrecorded"


def tool_context(db: Any, document_id: str, segment_ids: list[str] | None = None) -> ToolContext:
    """The compact lines for `segment_ids` on one page (None: the whole page)."""
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
    lines, ids = [], []
    for span in derived.spans:
        if span.representation_id is None or (wanted is not None and not in_scope(span.segment_id)):
            continue
        row = shapes.get(span.segment_id)
        box = " ".join(f"{v:.3f}" for v in (row.bbox_x, row.bbox_y, row.bbox_w, row.bbox_h)) if row else "- - - -"
        text = derived.text[span.start:span.end].replace("\n", " ")
        lines.append(f"{span.segment_id} | {box} | {_maker(readings.get(span.representation_id))} | {text}")
        ids.append(span.segment_id)
    characters = sum(len(line) for line in lines)
    where = "the page" if wanted is None else f"{len(wanted)} selected segment(s)"
    statement = (
        f"{len(lines)} line(s) of {where}, {characters} characters, from pass {derived.pass_id} in reading order"
        if lines else f"no reading on {where} yet: the tool works from the picture alone"
    )
    return ToolContext(text="\n".join(lines), segment_ids=ids, characters=characters,
                       pass_id=derived.pass_id, statement=statement)


def as_prompt_context(context: ToolContext) -> str:
    """The context as the model reads it: what it is, then the lines."""
    if not context.segment_ids:
        return f"This page has {context.statement}."
    return (
        "The page's existing reading, one line per segment: id | x y w h (fractions of the page) | "
        f"who made it | text. A person's line outranks a machine's. ({context.statement}.)\n"
        + context.text
    )


def with_page_context(
    context: str | list | None, documents: list, files: list, library_path: str
) -> str | list | None:
    """A vision tool's per-file context with each page's lines added (files[i] pairs with
    documents[i], as `process_vision` pairs them). Anything already wired in comes first."""
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
        page = None
        if doc_id:
            built = tool_context(db, str(doc_id))
            log.info("page context for %s: %s", doc_id, built.statement)   # says what it sends
            page = as_prompt_context(built)
        out.append("\n\n".join(part for part in (wired, page) if part) or None)
    return out
