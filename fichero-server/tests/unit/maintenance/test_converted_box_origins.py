"""#5066: where each converted box WAS is its own record, not the result's block.

`source.convert.box-origins-are-their-own-record` (docs/contributor_manual/specs/source/
segments-and-geometry.md). A mark drawn before conversion has only a rectangle; `resolve_anchor`
finds its box's segment by matching that rectangle against where the box was. That table lived
inside the result's kept block, so the result could never be deleted without every such mark
silently losing its box (the near-miss recorded on #5066). What breaks without these tests: an
origin not written at conversion, a resolver that still needs the block, or a library converted
before this that never gains its origins.
"""
from __future__ import annotations

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.document.segment_conversion import (
    record_missing_box_origins,
    resolve_anchor,
)
from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
from fichero_server.models import Artifact, ConvertedBoxOrigin, DocType, Document, FileType, Segment, Status
from fichero_server.models.anchors import SourceAnchor
from fichero_server.models.segments import converted_segment_id

FIRST = [0.1, 0.1, 0.5, 0.04]
SECOND = [0.1, 0.2, 0.5, 0.04]


def _converted_page(db, *, rendition_id=None):
    doc = Document(name="folio", doc_type=DocType.file, file_type=FileType.image, path="/p/f.jpg",
                   status=Status.completed, metadata={"width": 2000, "height": 3000})
    db.save(doc)
    result = Artifact(document_id=doc.id, artifact_type="transcription", provider="apple_vision",
                      ocr_geometry=OCRGeometryResult(provider="apple_vision", text="a\nb", rendition_id=rendition_id,
                                                     boxes=[OCRGeometryBox(text="a", bbox=FIRST, level="line"),
                                                            OCRGeometryBox(text="b", bbox=SECOND, level="line")]))
    db.save(result)
    ctx = ActionContext(actor="system", is_bootstrap=True)
    registry.invoke(db, "segment.convert_and_edit", {"document_id": doc.id}, ctx)
    return doc, db.get(Artifact, result.id)


def _move(db, segment_id, rect):
    segment = db.get(Segment, segment_id)
    segment.anchor = segment.anchor.model_copy(update={"rect": rect})
    db.save(segment)


def test_conversion_records_where_each_box_was(db):
    doc, result = _converted_page(db, rendition_id="crop-1")
    origins = sorted(db.query(ConvertedBoxOrigin, document_id=doc.id), key=lambda o: o.box_index)
    assert [(o.id, o.artifact_id, o.box_index, o.rect, o.rendition_id) for o in origins] == [
        (converted_segment_id(result.id, 0), result.id, 0, FIRST, "crop-1"),
        (converted_segment_id(result.id, 1), result.id, 1, SECOND, "crop-1"),
    ]


def test_a_mark_drawn_before_conversion_follows_its_box_without_the_block(db):
    """The point of the record: delete the result's block and the mark still finds its box."""
    doc, result = _converted_page(db)
    second = converted_segment_id(result.id, 1)
    _move(db, second, [0.3, 0.6, 0.4, 0.05])
    db.delete(result)  # what a person's delete will do once it is allowed

    resolved = resolve_anchor(db, SourceAnchor(document_id=doc.id, rect=SECOND))
    assert resolved.segment_id == second
    assert resolved.anchor.rect == [0.3, 0.6, 0.4, 0.05], "the box's CURRENT place"


def test_a_library_converted_before_origins_reads_the_same_then_gains_them_once(db):
    doc, result = _converted_page(db)
    for origin in db.query(ConvertedBoxOrigin, document_id=doc.id):
        db.delete(origin)  # a library converted before #5066
    anchor = SourceAnchor(document_id=doc.id, rect=FIRST)
    before = resolve_anchor(db, anchor)
    assert before.segment_id == converted_segment_id(result.id, 0), "the block still answers meanwhile"

    assert record_missing_box_origins(db) == 1
    assert len(db.query(ConvertedBoxOrigin, document_id=doc.id)) == 2
    assert resolve_anchor(db, anchor) == before, "the same answer from the record"
    assert record_missing_box_origins(db) == 0, "a later open reads nothing"


def test_recording_stops_between_results_when_asked(db):
    _converted_page(db)
    db.delete(db.all(ConvertedBoxOrigin)[0])
    assert record_missing_box_origins(db, should_stop=lambda: True) == 0


# --- `source.convert.a-converted-result-can-be-deleted` -----------------------------------------

def _delete(db, artifact_id):
    return registry.invoke(db, "artifact.delete", {"artifact_id": artifact_id}, ActionContext(actor="alice"))


def test_a_converted_result_can_be_deleted_and_the_page_keeps_its_boxes_words_and_marks(db, client):
    from fichero_server.models import SegmentPass

    doc, result = _converted_page(db)
    _delete(db, result.id)
    assert db.get(Artifact, result.id) is None

    pass_row = db.get(SegmentPass, result.geometry_superseded_by_pass_id)
    assert pass_row is not None and pass_row.deleted_at is None, "its pass stays"
    assert pass_row.source_artifact_type == "transcription", "kept for the label and the ranking"
    listing = client.get(f"/api/segments/document/{doc.id}").json()
    assert sorted(seg["text"] for seg in listing["segments"]) == ["a", "b"], "the words are the readings"
    assert listing["passes"][0]["artifact_type"] == "transcription"
    assert listing["passes"][0]["working"] is True
    resolved = resolve_anchor(db, SourceAnchor(document_id=doc.id, rect=FIRST))
    assert resolved.segment_id == converted_segment_id(result.id, 0), "a mark still finds its box"


def test_a_persons_corrected_result_keeps_its_rank_after_it_is_deleted(db):
    """The SACRED signal lived on the result: a person's reviewed result ranks as a person's. Deleting
    it must not demote their pass to a machine's, or the page's working pass and text would change."""
    from fichero_server.api.routes.document.segment_readings import _pass_candidates

    doc, result = _converted_page(db)
    result.reviewed = True
    db.save(result)
    before = {c.pass_id: c.has_human_segment for c in _pass_candidates(db, doc.id)}
    _delete(db, result.id)
    after = {c.pass_id: c.has_human_segment for c in _pass_candidates(db, doc.id)}
    assert before == after and any(after.values())


def test_undoing_the_delete_brings_the_result_back_exactly(db):
    from fichero_server.api.routes.system.actions_registry import undo_action  # noqa: F401
    from fichero_server.models import ActionAudit

    _doc, result = _converted_page(db)
    kept = db.get(Artifact, result.id).model_dump(mode="json")
    deleted = _delete(db, result.id)
    audit = db.get(ActionAudit, deleted.audit_id)
    reg = registry.get(audit.action_name)
    name, params = reg.invert(audit.before, audit.after, ActionContext(actor="alice"))
    registry.invoke(db, name, params, ActionContext(actor="alice"))
    assert db.get(Artifact, result.id).model_dump(mode="json")["ocr_geometry"] == kept["ocr_geometry"]


def test_a_deleted_result_comes_back_only_as_it_was(db):
    """#4990's invariant, moved: the block is never REWRITTEN. A snapshot of a deleted converted
    result whose boxes differ from where its boxes were recorded is refused by a single undo, and a
    bulk document restore brings the result back without those boxes rather than with them."""
    import pytest

    from fichero_server.api.routes.document.documents import restore_documents_impl
    from fichero_server.api.routes.document.segment_conversion import restored_artifact_row

    _doc, result = _converted_page(db)
    snapshot = db.get(Artifact, result.id).model_dump(mode="json")
    _delete(db, result.id)
    forged = dict(snapshot)
    forged["ocr_geometry"] = dict(snapshot["ocr_geometry"])
    forged["ocr_geometry"]["boxes"] = list(reversed(snapshot["ocr_geometry"]["boxes"]))

    with pytest.raises(Exception):
        restored_artifact_row(db, forged, refuse_different_boxes=True)
    restore_documents_impl(db, doc_ids=[], documents=[], artifacts=[forged])
    back = db.get(Artifact, result.id)
    assert back is not None and back.ocr_geometry is None


def test_a_result_whose_origins_are_not_recorded_yet_is_not_deleted(db):
    _doc, result = _converted_page(db)
    for origin in db.query(ConvertedBoxOrigin, artifact_id=result.id):
        db.delete(origin)
    import pytest

    with pytest.raises(Exception) as caught:
        _delete(db, result.id)
    assert "where their box was" in str(caught.value)
    assert db.get(Artifact, result.id) is not None
