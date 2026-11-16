"""#6412: segments added in the Preview editor are saved (source/segment-editor-crud.md, `segment-editor.*`).

The Preview's draw sends `segment.create` on the shown pass (a region by polygon, a line by baseline into the
region holding it). The rows must reach the library database: still there after the library is closed and opened
again, listed for the document, and one audited create each with one undo.
"""
from __future__ import annotations

import pytest

from fichero_server.db.manager import db_manager
from fichero_server.models import ActionAudit
from fichero_server.models.segments import Segment
from tests.unit.api.test_regenerate_outline import _page

pytestmark = pytest.mark.source_model

SQUARE = [[0.1, 0.1], [0.6, 0.1], [0.6, 0.5], [0.1, 0.5]]


def _create(client, doc, pass_id, **body):
    response = client.post("/api/segments", json={"document_id": doc.id, "pass_id": pass_id, **body})
    assert response.status_code == 200, response.text
    return response.json()["id"]


def test_regions_and_lines_drawn_in_the_preview_survive_closing_the_library(db, client, test_package):
    doc, pass_id = _page(db, client, [])
    region = _create(client, doc, pass_id, kind="region",
                     anchor={"document_id": doc.id, "rect": [0.1, 0.1, 0.5, 0.4], "polygon": SQUARE})
    line = _create(client, doc, pass_id, kind="line", parent_segment_id=region,
                   baseline=[[0.15, 0.3], [0.55, 0.3]],
                   anchor={"document_id": doc.id, "shapes": [{"kind": "path", "points": [[0.15, 0.3], [0.55, 0.3]]}]})

    db_manager.close_all()
    reopened = db_manager.get_database(test_package)

    rows = {row.id: row for row in reopened.query(Segment, document_id=doc.id) if row.deleted_at is None}
    assert set(rows) == {region, line}
    assert rows[line].parent_segment_id == region
    listed = client.get(f"/api/segments/document/{doc.id}").json()
    assert {s["id"] for s in listed["segments"]} >= {region, line}


def test_each_drawn_segment_is_one_audited_create_and_one_undo_removes_it(db, client):
    doc, pass_id = _page(db, client, [])
    region = _create(client, doc, pass_id, kind="region",
                     anchor={"document_id": doc.id, "rect": [0.1, 0.1, 0.5, 0.4], "polygon": SQUARE})
    creates = [a for a in db.all(ActionAudit) if a.action_name == "segment.create"]
    assert len(creates) == 1
    response = client.post(f"/api/actions/audit/{creates[0].id}/undo")
    assert response.status_code == 200, response.text
    assert db.get(Segment, region).deleted_at is not None
