"""A segment list says what each segment READS and what it sits in (#5139, first half).

Acceptance defect 11: `GET /api/segments/document/{id}`, `GET /api/segments` and
`GET /api/segments/{id}` returned `text: null` for every real segment and no parent, so a caller
could list the 4,525 shapes of a newspaper page and read none of them without one readings
request per segment. Checked through the LIBRARY: a real ALTO page goes in with `format.import`,
comes back through the routes, and each word's text and each segment's parent are compared with
the file itself (plain lxml), matched by the element id the import keeps (`source_id`).
"""

from __future__ import annotations

from lxml import etree

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import Segment
from tests.unit.api.test_page_text_follows_the_file import CLM, _import

BOOT = ActionContext(actor="historian", library_path=None, is_bootstrap=True)


def _file_truth():
    """From the file: each line's ID -> (its block's ID, its words' CONTENT in order). Clm's
    `String`s carry no ID, so a word is known by its line and its place in it."""
    lines = {}
    for el in etree.parse(str(CLM)).getroot().iter():
        if not isinstance(el.tag, str) or etree.QName(el).localname != "TextLine":
            continue
        block = el.getparent()
        while block is not None and etree.QName(block).localname not in ("TextBlock", "ComposedBlock"):
            block = block.getparent()
        words = [w.get("CONTENT") for w in el if isinstance(w.tag, str) and etree.QName(w).localname == "String"]
        lines[el.get("ID")] = (block.get("ID") if block is not None else None, words)
    return lines


def _check(items: list[dict], truth: dict) -> int:
    """Every word's text against the file, per line in order, and every line's parent. Returns
    how many words were checked."""
    by_id = {item["id"]: item for item in items}
    words_of: dict[str, list[dict]] = {}
    for item in items:
        if item["kind"] == "word":
            words_of.setdefault(item["parent_segment_id"], []).append(item)
    checked = 0
    for line_id, words in words_of.items():
        line = by_id.get(line_id)
        assert line is not None and line["kind"] == "line", "a word's parent is not its line"
        block_source, expected = truth[line["metadata"]["source_id"]]
        words.sort(key=lambda w: w["metadata"]["file_position"])
        assert [w["text"] for w in words] == expected, line["metadata"]["source_id"]
        checked += len(words)
        if line["parent_segment_id"] in by_id:
            assert by_id[line["parent_segment_id"]]["metadata"]["source_id"] == block_source
    return checked


def test_the_document_listing_carries_every_words_text_and_every_parent(db, client):
    doc_id = _import(db, CLM)
    items = client.get(f"/api/segments/document/{doc_id}").json()["segments"]
    truth = _file_truth()
    assert _check(items, truth) == sum(len(words) for _block, words in truth.values()) > 0
    assert all(item["parent_segment_id"] for item in items if item["kind"] in ("line", "word"))


def test_the_library_scoped_listing_carries_them_too(db, client):
    doc_id = _import(db, CLM)
    body = client.get("/api/segments", params={"document_ids": doc_id, "limit": 1000}).json()
    assert body["total"] <= 1000, "the page must hold the whole document for this check"
    truth = _file_truth()
    assert _check(body["items"], truth) == sum(len(words) for _block, words in truth.values()) > 0


def test_one_segment_carries_its_text_and_parent(db, client):
    doc_id = _import(db, CLM)
    word = next(s for s in db.all(Segment) if s.document_id == doc_id and s.kind == "word")
    line = db.get(Segment, word.parent_segment_id)
    siblings = sorted((s for s in db.all(Segment) if s.parent_segment_id == line.id),
                      key=lambda s: s.metadata["file_position"])
    _block, expected = _file_truth()[line.metadata["source_id"]]
    body = client.get(f"/api/segments/{word.id}").json()["segment"]
    assert body["text"] == expected[siblings.index(word)]
    assert body["parent_segment_id"] == line.id


def test_the_text_is_the_counting_reading_not_the_first_one(db, client):
    """A person's choice between two readings is what the list says -- the same answer as the page."""
    doc_id = _import(db, CLM)
    word = next(s for s in db.all(Segment) if s.document_id == doc_id and s.kind == "word")
    made = registry.invoke(db, "representation.create", {
        "document_id": doc_id, "segment_id": word.id, "kind": "transcription", "content": "CORRECTED",
    }, BOOT).result
    rep_id = made["id"] if isinstance(made, dict) else made.id
    registry.invoke(db, "reading.choose", {
        "segment_id": word.id, "kind": "transcription", "representation_id": rep_id,
    }, BOOT)
    assert client.get(f"/api/segments/{word.id}").json()["segment"]["text"] == "CORRECTED"
