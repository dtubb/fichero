"""The rows the Inspector's form draws for a selection (`source.editor.inspector-form-comes-from-the-engine`).

The app draws what this answers and sends the existing action for each control; it keeps no table of
its own. One row per fact a person can change on the selection's level, each with its state across
the selection (`set` on the segment, `inherited` from above, `mixed`, or `none` when nothing states
it) and the choices the control offers.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from fichero_server.db import Database
from fichero_server.llm.language_policy import DIRECTIONS
from fichero_server.models import Segment

#: Region types in the order the Kind menu lists them (`segment-editor.type-by-key`); a person's pick is written to `kind_raw`.
REGION_TYPES: tuple[str, ...] = (
    "main text", "heading", "marginalia", "stamp", "signature", "table", "picture", "damage", "blank",
)
#: How a region's lines or columns succeed one another: not `alternating` or `follows-baseline`, which describe a line.
LINE_PROGRESSIONS: tuple[str, ...] = ("ltr", "rtl", "ttb", "btt")

_DIRECTION_LABELS = {
    "ltr": "Left to Right", "rtl": "Right to Left", "ttb": "Top to Bottom", "btt": "Bottom to Top",
    "alternating": "Alternating (Boustrophedon)", "follows-baseline": "Follows the Baseline",
}

#: The rows per level, in the order the form draws them. A kind not listed (a table cell, a picture) gets the facts only.
LEVEL_ROWS: dict[str, tuple[str, ...]] = {
    "region": ("type", "furniture", "language", "script", "direction", "line_progression"),
    "line": ("furniture", "language", "script", "direction"),
    "word": ("language", "script", "direction"),
}
_FACTS_ONLY = ("language", "script", "direction")
_LABELS = {
    "type": "Type", "furniture": "Page furniture", "language": "Language", "script": "Script",
    "direction": "Direction", "line_progression": "Line progression",
}
_FACTS = ("language", "script", "direction")


class InspectChoice(BaseModel):
    value: str
    label: str


class InspectRow(BaseModel):
    key: str
    label: str
    #: `choice` is a menu (free text too when `free_text`), `toggle` an on/off switch whose values are "true" and "false".
    kind: Literal["choice", "toggle"]
    state: Literal["set", "inherited", "mixed", "none"]
    #: The shared value when the selection agrees; None when mixed or nothing states it.
    value: str | None = None
    #: Every distinct value when mixed, so the form can say "Mixed" and offer them.
    values: list[str] = []
    #: The level that answered when inherited ("document", "project", "derived-from-script", ...).
    inherited_from: str | None = None
    choices: list[InspectChoice] = []
    #: A language or script is any code, not only the choices.
    free_text: bool = False


class SegmentInspectRead(BaseModel):
    #: The shared level ("region", "line", "word", ...) or "mixed".
    level: str
    count: int
    #: Ids left out (not found, deleted, or on a page the caller may not read), counted and never a 404.
    withheld: int = 0
    rows: list[InspectRow]


def rows_for_levels(levels: list[str]) -> tuple[str, list[str]]:
    """The level the selection shares ("mixed" when it spans levels) and the row keys every level has."""
    shared = [list(LEVEL_ROWS.get(level, _FACTS_ONLY)) for level in levels]
    keys = [key for key in shared[0] if all(key in other for other in shared)]
    return (levels[0] if len(set(levels)) == 1 else "mixed"), keys


def _seen_codes(db: Database, rows: list[Segment]) -> dict[str, list[str]]:
    """What the selection's pages already state for language and script: the codes a person would pick again (one read)."""
    ids = sorted({row.document_id for row in rows})
    marks = ", ".join("?" for _ in ids)
    found = db.execute_fetchall(
        f"SELECT DISTINCT language, script FROM segments WHERE document_id IN ({marks}) AND deleted_at IS NULL", ids
    )
    return {
        "language": sorted({r[0] for r in found if r[0]}),
        "script": sorted({r[1] for r in found if r[1]}),
    }


def _choices(key: str, seen: dict[str, list[str]], values: list[str]) -> list[InspectChoice]:
    if key == "type":
        return [InspectChoice(value=t, label=t.capitalize()) for t in REGION_TYPES]
    if key == "direction":
        return [InspectChoice(value=d, label=_DIRECTION_LABELS.get(d, d)) for d in DIRECTIONS]
    if key == "line_progression":
        return [InspectChoice(value=d, label=_DIRECTION_LABELS[d]) for d in LINE_PROGRESSIONS]
    if key in ("language", "script"):
        codes = sorted(set(seen[key]) | set(values))
        return [InspectChoice(value=c, label=c) for c in codes]
    return []


def inspect_selection(db: Database, rows: list[Segment], withheld: int) -> SegmentInspectRead:
    """The form for `rows` (live segments, at least one): the shared level's rows, each with its state."""
    from fichero_server.api.routes.document.source_settings import _resolved_for

    level, keys = rows_for_levels([row.kind for row in rows])
    resolved = {row.id: {s.key: s for s in _resolved_for(db, row.id, None).settings} for row in rows}
    seen = _seen_codes(db, rows)
    out: list[InspectRow] = []
    for key in keys:
        entries: list[tuple[str | None, str | None, str | None]] = []  # (own, effective, inherited level)
        for row in rows:
            if key in _FACTS:
                own = getattr(row, key)
                answer = resolved[row.id][key]
                entries.append((own, own or answer.value, None if own else _came_from(answer, row)))
            elif key == "type":
                entries.append((row.kind_raw, row.kind_raw, None))
            elif key == "furniture":
                flag = "true" if row.is_furniture else "false"
                entries.append((flag, flag, None))
            else:
                entries.append((row.line_progression, row.line_progression, None))
        out.append(_row(key, entries, seen))
    return SegmentInspectRead(level=level, count=len(rows), withheld=withheld, rows=out)


def _came_from(answer: Any, row: Segment) -> str:
    """Where an inherited value came from: the rung's level, "parent" for a value set on the segment's own parent, else the source."""
    if answer.level == "segment" and answer.segment_id not in (None, row.id):
        return "parent"
    return answer.level or answer.source


def _row(key: str, entries: list[tuple[str | None, str | None, str | None]], seen: dict[str, list[str]]) -> InspectRow:
    effective = [e[1] for e in entries]
    distinct = sorted({v for v in effective if v is not None})
    owned = [e[0] is not None for e in entries]
    state: Any
    value: str | None = None
    values: list[str] = []
    inherited_from: str | None = None
    if len(set(effective)) > 1 or (any(owned) and not all(owned)):
        state, values = "mixed", distinct
    elif effective[0] is None:
        state = "none"
    elif all(owned):
        state, value = "set", effective[0]
    else:
        state, value = "inherited", effective[0]
        inherited_from = next((e[2] for e in entries if e[2]), None)
    return InspectRow(
        key=key, label=_LABELS[key], kind="toggle" if key == "furniture" else "choice", state=state, value=value,
        values=values, inherited_from=inherited_from, choices=_choices(key, seen, distinct),
        free_text=key in ("language", "script"),
    )
