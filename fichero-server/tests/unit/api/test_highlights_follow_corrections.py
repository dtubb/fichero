"""#5077 (ruled 2026-10-01): when a correction changes a page's text, every highlight is re-found by
the words it quoted, and one that cannot be found unambiguously is FLAGGED, never moved silently.

Why this matters: highlight offsets index `page_content`. Once corrections rewrite that text, an
offset left alone lands on other words, a plausible wrong quotation with no error, and
`promote-to-claim` copies it into a claim's `source_excerpt` in a scholar's knowledge graph. If these
tests go red, highlights are quoting the wrong words again; do not loosen them to make them pass.
"""
from __future__ import annotations

import pytest

from fichero_server.actions.highlight_reanchor import find_quote, reanchor_highlights
from fichero_server.models import ActionAudit, Document
from fichero_server.models.knowledge import Annotation, AnnotationKind

from .test_page_content_is_a_cache import _converted, _correct

pytestmark = pytest.mark.source_model


def _u16(text: str, cp: int) -> int:
    return len(text[:cp].encode("utf-16-le")) // 2


def _highlight(db, doc_id: str, text: str, words: str) -> Annotation:
    cp = text.index(words)
    ann = Annotation(document_id=doc_id, kind=AnnotationKind.highlight,
                     char_start=_u16(text, cp), char_end=_u16(text, cp + len(words)))
    db.save(ann)
    return ann


def _quoted(db, ann_id: str) -> str:
    from fichero_server.core.utf16_offsets import utf16_range_to_codepoint_range

    ann = db.get(Annotation, ann_id)
    text = db.get(Document, ann.document_id).page_content
    s, e = utf16_range_to_codepoint_range(text, ann.char_start, ann.char_end)
    return text[s:e]


class TestThroughTheRealCorrection:
    def test_a_highlight_after_a_lengthened_line_still_quotes_its_words(self, db, client):
        page, _art, row = _converted(db, client)
        ann = _highlight(db, page.id, db.get(Document, page.id).page_content, "sailed from Cadiz")
        _correct(db, page, row)  # line 0 gets longer, so every later offset shifts
        assert _quoted(db, ann.id) == "sailed from Cadiz"
        assert "reanchor" not in (db.get(Annotation, ann.id).metadata or {})

    def test_a_highlight_on_words_the_correction_removed_is_flagged_not_moved(self, db, client):
        page, _art, row = _converted(db, client)
        before = db.get(Document, page.id).page_content
        ann = _highlight(db, page.id, before, "our Lord")
        old = (ann.char_start, ann.char_end)
        _correct(db, page, row, content="In the year of grace")
        got = db.get(Annotation, ann.id)
        assert (got.char_start, got.char_end) == old
        assert got.metadata["reanchor"]["status"] == "lost"
        assert got.metadata["reanchor"]["quote"]["exact"] == "our Lord"

    def test_undoing_the_correction_brings_a_flagged_highlight_back(self, db, client):
        page, _art, row = _converted(db, client)
        ann = _highlight(db, page.id, db.get(Document, page.id).page_content, "our Lord")
        result = _correct(db, page, row, content="In the year of grace")
        assert client.post(f"/api/actions/audit/{result.audit_id}/undo").status_code == 200
        first = [a for a in db.all(ActionAudit) if a.action_name == "representation.create"][-1]
        assert client.post(f"/api/actions/audit/{first.id}/undo").status_code == 200
        assert _quoted(db, ann.id) == "our Lord"
        assert "reanchor" not in (db.get(Annotation, ann.id).metadata or {})


class TestTheRule:
    def test_offsets_are_utf16_so_astral_characters_before_the_span_count_twice(self, db):
        old, new = "𝔄 sailed from Cadiz", "𝔄𝔄 sailed from Cadiz"
        doc = Document(name="p", page_content=old)
        db.save(doc)
        ann = _highlight(db, doc.id, old, "Cadiz")
        reanchor_highlights(db, doc.id, old, new)
        got = db.get(Annotation, ann.id)
        assert (got.char_start, got.char_end) == (_u16(new, new.index("Cadiz")), _u16(new, len(new)))

    def test_a_repeated_quote_is_told_apart_by_its_context(self):
        new = "to Cadiz by sea. Later, from Cadiz by land."
        quote = {"exact": "Cadiz", "prefix": "Later, from ", "suffix": " by land."}
        assert find_quote(new, quote, near=0) == ("ok", new.rindex("Cadiz"))

    def test_a_repeated_quote_with_no_telling_context_and_no_position_is_ambiguous(self):
        new = "x Cadiz x Cadiz x"
        quote = {"exact": "Cadiz", "prefix": "", "suffix": ""}
        assert find_quote(new, quote, near=6) == ("ambiguous", None)  # hits at 2 and 10, equally far
