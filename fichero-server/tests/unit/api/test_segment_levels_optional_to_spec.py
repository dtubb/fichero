"""source.segment.levels-optional (docs/contributor_manual/specs/source/segments-and-geometry.md, #4927).

Spec: "any level may be absent; adding word segments under a line changes no id, shape or reading of the line or its
region."
Through the real segment routes: a region holding a line (no words); words are then added under the line; the region and
the line are the same rows, byte for byte.
"""
from __future__ import annotations

from fichero_server.models import Segment
from tests.unit.api.test_segments_write_actions import _create_pass, _create_segment, _make_doc


def test_source_segment_levels_optional__words_added_under_a_line_change_nothing_of_the_line_or_its_region(client, db):
    doc = _make_doc(db)
    pass_id = _create_pass(client, doc.id)["id"]
    region = _create_segment(client, document_id=doc.id, pass_id=pass_id, kind="region",
                             anchor={"document_id": doc.id, "rect": [0.05, 0.05, 0.9, 0.3]}).json()
    line = _create_segment(client, document_id=doc.id, pass_id=pass_id, kind="line", parent_segment_id=region["id"],
                           anchor={"document_id": doc.id, "rect": [0.1, 0.1, 0.8, 0.05]}).json()
    assert [s.kind for s in db.query(Segment, pass_id=pass_id) if s.kind == "word"] == [], "the word level is absent"
    before = {i: db.get(Segment, i).model_dump(mode="json") for i in (region["id"], line["id"])}

    for x in (0.1, 0.3, 0.5):
        made = _create_segment(client, document_id=doc.id, pass_id=pass_id, kind="word", parent_segment_id=line["id"],
                               anchor={"document_id": doc.id, "rect": [x, 0.1, 0.15, 0.05]})
        assert made.status_code == 200, made.text

    assert {i: db.get(Segment, i).model_dump(mode="json") for i in before} == before
    assert len([s for s in db.query(Segment, pass_id=pass_id) if s.kind == "word"]) == 3
