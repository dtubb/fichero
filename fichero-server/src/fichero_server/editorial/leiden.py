"""The editor's brackets and dots, DRAWN from editorial facts (`source.sure.brackets-are-drawn`).

The Leiden conventions, as papyrologists and epigraphers print them. A reading's text never holds
these signs; they are produced here, from the reading and the facts about it, whenever a reading is
shown or exported:

    unclear      each letter with an under-dot        αβ   -> α̣β̣
    lost         the letters restored inside [ ]      [αβ]  (with no text: [--- n ---] or [.n])
    restored     the same square brackets             [αβ]
    supplied     angle brackets (left out by the scribe) <αβ>
    superfluous  braces                               {αβ}
    deleted      double square brackets               ⟦αβ⟧
    added        slashes: above the line \\αβ/, below /αβ\\, in the margin `αβ`

A project may one day choose its own signs; this is the one convention the spec names.
"""

from __future__ import annotations

from collections.abc import Iterable

from fichero_server.models.editorial import EditorialFact, EditorialFactKind

_UNDERDOT = "\u0323"

_WRAP: dict[EditorialFactKind, tuple[str, str]] = {
    EditorialFactKind.lost: ("[", "]"),
    EditorialFactKind.restored: ("[", "]"),
    EditorialFactKind.supplied: ("<", ">"),
    EditorialFactKind.superfluous: ("{", "}"),
    EditorialFactKind.deleted: ("\u27e6", "\u27e7"),
}

_ADDED_PLACE: dict[str, tuple[str, str]] = {
    "above": ("\\", "/"),
    "below": ("/", "\\"),
    "margin": ("`", "`"),
}


def _gap(fact: EditorialFact) -> str:
    """A lost stretch with no text: how much is missing, as Leiden writes it."""
    if fact.extent_quantity is not None and fact.extent_unit in (None, "character", "letter"):
        count = int(fact.extent_quantity)
        return f"[.{count}]" if count <= 12 else f"[--- {count} ---]"
    if fact.extent:
        return f"[--- {fact.extent} ---]"
    return "[---]"


def _signs(fact: EditorialFact) -> tuple[str, str] | None:
    if fact.kind == EditorialFactKind.added:
        return _ADDED_PLACE.get(fact.place or "above", ("\\", "/"))
    return _WRAP.get(fact.kind)


def draw(text: str, facts: Iterable[EditorialFact]) -> str:
    """`text` with its editorial facts drawn in. Facts with a character span are drawn at it (a fact
    whose span does not fit the text is left out, never drawn somewhere else); a lost fact with NO
    span is a gap in the text, drawn where its span would start, or at the end when it has none.
    Nested spans are drawn inside out; overlapping ones keep the outer."""
    live = [f for f in facts if f.withdrawn_at is None]
    spanned = sorted(
        (f for f in live if f.char_start is not None and f.char_end is not None
         and 0 <= f.char_start < f.char_end <= len(text)),
        key=lambda f: (f.char_start, -(f.char_end or 0)),
    )
    gaps = [f for f in live if f.kind == EditorialFactKind.lost and (f.char_start is None or f.char_end is None)]

    # Where each sign goes: (position, order, sign). Openers sort after closers at one position so
    # "]" of one stretch comes before "[" of the next; under-dots attach to their letter.
    marks: list[tuple[int, int, str]] = []
    dotted: set[int] = set()
    for fact in spanned:
        if fact.kind == EditorialFactKind.unclear:
            dotted.update(range(fact.char_start, fact.char_end))
            continue
        signs = _signs(fact)
        if signs is None:
            continue
        opener, closer = signs
        marks.append((fact.char_start, 1, opener))
        marks.append((fact.char_end, 0, closer))
    for fact in gaps:
        at = fact.char_start if fact.char_start is not None and 0 <= fact.char_start <= len(text) else len(text)
        marks.append((at, 2, _gap(fact)))

    out: list[str] = []
    by_position: dict[int, list[tuple[int, str]]] = {}
    for position, order, sign in marks:
        by_position.setdefault(position, []).append((order, sign))
    for index in range(len(text) + 1):
        for _order, sign in sorted(by_position.get(index, [])):
            out.append(sign)
        if index < len(text):
            out.append(text[index] + (_UNDERDOT if index in dotted else ""))
    return "".join(out)
