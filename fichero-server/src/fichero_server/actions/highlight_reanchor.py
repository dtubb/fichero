"""Highlights follow the words they quoted when a page's text changes (#5077, ruled 2026-10-01).

A text highlight stores ``char_start``/``char_end`` as UTF-16 offsets into ``Document.page_content``
(the Swift frontend's units, #3262). When a correction changes the page's text, those offsets would
land on other words: a plausible wrong quotation that ``promote-to-claim`` would copy into a claim.
So whenever the cache writer replaces the text, every highlight on the page is re-found by the words
it quoted plus a little context on each side (the W3C TextQuoteSelector idea). A highlight that
cannot be found unambiguously keeps its offsets and is FLAGGED in ``metadata["reanchor"]`` with its
quote, so a person can decide; it is never moved silently. A flagged highlight is retried on every
later change, which is how undoing a correction brings it back.
"""
from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

from fichero_server.core.utf16_offsets import utf16_range_to_codepoint_range

CONTEXT = 32
REANCHOR = "reanchor"


def _utf16(text: str, cp: int) -> int:
    return len(text[:cp].encode("utf-16-le")) // 2


def _mapped(matcher: SequenceMatcher, cp: int) -> int:
    """Where an old code-point position sits in the new text (inside an edit: the edit's start)."""
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if i1 <= cp < i2 or (cp == i2 and tag == "equal"):
            return j1 + (cp - i1 if tag == "equal" else 0)
    return len(matcher.b)


def _common_suffix(a: str, b: str) -> int:
    n = 0
    while n < min(len(a), len(b)) and a[-1 - n] == b[-1 - n]:
        n += 1
    return n


def _common_prefix(a: str, b: str) -> int:
    n = 0
    while n < min(len(a), len(b)) and a[n] == b[n]:
        n += 1
    return n


def find_quote(new_text: str, quote: dict, near: int) -> tuple[str, int | None]:
    """Locate ``quote`` ({exact, prefix, suffix}) in ``new_text``. Returns (status, code-point start):
    ``ok`` with a position, or ``lost`` / ``ambiguous`` with None."""
    exact = quote["exact"]
    if not exact:
        return "ok", min(near, len(new_text))
    hits, start = [], new_text.find(exact)
    while start != -1:
        hits.append(start)
        start = new_text.find(exact, start + 1)
    if not hits:
        return "lost", None
    if len(hits) == 1:
        return "ok", hits[0]

    # Several: the context decides; distance from where the edit map puts it breaks a tie.
    def score(h: int) -> tuple[int, int]:
        ctx = _common_suffix(new_text[:h], quote["prefix"]) + _common_prefix(
            new_text[h + len(exact):], quote["suffix"]
        )
        return ctx, -abs(h - near)

    ranked = sorted(hits, key=score, reverse=True)
    if score(ranked[0]) == score(ranked[1]):
        return "ambiguous", None
    return "ok", ranked[0]


def reanchor_highlights(db: Any, document_id: str, old_text: str, new_text: str) -> dict[str, int]:
    """Move every text highlight on ``document_id`` from ``old_text`` to ``new_text``. Returns counts
    by outcome. ponytail: one SequenceMatcher per page change, quadratic in the worst case; a page is
    a few thousand characters, so fine until somebody stores a book as one page."""
    from fichero_server.models.knowledge import Annotation

    counts = {"moved": 0, "unchanged": 0, "flagged": 0}
    anns = [a for a in db.query(Annotation, document_id=document_id)
            if a.char_start is not None and a.char_end is not None]
    if not anns or old_text == new_text:
        return counts
    matcher = SequenceMatcher(None, old_text, new_text, autojunk=False)
    for ann in anns:
        metadata = dict(ann.metadata or {})
        flagged = metadata.get(REANCHOR)
        if flagged:  # its offsets point into some earlier text; only its quote is trustworthy
            quote, near = flagged["quote"], len(new_text) // 2
        else:
            s, e = utf16_range_to_codepoint_range(old_text, ann.char_start, ann.char_end)
            quote = {"exact": old_text[s:e], "prefix": old_text[max(0, s - CONTEXT):s], "suffix": old_text[e:e + CONTEXT]}
            near = _mapped(matcher, s)
        status, cp = find_quote(new_text, quote, near)
        if status != "ok":
            metadata[REANCHOR] = {"status": status, "quote": quote}
            if metadata != (ann.metadata or {}):
                ann.metadata = metadata
                db.save(ann)
            counts["flagged"] += 1
            continue
        start, end = _utf16(new_text, cp), _utf16(new_text, cp + len(quote["exact"]))
        metadata.pop(REANCHOR, None)
        if (start, end) == (ann.char_start, ann.char_end) and metadata == (ann.metadata or {}):
            counts["unchanged"] += 1
            continue
        if ann.anchor is not None and (ann.anchor.char_start, ann.anchor.char_end) == (ann.char_start, ann.char_end):
            ann.anchor = ann.anchor.model_copy(update={"char_start": start, "char_end": end})
        ann.char_start, ann.char_end, ann.metadata = start, end, metadata
        db.save(ann)
        counts["moved"] += 1
    return counts
