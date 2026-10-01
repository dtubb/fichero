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
