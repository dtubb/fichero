"""Reader prompt fragments (`image.enhance.reader-prompt-fragment`, #6199).

A fragment is a named, versioned sentence (`ignore-show-through@1`) with one wording per reader kind: `line` (the line
reader, one picture a line) and `page` (a vision model reading the whole page). A recipe step names the fragments it sends;
what is sent is appended to that reader's prompt and the run keeps each one's id and version (`records`), so two runs'
results can be compared. A new wording is a new version: a registered id@version is never edited.

A project switches a fragment off by listing its id (no version) under the `prompt_fragments.off` setting
(comma separated); `project_off` reads it. A fragment that is off is not sent and is not recorded as sent.
"""
from __future__ import annotations

from typing import Any

LINE = "line"
PAGE = "page"
OFF_SETTING = "prompt_fragments.off"

#: id@version -> reader kind -> wording. `None` is a reader whose own prompt already says it.
FRAGMENTS: dict[str, dict[str, str | None]] = {
    "ignore-show-through@1": {
        LINE: "Faint, mirrored writing is the other side of the leaf showing through: do not read it.",
        PAGE: ("Ignore faint mirrored text showing through from the other side of the leaf; transcribe only the writing "
               "on this side."),
    },
    "ignore-furniture@1": {
        LINE: None,  # `line_reader.PROMPT` already answers null for a ruler, graph paper or blank paper
        PAGE: "Ignore the ruler, the colour card, the mount and anything outside the page.",
    },
    "read-over-stamps@1": {
        LINE: "A stamp or seal over the writing is not text: read the writing under and around it.",
        PAGE: ("Where a stamp or seal lies over the text, read the text, not the stamp; name the stamp in one bracketed "
               "note."),
    },
}


def split(name: str) -> tuple[str, int]:
    fid, _, version = name.partition("@")
    return fid, int(version)


def project_off(db: Any) -> frozenset[str]:
    """The fragment ids a project has switched off."""
    from fichero_server.models.knowledge import LibrarySetting

    row = db.get(LibrarySetting, OFF_SETTING) if db is not None else None
    return frozenset(part.strip() for part in (row.value if row else "").split(",") if part.strip())


def resolve(names: list[str] | None, reader: str, off: frozenset[str] | set[str] = frozenset()) -> tuple[str, list[dict[str, Any]]]:
    """`(text, records)` for the fragments a step names, for one reader kind. `text` is the wordings joined by a space
    (empty when none apply); `records` is `[{id, version, reader}]` for each fragment that is on, in the order named, even
    where this reader has no extra wording (its prompt already says it). An unknown name raises `ValueError`."""
    if reader not in (LINE, PAGE):
        raise ValueError(f"unknown reader kind {reader!r}")
    sentences: list[str] = []
    records: list[dict[str, Any]] = []
    for name in names or []:
        if name not in FRAGMENTS:
            raise ValueError(f"unknown prompt fragment {name!r}; known: {', '.join(sorted(FRAGMENTS))}")
        fid, version = split(name)
        if fid in off:
            continue
        records.append({"id": fid, "version": version, "reader": reader})
        wording = FRAGMENTS[name][reader]
        if wording:
            sentences.append(wording)
    return " ".join(sentences), records


def count_words(text: str, words: list[str]) -> int:
    """How many of `words` (the page's show-through words, as a person listed them) the reading contains: a word counts
    once per occurrence, whole words only, case ignored."""
    import re

    tokens = re.findall(r"\w+", (text or "").casefold())
    wanted = {w.casefold() for w in words}
    return sum(1 for token in tokens if token in wanted)


def measure_2x2(pages: list[dict[str, Any]], read: Any) -> dict[str, Any]:
    """Show-through words per page for the four cells: fragment on/off x cleanup on/off.

    `pages` is `[{id, show_through: [words]}]` (three sample pages). `read(page, fragment: bool, cleanup: bool) -> str` reads
    one page one way and returns its text. The account is `{cells: {"fragment=on,cleanup=off": {per_page: {id: n},
    seconds_per_page: {id: s}, total: n}, ...}}`; every cell reads every page."""
    import time

    cells: dict[str, Any] = {}
    for fragment in (False, True):
        for cleanup in (False, True):
            per_page: dict[str, int] = {}
            seconds: dict[str, float] = {}
            for page in pages:
                started = time.perf_counter()
                text = read(page, fragment, cleanup)
                seconds[page["id"]] = round(time.perf_counter() - started, 4)
                per_page[page["id"]] = count_words(text, page["show_through"])
            key = f"fragment={'on' if fragment else 'off'},cleanup={'on' if cleanup else 'off'}"
            cells[key] = {"per_page": per_page, "seconds_per_page": seconds, "total": sum(per_page.values())}
    return {"cells": cells}
