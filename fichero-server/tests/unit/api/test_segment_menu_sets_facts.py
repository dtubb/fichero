"""The Segment menu's request lands, and undoes (#5157).

The app's Segment menu sends ONE `segment.update_many` for a whole selection, each row carrying only
the fact being set and the version the app read (`SegmentEdit.set`). This sends exactly that shape
through the call the app makes -- `POST /api/actions/invoke` -- on the real imported Syriac page, and
undoes it through the audit trail.
"""

from __future__ import annotations

import fichero_server.api.main  # noqa: F401  (registers every action)
from tests.unit.api.test_page_text_follows_the_file import SYRIAC, _import


def _lines(client, doc_id: str) -> list[dict]:
    body = client.get(f"/api/segments/document/{doc_id}").json()
    real = next(p for p in body["passes"] if not p["provisional"])
    return sorted((s for s in body["segments"] if s["pass_id"] == real["id"] and s["kind"] == "line"),
                  key=lambda s: s["anchor"]["rect"])


def test_setting_direction_on_two_lines_is_one_action_and_one_undo(db, client):
    doc_id = _import(db, SYRIAC)
    first, second = _lines(client, doc_id)[:2]
    sent = client.post("/api/actions/invoke", json={"name": "segment.update_many", "params": {"updates": [
        {"segment_id": first["id"], "expected_version": first["version"], "direction": "rtl"},
        {"segment_id": second["id"], "expected_version": second["version"], "direction": "rtl"},
    ]}})
    assert sent.status_code == 200, sent.text
    after = {s["id"]: s for s in _lines(client, doc_id)}
    assert after[first["id"]]["direction"] == "rtl" and after[second["id"]]["direction"] == "rtl"
    assert after[first["id"]]["version"] == first["version"] + 1

    undone = client.post(f"/api/actions/audit/{sent.json()['audit_id']}/undo")
    assert undone.status_code == 200, undone.text
    back = {s["id"]: s for s in _lines(client, doc_id)}
    assert back[first["id"]]["direction"] == first["direction"]
    assert back[second["id"]]["direction"] == second["direction"]


def test_a_direction_the_engine_does_not_know_is_refused(db, client):
    doc_id = _import(db, SYRIAC)
    line = _lines(client, doc_id)[0]
    sent = client.post("/api/actions/invoke", json={"name": "segment.update_many", "params": {"updates": [
        {"segment_id": line["id"], "expected_version": line["version"], "direction": "sideways"},
    ]}})
    assert sent.status_code == 422, sent.text
