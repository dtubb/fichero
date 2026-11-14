"""The validator: what is wrong with a page's segments before it is exported.

Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.validate-before-export` (lines outside
every region; outlines that cross themselves; outlines overlapping another of the same level by more than a tenth;
segments with no shape; lines with no baseline; a reading order with a repeat, a gap or a segment missing; words whose
spans do not tile their line's reading) and `segment-editor.edge.empty-region`. Through the real route.
"""

from __future__ import annotations

import pytest

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import DocType, Document, FileType, Segment, Status
from fichero_server.models.reading_orders import ReadingOrderEntry

pytestmark = pytest.mark.source_model


def _person() -> ActionContext:
    return ActionContext(actor="historian", library_path=None, is_bootstrap=True)


def _box(x, y, w, h):
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def _page(db, client):
    doc = Document(name="folio.jpg", doc_type=DocType.file, file_type=FileType.image, path="/path/folio.jpg",
                   status=Status.completed)
    db.save(doc)
    pass_id = client.post("/api/segments/passes", json={"document_id": doc.id, "name": "lines"}).json()["id"]
    return doc, pass_id


def _segment(client, doc, pass_id, *, kind="line", polygon=None, baseline=None, parent=None, rect=None):
    anchor = {"document_id": doc.id}
    if polygon:
        anchor["polygon"] = polygon
    if rect:
        anchor["rect"] = rect
    body = {"document_id": doc.id, "pass_id": pass_id, "kind": kind, "anchor": anchor}
    if baseline:
        body["baseline"] = baseline
    if parent:
        body["parent_segment_id"] = parent
    response = client.post("/api/segments", json=body)
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _clean_page(db, client):
    doc, pass_id = _page(db, client)
    region = _segment(client, doc, pass_id, kind="region", polygon=_box(0.05, 0.1, 0.9, 0.5))
    first = _segment(client, doc, pass_id, polygon=_box(0.1, 0.2, 0.8, 0.05), baseline=[[0.1, 0.24], [0.9, 0.24]],
                     parent=region)
    second = _segment(client, doc, pass_id, polygon=_box(0.1, 0.3, 0.8, 0.05), baseline=[[0.1, 0.34], [0.9, 0.34]],
                      parent=region)
    return doc, pass_id, region, first, second


def _problems(client, doc):
    response = client.get(f"/api/segments/document/{doc.id}/validate")
    assert response.status_code == 200, response.text
    return response.json()["problems"]


def _kinds(problems):
    return {(p["kind"], tuple(p["segment_ids"])) for p in problems}


def test_a_clean_page_has_nothing_to_fix(db, client):
    doc, *_ = _clean_page(db, client)

    assert _problems(client, doc) == []


def test_a_line_outside_every_region_and_a_line_with_no_baseline_are_named(db, client):
    doc, pass_id, *_ = _clean_page(db, client)
    stray = _segment(client, doc, pass_id, polygon=_box(0.1, 0.7, 0.8, 0.05))

    kinds = _kinds(_problems(client, doc))

    assert ("line-outside-regions", (stray,)) in kinds
    assert ("no-baseline", (stray,)) in kinds


def test_an_empty_region_and_two_overlapping_lines_are_named(db, client):
    doc, pass_id, region, first, _second = _clean_page(db, client)
    empty = _segment(client, doc, pass_id, kind="region", polygon=_box(0.05, 0.7, 0.9, 0.2))
    over = _segment(client, doc, pass_id, polygon=_box(0.1, 0.21, 0.8, 0.05), baseline=[[0.1, 0.25], [0.9, 0.25]],
                    parent=region)

    problems = _problems(client, doc)

    assert ("empty-region", (empty,)) in _kinds(problems)
    overlap = next(p for p in problems if p["kind"] == "overlap" and set(p["segment_ids"]) == {first, over})
    assert overlap["share"] > 0.5


def test_a_self_crossing_outline_written_by_an_import_is_named(db, client):
    doc, _pass_id, _region, first, _second = _clean_page(db, client)
    row = db.get(Segment, first)
    row.anchor = row.anchor.model_copy(update={"polygon": [[0.1, 0.2], [0.9, 0.25], [0.9, 0.2], [0.1, 0.25]]})
    db.save(row)  # straight into the store, as an import that predates the check could have

    assert ("self-crossing", (first,)) in _kinds(_problems(client, doc))


def test_a_segment_missing_from_the_order_and_one_named_twice_are_named(db, client):
    doc, _pass_id, _region, first, second = _clean_page(db, client)
    (entry,) = [e for e in db.all(ReadingOrderEntry) if e.segment_id == first]
    db.delete(entry)
    (kept,) = [e for e in db.all(ReadingOrderEntry) if e.segment_id == second]
    db.save(kept.model_copy(update={"id": "twice", "position": kept.position + 0.5}))

    kinds = _kinds(_problems(client, doc))

    assert ("order-missing", (first,)) in kinds
    assert ("order-repeat", (second,)) in kinds


def test_words_that_do_not_tile_their_lines_reading_are_named(db, client):
    doc, pass_id, _region, first, _second = _clean_page(db, client)
    registry.invoke(db, "representation.create", {
        "document_id": doc.id, "segment_id": first, "kind": "transcription", "content": "en el"}, _person())
    word = _segment(client, doc, pass_id, kind="word", rect=[0.1, 0.2, 0.2, 0.05], parent=first)
    row = db.get(Segment, word)
    row.metadata = {**row.metadata, "reading_span": [0, 2]}  # "el" is in no word
    db.save(row)

    assert ("words-do-not-tile", (first, word)) in _kinds(_problems(client, doc))


def test_a_line_whose_region_was_deleted_is_outside_every_region(db, client):
    """Review of batch 16 (2026-11-14): a parent id alone was taken for a region; a line whose region is deleted is in
    no region, with or without other regions on the page."""
    from fichero_server.core.timeutil import utc_now

    doc, pass_id, region, first, second = _clean_page(db, client)
    row = db.get(Segment, region)
    row.deleted_at = utc_now()
    db.save(row)
    kinds = _kinds(_problems(client, doc))
    assert ("line-outside-regions", (first,)) in kinds and ("line-outside-regions", (second,)) in kinds
