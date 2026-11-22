"""Every writer names the editorial facts and the names and dates it cannot carry (#6800,
`source.format.undeclared-losses-are-declared`).

WHY: measured 2026-11-20, a line with a `deleted` and an `unclear` fact went to TEI as `<del>` and
`<unclear>`, to PAGE XML with the `unclear` in `custom` and the deletion named lost, and to ALTO with
neither and no loss named; the record's names and dates on a line were dropped by ALTO and PAGE XML
with nothing said. The page is the record-export page (`test_export_reads_the_record.library`: three
lines imported from PAGE XML, a person, a place and a date standing on them), with two editorial
facts recorded on its first line.
"""

from __future__ import annotations

import pytest

from fichero_server.api.routes.document.segment_readings import readings_of_segment
from fichero_server.formats import write_page
from fichero_server.models.editorial import EditorialFact, EditorialFactKind
from fichero_server.page_export import page_from_library
from tests.unit.core.test_export_reads_the_record import LINES, library  # noqa: F401  (fixture)

NAMES = "names and dates"


@pytest.fixture
def page(db, library):  # noqa: F811
    first = library["lines"][0]
    (reading,) = [r for r in readings_of_segment(db, first.segment_id) if r.kind == "transcription"]
    assert reading.content == LINES[0]
    for kind, start, end in ((EditorialFactKind.deleted, 3, 9), (EditorialFactKind.unclear, 12, 13)):
        db.save(EditorialFact(segment_id=first.segment_id, kind=kind, representation_id=reading.id,
                              char_start=start, char_end=end))
    built, _ = page_from_library(db, library["doc"].id)
    return built


@pytest.mark.parametrize("name", ["alto", "hocr", "yolo"])
def test_a_format_with_no_place_for_them_names_every_editorial_fact_and_every_name(page, name):
    _data, report = write_page(name, page)
    counts = {loss.what: loss.count for loss in report.losses}
    assert counts.get("a 'deleted' editorial mark") == 1, report.as_dict()
    assert counts.get("a 'unclear' editorial mark") == 1, report.as_dict()
    # Pedro Ruiz, Quibdó and the date: the unanchored name stands on no line and is not on the page.
    assert counts.get(NAMES) == 3, report.as_dict()


def test_page_xml_names_the_names_and_the_deletion_and_carries_the_unclear(page):
    data, report = write_page("pagexml", page)
    counts = {loss.what: loss.count for loss in report.losses}
    assert counts.get(NAMES) == 3, report.as_dict()
    assert counts.get("a 'deleted' editorial mark") == 1, report.as_dict()
    assert "a 'unclear' editorial mark" not in counts
    assert b"unclear {offset:12; length:1;}" in data


def test_tei_writes_them_and_names_none_of_them_lost(page):
    data, report = write_page("tei", page)
    assert NAMES not in report.lost and not any("editorial mark" in what for what in report.lost)
    assert b"<del" in data and b"<unclear" in data and b"<persName" in data
