"""A file says who made each line's reading, and importing it restores a person's authorship (#6802:
`source.format.who-made-it-out`, `source.format.round-trip-through-a-library`, `source.format.alto-out`).

WHY: PAGE and TEI named the pass's maker only, ALTO named nobody, and a library page exported and imported
again came back with a person's reading stamped as the file's (`external_import`), so the person's lines were
counted as unreviewed machine lines. The page is the record-export page: line 1 a person's reading, line 2 a
machine's (a model), line 3 withdrawn. Exported through the one page exporter, imported through `format.import`
into a fresh page, and read out of the library again.
"""
from __future__ import annotations

import datetime

import pytest

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.document.segment_readings import readings_of_segment
from fichero_server.formats import write_page
from fichero_server.models import ContentRepresentation, DocType, Document, FileType, Status
from fichero_server.models.knowledge import ProvenanceKind
from fichero_server.page_export import page_from_library
from tests.unit.core.test_export_reads_the_record import LINES, library  # noqa: F401  (fixture)

# The embedder is the test one: saving an entity must not load the pinned model (#5188, #5530).
pytestmark = pytest.mark.usefixtures("hashed_text_embedder")

pytestmark = pytest.mark.source_model

BOOT = ActionContext(actor="importer", library_path=None, is_bootstrap=True)
SUFFIX = {"alto": "alto.xml", "pagexml": "page.xml", "tei": "tei.xml"}
#: What each format's file holds for line 1's person, as bytes.
PERSON_MARK = {
    "pagexml": b"fichero-maker {by:person; name:Ana%20Ruiz;}",
    "alto": b'LABEL="maker:person" DESCRIPTION="Ana Ruiz"',
    "tei": b"<name>Ana Ruiz</name>",
}


@pytest.fixture
def made(db, library):  # noqa: F811
    first, second, third = library["lines"]
    for span, edit in ((first, {"provenance_kind": ProvenanceKind.human, "created_by": "Ana Ruiz"}),
                       (second, {"provenance_kind": ProvenanceKind.workflow, "producer_model": "vision-model"}),
                       (third, {"retracted_at": datetime.datetime.now(datetime.timezone.utc)})):
        (reading,) = [r for r in readings_of_segment(db, span.segment_id) if r.kind == "transcription"]
        stored = db.get(ContentRepresentation, reading.id)
        for name, value in edit.items():
            setattr(stored, name, value)
        db.save(stored)
    return library


def _first_readings(db, document_id):
    page, _ = page_from_library(db, document_id)
    return page, [s for s in page.segments if s.kind == "line"]


@pytest.mark.parametrize("name", ["pagexml", "alto", "tei"])
def test_a_file_says_who_made_each_reading_and_an_import_restores_the_person(db, made, tmp_path, name):
    sent, lines = _first_readings(db, made["doc"].id)
    assert [line.reading_maker for line in lines[:2]] == [
        {"type": "Person", "name": "Ana Ruiz"}, {"type": "Software", "name": "vision-model"}]
    data, _report = write_page(name, sent)
    assert PERSON_MARK[name] in data
    if name == "alto":
        assert sent.producer and f"<softwareName>{sent.producer}</softwareName>".encode() in data

    path = tmp_path / f"acta.{SUFFIX[name]}"
    path.write_bytes(data)
    fresh = Document(name="acta.jpg", doc_type=DocType.file, file_type=FileType.image,
                     path=made["doc"].path, status=Status.completed)
    db.save(fresh)
    registry.invoke(db, "format.import", {"document_id": fresh.id, "path": str(path)}, BOOT)

    back, back_lines = _first_readings(db, fresh.id)
    assert back_lines[0].reading_maker == {"type": "Person", "name": "Ana Ruiz"}
    assert back_lines[1].reading_maker is None
    stored = [r for r in db.query(ContentRepresentation, document_id=fresh.id)
              if r.kind == "transcription" and r.content == LINES[0]]
    assert [(r.provenance_kind, r.created_by) for r in stored if r.level is None] == [(ProvenanceKind.human, "Ana Ruiz")]
    # The second export carries the person's mark again.
    again, _ = write_page(name, back)
    assert PERSON_MARK[name] in again
