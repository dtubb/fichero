"""A word whose text a person's edit took out of its line no longer counts (#5190, ruled 2026-09-28).

WHY: words imported from ALTO/PAGE carry their own readings, and the Reader edits LINES. Before
this, deleting a word in the Reader left that word's reading counting: the Inspector, the
Segments pane and every export still said the word was there, disagreeing with the line the
person just typed. `source.textedit.retiring-is-part-of-the-edit`: retirement is worked out at
read time from the counting line reading, so ⌘Z (which retracts the line reading) brings the word
back with nothing written about words.
"""

from __future__ import annotations

import asyncio

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.document.segment_readings import counting_by_kind, readings_of_segment
from fichero_server.api.routes.system.actions_registry import undo_action
from fichero_server.models import Segment
from tests.unit.api.test_an_edited_line_reads_from_itself import PERSON
from tests.unit.api.test_page_text_follows_the_file import CORPUS, _import

# The one corpus page whose words carry their own text, several to a line: Transkribus PAGE XML
# with `Word/TextEquiv`, a German Fraktur newspaper (524 words, 74 lines). The Clm ALTO and the
# Syriac PAGE each have one text-bearing "word" per line at most.
WORDED = CORPUS / "transkribus_german-fraktur_nzz-17840710.page.xml"


def _counting_text(db, segment_id: str) -> str | None:
    items = readings_of_segment(db, segment_id)
    answer = counting_by_kind(db, segment_id, items).get("transcription")
    if answer is None or answer.representation_id is None:
        return None
    return next(i.content for i in items if i.id == answer.representation_id)


def _words(db, line: Segment) -> list[Segment]:
    from fichero_server.api.routes.document.segment_readings import _segment_order_key

    rows = [s for s in db.all(Segment) if s.parent_segment_id == line.id and s.deleted_at is None]
    return sorted(rows, key=_segment_order_key)


def _a_line_of_words(db, doc_id: str) -> Segment:
    """A line whose words carry their own readings, three or more of them."""
    lines = [s for s in db.all(Segment) if s.document_id == doc_id and s.kind == "line" and s.deleted_at is None]
    return next(line for line in lines if len([w for w in _words(db, line) if _counting_text(db, w.id)]) >= 3)


def test_the_word_the_edit_took_out_stops_counting_and_undo_brings_it_back(db):
    doc_id = _import(db, WORDED)
    line = _a_line_of_words(db, doc_id)
    words = [w for w in _words(db, line) if _counting_text(db, w.id)]
    texts = [_counting_text(db, w.id) for w in words]

    edited = " ".join(texts[:1] + texts[2:])  # the person deletes the second word
    made = registry.invoke(db, "representation.create", {
        "document_id": doc_id, "segment_id": line.id, "kind": "transcription", "content": edited,
    }, PERSON)

    assert _counting_text(db, words[1].id) is None, "the deleted word still counts"
    assert [_counting_text(db, w.id) for w in (words[0], *words[2:])] == [texts[0], *texts[2:]]

    undone = asyncio.run(undo_action(made.audit_id, request=None, db=db, ctx=ActionContext(actor="historian")))
    assert undone.ok is True
    assert _counting_text(db, words[1].id) == texts[1], "undo must bring the word back"


def test_a_line_typed_unchanged_retires_nothing_and_a_machines_line_retires_nothing(db):
    doc_id = _import(db, WORDED)
    line = _a_line_of_words(db, doc_id)
    words = [w for w in _words(db, line) if _counting_text(db, w.id)]
    texts = [_counting_text(db, w.id) for w in words]

    registry.invoke(db, "representation.create", {
        "document_id": doc_id, "segment_id": line.id, "kind": "transcription",
        "content": "  ".join(texts),  # whitespace never counts
    }, PERSON)
    assert [_counting_text(db, w.id) for w in words] == texts


def test_a_word_given_its_own_reading_after_the_edit_counts_again(db):
    doc_id = _import(db, WORDED)
    line = _a_line_of_words(db, doc_id)
    words = [w for w in _words(db, line) if _counting_text(db, w.id)]
    texts = [_counting_text(db, w.id) for w in words]
    registry.invoke(db, "representation.create", {
        "document_id": doc_id, "segment_id": line.id, "kind": "transcription",
        "content": " ".join(texts[1:]),
    }, PERSON)
    assert _counting_text(db, words[0].id) is None

    registry.invoke(db, "representation.create", {
        "document_id": doc_id, "segment_id": words[0].id, "kind": "transcription", "content": "Typed",
    }, PERSON)
    assert _counting_text(db, words[0].id) == "Typed", "Retired applies only to readings older than the edit"


def _page_words(db, doc_id: str) -> list[str | None]:
    """Each PAGE `Word`'s text in export order, None for a Word with no TextEquiv."""
    import xml.etree.ElementTree as ET

    from fichero_server.page_export import export_page

    root = ET.fromstring(export_page(db, doc_id, "pagexml").data)
    out = []
    for word in root.iter():
        if word.tag.rsplit("}", 1)[-1] != "Word":
            continue
        unicode = [e.text or "" for e in word.iter() if e.tag.rsplit("}", 1)[-1] == "Unicode"]
        out.append(unicode[0] if unicode else None)
    return out


def test_the_export_writes_a_retired_word_with_its_shape_and_no_text(db):
    """`source.textedit.retired-words-in-the-export`: the export wrote EVERY reading of a word,
    so a word the person deleted from the line went out with its old text."""
    doc_id = _import(db, WORDED)
    line = _a_line_of_words(db, doc_id)
    words = [w for w in _words(db, line) if _counting_text(db, w.id)]
    texts = [_counting_text(db, w.id) for w in words]
    before = _page_words(db, doc_id)

    registry.invoke(db, "representation.create", {
        "document_id": doc_id, "segment_id": line.id, "kind": "transcription",
        "content": " ".join(texts[:1] + texts[2:]),
    }, PERSON)
    after = _page_words(db, doc_id)

    assert len(after) == len(before), "the retired word keeps its shape"
    assert after.count(None) == before.count(None) + 1, "exactly one Word lost its text"
    gone = [b for b, a in zip(before, after) if b is not None and a is None]
    assert gone == [texts[1]]


def test_the_audit_names_the_words_the_edit_retired(db):
    """`retiring-is-part-of-the-edit`: one action, one audit row -- and the row says which words
    the edit retired, so the history can answer "why does this word have no reading"."""
    from fichero_server.models import ActionAudit

    doc_id = _import(db, WORDED)
    line = _a_line_of_words(db, doc_id)
    words = [w for w in _words(db, line) if _counting_text(db, w.id)]
    texts = [_counting_text(db, w.id) for w in words]
    made = registry.invoke(db, "representation.create", {
        "document_id": doc_id, "segment_id": line.id, "kind": "transcription",
        "content": " ".join(texts[:1] + texts[2:]),
    }, PERSON)

    audit = db.get(ActionAudit, made.audit_id)
    assert audit.after["retired_word_segment_ids"] == [words[1].id]


def test_redo_retires_the_word_again(db):
    """⌘Z then ⌘⇧Z: the line reading is retracted then unretracted, and since nothing about the
    words was ever written, the word counts after the undo and is retired again after the redo."""
    doc_id = _import(db, WORDED)
    line = _a_line_of_words(db, doc_id)
    words = [w for w in _words(db, line) if _counting_text(db, w.id)]
    texts = [_counting_text(db, w.id) for w in words]
    made = registry.invoke(db, "representation.create", {
        "document_id": doc_id, "segment_id": line.id, "kind": "transcription",
        "content": " ".join(texts[:1] + texts[2:]),
    }, PERSON)

    undone = asyncio.run(undo_action(made.audit_id, request=None, db=db, ctx=ActionContext(actor="historian")))
    assert _counting_text(db, words[1].id) == texts[1]
    redone = asyncio.run(undo_action(undone.audit_id, request=None, db=db, ctx=ActionContext(actor="historian")))
    assert redone.ok is True
    assert _counting_text(db, words[1].id) is None, "redo must retire the word again"


def _exported_words(db, doc_id: str, fmt: str) -> list[str | None]:
    """Each exported word's text in order, None for a word written with no text: ALTO
    `String@CONTENT`, hOCR `ocrx_word`'s text."""
    import xml.etree.ElementTree as ET

    from fichero_server.page_export import export_page

    data = export_page(db, doc_id, fmt).data
    if fmt == "alto":
        strings = [e for e in ET.fromstring(data).iter() if e.tag.rsplit("}", 1)[-1] == "String"]
        return [e.get("CONTENT") or None for e in strings]
    import html.parser

    class Words(html.parser.HTMLParser):
        def __init__(self):
            super().__init__()
            self.out: list[str | None] = []
            self.depth = 0

        def handle_starttag(self, tag, attrs):
            if self.depth:
                self.depth += 1
            elif "ocrx_word" in (dict(attrs).get("class") or "").split():
                self.out.append(None)
                self.depth = 1

        def handle_endtag(self, tag):
            if self.depth:
                self.depth -= 1

        def handle_data(self, text):
            if self.depth and text.strip():
                self.out[-1] = (self.out[-1] or "") + text.strip()

    parser = Words()
    parser.feed(data.decode("utf-8"))
    return parser.out


def test_alto_and_hocr_write_a_retired_word_with_no_text(db):
    """`retired-words-in-the-export`: ALTO `String CONTENT=""` (the form an untranscribed word
    already takes) and an empty hOCR `ocrx_word`, as PAGE XML above."""
    doc_id = _import(db, WORDED)
    line = _a_line_of_words(db, doc_id)
    words = [w for w in _words(db, line) if _counting_text(db, w.id)]
    texts = [_counting_text(db, w.id) for w in words]
    before = {fmt: _exported_words(db, doc_id, fmt) for fmt in ("alto", "hocr")}
    registry.invoke(db, "representation.create", {
        "document_id": doc_id, "segment_id": line.id, "kind": "transcription",
        "content": " ".join(texts[:1] + texts[2:]),
    }, PERSON)
    for fmt, was in before.items():
        now = _exported_words(db, doc_id, fmt)
        assert len(now) == len(was), f"{fmt}: the retired word keeps its place"
        assert [b for b, a in zip(was, now) if b is not None and a is None] == [texts[1]], fmt
