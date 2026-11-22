"""A segment's own type and the confidences on a library page reach the writers (#6801,
`source.format.kind-raw-out`, `source.format.confidence-out`).

WHY: `page_export.page_from_library` copied neither `Segment.kind_raw` nor a shape's or a reading's
machine confidence onto `PageSegment`, so no writer could write them and none could say it dropped
them. The page is the record-export page (three lines imported from PAGE XML). Its first line gets the
type `DefaultLine`, a shape confidence of 0.83 and a reading confidence of 0.91; its second line gets
a type only; its third line is left as imported.
"""

from __future__ import annotations

import pytest

from fichero_server.formats import write_page
from fichero_server.models import ContentRepresentation, Segment
from fichero_server.page_export import page_from_library
from tests.unit.core.test_export_reads_the_record import library  # noqa: F401  (fixture)

pytestmark = pytest.mark.source_model

SHAPE = "a shape's confidence"
READING = "a reading's confidence"


def _counts(report) -> dict[str, int]:
    return {loss.what: loss.count for loss in report.losses}


@pytest.fixture
def typed(db, library):  # noqa: F811
    from fichero_server.api.routes.document.segment_readings import readings_of_segment

    first, second = library["lines"][0], library["lines"][1]
    row = db.get(Segment, first.segment_id)
    row.kind_raw, row.confidence = "DefaultLine", 0.83
    db.save(row)
    row = db.get(Segment, second.segment_id)
    row.kind_raw = "MarginTextZone"
    db.save(row)
    (reading,) = [r for r in readings_of_segment(db, first.segment_id) if r.kind == "transcription"]
    stored = db.get(ContentRepresentation, reading.id)
    stored.machine_confidence = 0.91
    db.save(stored)
    built, _ = page_from_library(db, library["doc"].id)
    return built


def test_the_library_page_hands_the_writers_the_type_and_both_confidences(typed):
    first, second, third = [s for s in typed.segments if s.kind == "line"]
    assert (first.kind_raw, first.confidence, first.reading_confidence) == ("DefaultLine", 0.83, 0.91)
    assert (second.kind_raw, second.confidence, second.reading_confidence) == ("MarginTextZone", None, None)
    assert (third.kind_raw, third.confidence, third.reading_confidence) == (None, None, None)


def test_page_xml_writes_the_type_in_custom_and_both_confidences(typed):
    data, report = write_page("pagexml", typed)
    assert b"structure {type:DefaultLine;}" in data
    assert b"structure {type:MarginTextZone;}" in data
    assert b'conf="0.83"' in data and b'conf="0.91"' in data
    assert SHAPE not in report.lost and READING not in report.lost


def test_alto_declares_the_type_as_a_tag_the_element_references(typed):
    data, report = write_page("alto", typed)
    assert b'LABEL="DefaultLine"' in data and b'LABEL="MarginTextZone"' in data
    assert b'TAGREFS="' in data
    assert b'WC="0.91"' in data          # the line's own String
    assert _counts(report)[SHAPE] == 1   # ALTO has no confidence on a block or a line
    assert READING not in report.lost


def test_tei_writes_the_type_on_the_zone_and_names_both_confidences_lost(typed):
    data, report = write_page("tei", typed)
    assert b'type="DefaultLine"' in data and b'type="MarginTextZone"' in data
    assert _counts(report)[SHAPE] == 1 and _counts(report)[READING] == 1
