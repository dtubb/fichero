"""Importing a file Fichero exported adds no reading the file does not hold (#6803,
`source.format.reimport-adds-no-reading`).

WHY: an import derives an `expanded` reading from a line's abbreviation markup; the export wrote it as a
second reading; the next import read that second reading as written and derived a third from the markup, so
each round trip grew the page. The page is the one of `test_page_import_opens_abbreviations_5651`: a line
with an abbreviation and a line without.
"""

from __future__ import annotations

import pytest

from fichero_server.formats import write_page
from fichero_server.models import ContentRepresentation, DocType, Document, FileType, Status
from fichero_server.page_export import page_from_library
from tests.unit.api.test_page_import_opens_abbreviations_5651 import CUSTOM, PERSON, registry

pytestmark = pytest.mark.source_model

SUFFIX = {"pagexml": "page.xml", "tei": "tei.xml", "alto": "alto.xml"}


def _import(db, tmp_path, source) -> str:
    doc = Document(name="p.jpg", doc_type=DocType.file, file_type=FileType.image, path=str(tmp_path / "p.jpg"),
                   status=Status.completed)
    db.save(doc)
    registry.invoke(db, "format.import", {"document_id": doc.id, "path": str(source)}, PERSON)
    return doc.id


def _contents(db, doc_id) -> list[tuple[str | None, str]]:
    return sorted((r.level or "", r.content) for r in db.query(ContentRepresentation, document_id=doc_id)
                  if r.kind == "transcription")


@pytest.mark.parametrize("name", ["pagexml", "tei"])
def test_two_round_trips_through_a_library_add_no_reading(db, tmp_path, name):
    source = tmp_path / "custom.page.xml"
    source.write_text(CUSTOM, encoding="utf-8")
    doc_id = _import(db, tmp_path, source)
    first = _contents(db, doc_id)
    assert ("expanded", "que dicha Ana") in first      # the import's own derivation, kept
    for turn in range(2):
        page, _ = page_from_library(db, doc_id)
        data, _report = write_page(name, page)
        again = tmp_path / f"turn{turn}.{SUFFIX[name]}"
        again.write_bytes(data)
        doc_id = _import(db, tmp_path, again)
        back = _contents(db, doc_id)
        # TEI has no place for a reading's level, so the derived reading comes back as a written one.
        same = back == first if name == "pagexml" else sorted(c for _, c in back) == sorted(c for _, c in first)
        assert same, (turn + 1, name, back, first)
