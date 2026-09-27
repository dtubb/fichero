"""A page's text follows its `as-written` order, so a line moved in the order reads where it was
moved to (Q5, lines move in the Reader's text; the Inspector's Order list too).

Three pins the manager set: before any move the text is BYTE-IDENTICAL to today's file-position
text; after a move the text shows it and undo restores it byte for byte; a move refreshes ONLY that
page's `page_content`. Through the library: real pages imported with `format.import`, moves through
the route the app calls, undo through the audit trail.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.api.routes.document.reading_orders import as_written_order
from fichero_server.api.routes.document.segment_readings import document_text
from fichero_server.models import Document, Segment, SegmentPass
from fichero_server.models.reading_orders import ReadingOrderEntry
from tests.unit.api.test_page_text_follows_the_file import CHINESE, CLM, _import

CHEROKEE = Path(
    "/Users/danieltubb/Fichero Test Corpus/Cherokee and English - Cherokee Phoenix newspaper, 1828 "
    "(ALTO 2, inch1200)/cherokee-phoenix_1828030601_0002.xml"
)


def _pass_id(db, doc_id: str) -> str:
    return next(p.id for p in db.all(SegmentPass) if p.document_id == doc_id and p.deleted_at is None)


def _file_position_text(db, doc_id: str):
    """Today's text: what the page derives with no as-written order to follow."""
    from fichero_server.core.timeutil import utc_now

    order = as_written_order(db, _pass_id(db, doc_id))
    order.deleted_at = utc_now()
    db.save(order)
    try:
        return document_text(db, doc_id)
    finally:
        order.deleted_at = None
        db.save(order)


@pytest.mark.parametrize("path", [CLM, CHEROKEE], ids=["clm-38r", "cherokee-p2"])
def test_before_any_move_the_text_is_byte_identical_to_file_position(db, path):
    if not path.exists():
        pytest.skip(f"{path.name} is in the local corpus only")
    doc_id = _import(db, path)
    following = document_text(db, doc_id)
    before = _file_position_text(db, doc_id)
    assert following.text.encode("utf-8") == before.text.encode("utf-8")
    assert [s.segment_id for s in following.spans] == [s.segment_id for s in before.spans]
    assert db.get(Document, doc_id).page_content == following.text


def _move_last_line_of_a_block_to_its_start(db, client, doc_id: str):
    order = as_written_order(db, _pass_id(db, doc_id))
    entries = [e for e in db.all(ReadingOrderEntry) if e.order_id == order.id]
    kinds = {s.id: s.kind for s in db.all(Segment) if s.document_id == doc_id}
    by_parent: dict = {}
    for entry in entries:
        if kinds[entry.segment_id] == "line":
            by_parent.setdefault(entry.parent_entry_id, []).append(entry)
    block_entry_id, lines = next((k, v) for k, v in by_parent.items() if len(v) >= 3)
    lines.sort(key=lambda e: e.position)
    moved, first = lines[-1], lines[0]
    response = client.post(f"/api/reading-orders/{order.id}/place", json={
        "segment_id": moved.segment_id, "parent_entry_id": block_entry_id,
        "expected_version": moved.version,
    })
    assert response.status_code == 200, response.text
    return response.json()["audit_id"], moved.segment_id, first.segment_id


def _first_span_of_line(db, derived, line_id: str) -> int:
    parents = {s.id: s.parent_segment_id for s in db.all(Segment)}
    return next(i for i, span in enumerate(derived.spans)
                if span.segment_id == line_id or parents.get(span.segment_id) == line_id)


def test_a_move_shows_in_the_text_and_undo_restores_it_byte_for_byte(db, client):
    doc_id = _import(db, CLM)
    before = document_text(db, doc_id).text
    audit_id, moved, first = _move_last_line_of_a_block_to_its_start(db, client, doc_id)
    after = document_text(db, doc_id)
    assert after.text != before
    assert _first_span_of_line(db, after, moved) < _first_span_of_line(db, after, first)
    assert db.get(Document, doc_id).page_content == after.text   # the cache followed

    assert client.post(f"/api/actions/audit/{audit_id}/undo").status_code == 200
    assert document_text(db, doc_id).text.encode("utf-8") == before.encode("utf-8")
    assert db.get(Document, doc_id).page_content.encode("utf-8") == before.encode("utf-8")


def test_a_move_refreshes_only_its_own_page(db, client):
    moved_doc = _import(db, CLM)
    other_doc = _import(db, CHINESE)
    other_before = db.get(Document, other_doc)
    _move_last_line_of_a_block_to_its_start(db, client, moved_doc)
    other_after = db.get(Document, other_doc)
    assert other_after.page_content == other_before.page_content
    assert other_after.updated_at == other_before.updated_at
