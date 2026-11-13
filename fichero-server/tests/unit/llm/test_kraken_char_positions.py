"""Kraken's character positions are kept on the reading.

Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.char-positions-kept` (when Kraken reads a
line, where each character starts along the baseline is kept on the reading as `char_positions`, beside
`char_confidences`; a reader that gives none leaves it absent, never faked). The record is a real Kraken
`BaselineOCRRecord`, so the cut format is Kraken's own; the reading goes through the real writer and action.
"""

from __future__ import annotations

import pytest

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.llm import kraken_runtime
from fichero_server.llm.working_lines import character_facts, write_readings
from fichero_server.models import ContentRepresentation
from tests.unit.api.test_reader_directions import SYRIAC, _import

containers = pytest.importorskip("kraken.containers")


def _record(text: str, cuts: list[tuple[int, int]]):
    line = containers.BaselineLine(
        id="l1", baseline=[[0, 20], [100, 20]], boundary=[[0, 0], [100, 0], [100, 30], [0, 30]],
    )
    return containers.BaselineOCRRecord(text, cuts, [0.9] * len(text), line)


def test_each_character_starts_where_kraken_cut_it_along_the_baseline():
    record = _record("abcd", [(0, 20), (20, 45), (45, 70), (70, 100)])

    assert kraken_runtime.char_positions(record) == pytest.approx([0.0, 0.2, 0.45, 0.7], abs=0.011)


def test_a_record_with_no_cuts_or_too_few_gives_none_never_a_guess():
    class Bare:
        prediction = "abc"

    assert kraken_runtime.char_positions(Bare()) is None
    assert kraken_runtime.char_positions(_record("abc", [(0, 50), (50, 100)])) is None


def test_a_read_line_carries_its_positions_and_the_writer_keeps_them_on_the_reading(db):
    doc_id = _import(db, SYRIAC)
    line = next(r.segment_id for r in db.query(ContentRepresentation, document_id=doc_id) if r.segment_id)
    read = kraken_runtime.ReadLine(" abc", confidence=0.8, char_confidences=[0.5, 0.9, 0.8, 0.7],
                                   char_positions=[0.0, 0.1, 0.4, 0.7])

    (made,) = write_readings(db, document_id=doc_id, readings=[(line, read, read.confidence, character_facts(read))],
                             artifact_id=None, run_id=None)

    reading = db.get(ContentRepresentation, made)
    assert reading.content == "abc"
    # The leading space the writer stripped takes its position with it.
    assert reading.char_positions == [0.1, 0.4, 0.7]
    assert reading.char_confidences == [0.9, 0.8, 0.7]


def test_a_reading_from_a_reader_that_gives_no_positions_has_none(db):
    doc_id = _import(db, SYRIAC)
    line = next(r.segment_id for r in db.query(ContentRepresentation, document_id=doc_id) if r.segment_id)

    (made,) = write_readings(db, document_id=doc_id, readings=[(line, "abc", 0.8)], artifact_id=None, run_id=None)

    assert db.get(ContentRepresentation, made).char_positions is None


def test_return_in_a_line_with_positions_cuts_where_the_character_starts_and_says_measured(db, client):
    """`segment.split(at_offset)` reads the positions: the box is cut where the character starts, not in proportion."""
    from fichero_server.actions.registry import ActionContext, registry
    from fichero_server.models import DocType, Document, FileType, Segment, Status

    doc = Document(name="folio.jpg", doc_type=DocType.file, file_type=FileType.image, path="/path/folio.jpg",
                   status=Status.completed)
    db.save(doc)
    pass_id = client.post("/api/segments/passes", json={"document_id": doc.id, "name": "lines"}).json()["id"]
    line = client.post("/api/segments", json={
        "document_id": doc.id, "pass_id": pass_id, "kind": "line",
        "anchor": {"document_id": doc.id, "rect": [0.0, 0.2, 1.0, 0.05]},
    }).json()["id"]
    person = ActionContext(actor="historian", library_path=None, is_bootstrap=True)
    made = registry.invoke(db, "representation.create", {
        "document_id": doc.id, "segment_id": line, "kind": "transcription", "content": "en el"}, person).result["id"]
    reading = db.get(ContentRepresentation, made)
    reading.char_positions = [0.0, 0.1, 0.2, 0.6, 0.7]
    db.save(reading)

    result = registry.invoke(db, "segment.split", {
        "segment_id": line, "at_offset": 3, "expected_version": db.get(Segment, line).version}, person).result

    kept, new = db.get(Segment, result["kept_id"]), db.get(Segment, result["new_segment_ids"][0])
    assert kept.anchor.rect == pytest.approx([0.0, 0.2, 0.6, 0.05])
    assert new.anchor.rect == pytest.approx([0.6, 0.2, 0.4, 0.05])
    assert kept.metadata["cut"] == new.metadata["cut"] == "measured"
