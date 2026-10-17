"""source.store.never-converted-by-a-migration (docs/contributor_manual/specs/source/segments-and-geometry.md, #4924).

Spec: "no migration, script, second engine or command-line process ever writes a segment record into an existing
project; opening a project adds empty tables and columns and nothing else."
WHY: a whole project is converted only by the running app's engine, a page at a time; a project that opens and
closes must come back with the same (zero) segment rows, however old its results are.
Driven through the real store: a library with a legacy result (geometry on an artifact), closed and opened again.
"""
from __future__ import annotations

from fichero_server.db.manager import db_manager
from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
from fichero_server.models import Artifact, DocType, Document, FileType
from fichero_server.models.segments import Segment, SegmentPass


def test_source_store_never_converted_by_a_migration__opening_a_project_writes_no_segment(test_package):
    library = str(test_package)
    db = db_manager.get_database(library)
    doc = Document(name="legacy.png", doc_type=DocType.file, file_type=FileType.image, path="/nowhere/legacy.png")
    db.save(doc)
    db.save(Artifact(
        document_id=doc.id, artifact_type="transcription", content="Primero.", provider="qwen", model="qwen-vl-max",
        ocr_geometry=OCRGeometryResult(
            provider="qwen", model="qwen-vl-max", text="Primero.", rendition_id=None,
            boxes=[OCRGeometryBox(text="Primero.", bbox=[0.1, 0.1, 0.2, 0.05], level="line", char_start=0,
                                  char_end=8, page_index=0)])))
    before = (len(db.query(Segment)), len(db.query(SegmentPass)))
    assert before == (0, 0)

    for _ in range(2):  # opened twice: neither open converts anything
        db_manager.close_database(library)
        db = db_manager.get_database(library)
        assert (len(db.query(Segment)), len(db.query(SegmentPass))) == before
    assert db.query(Artifact, document_id=doc.id), "the legacy result is still there, unconverted"
