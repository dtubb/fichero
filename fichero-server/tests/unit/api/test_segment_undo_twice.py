"""⌘Z twice on one segment undoes both edits (found 2026-09-28 pinning Reshape's undo).

Each edit's inverse restores the version before it, checked against the version the edit made.
Undoing the newer edit is itself a restore, which bumps the version while putting back the older
edit's result, so the older edit's undo met a number it did not expect and was REFUSED (409): the
second ⌘Z of any two successive edits of one segment -- two moves, a reshape then a baseline, two
Segment-menu settings -- did nothing but fail. What breaks without these: a person's second ⌘Z.
What must NOT break: an undo is still refused when somebody ELSE changed the segment in between.
On the imported Syriac page, through the app's calls.
"""

from __future__ import annotations

import fichero_server.api.main  # noqa: F401  (registers every action)
from tests.unit.api.test_page_text_follows_the_file import SYRIAC, _import


def _first_line(db, client):
    doc_id = _import(db, SYRIAC)
    body = client.get(f"/api/segments/document/{doc_id}").json()
    real = next(p for p in body["passes"] if not p["provisional"])
    return min((s for s in body["segments"] if s["pass_id"] == real["id"] and s["kind"] == "line"),
               key=lambda s: s["anchor"]["rect"])


def _invoke(client, name, params):
    return client.post("/api/actions/invoke", json={"name": name, "params": params})


def _live(client, segment_id):
    return client.get(f"/api/segments/{segment_id}").json()["segment"]


def _moved(line, by):
    anchor = {k: line["anchor"].get(k) for k in ("document_id", "page_id", "rendition_id", "space", "rotation",
                                                  "granularity", "polygon")}
    rect = line["anchor"]["rect"]
    return dict(anchor, rect=[rect[0] + by, rect[1], rect[2], rect[3]])


def test_two_edits_of_one_segment_undo_newest_first_and_both_land(db, client):
    line = _first_line(db, client)
    first = _invoke(client, "segment.update", {"segment_id": line["id"], "expected_version": line["version"],
                                               "anchor": _moved(line, 0.01)}).json()
    fewer = line["baseline"][:1] + line["baseline"][2:]
    second = _invoke(client, "segment.update", {"segment_id": line["id"], "expected_version": line["version"] + 1,
                                                "baseline": fewer}).json()
    assert client.post(f"/api/actions/audit/{second['audit_id']}/undo").status_code == 200
    assert _live(client, line["id"])["baseline"] == line["baseline"]
    undone = client.post(f"/api/actions/audit/{first['audit_id']}/undo")
    assert undone.status_code == 200, undone.text
    assert _live(client, line["id"])["anchor"]["rect"] == line["anchor"]["rect"], "both edits undone"


def test_an_undo_is_still_refused_when_somebody_else_changed_the_segment_in_between(db, client):
    line = _first_line(db, client)
    first = _invoke(client, "segment.update", {"segment_id": line["id"], "expected_version": line["version"],
                                               "anchor": _moved(line, 0.01)}).json()
    second = _invoke(client, "segment.update", {"segment_id": line["id"], "expected_version": line["version"] + 1,
                                                "kind": "heading"}).json()
    assert client.post(f"/api/actions/audit/{second['audit_id']}/undo").status_code == 200
    current = _live(client, line["id"])
    other = _invoke(client, "segment.update", {"segment_id": line["id"], "expected_version": current["version"],
                                               "language": "syc"})
    assert other.status_code == 200, other.text
    refused = client.post(f"/api/actions/audit/{first['audit_id']}/undo")
    assert refused.status_code == 409, "their change is not undone out from under them"
    assert _live(client, line["id"])["language"] == "syc"


def test_two_selection_wide_settings_undo_twice(db, client):
    line = _first_line(db, client)
    first = _invoke(client, "segment.update_many", {"updates": [
        {"segment_id": line["id"], "expected_version": line["version"], "language": "syc"}]}).json()
    second = _invoke(client, "segment.update_many", {"updates": [
        {"segment_id": line["id"], "expected_version": line["version"] + 1, "script": "Syrc"}]}).json()
    assert client.post(f"/api/actions/audit/{second['audit_id']}/undo").status_code == 200
    undone = client.post(f"/api/actions/audit/{first['audit_id']}/undo")
    assert undone.status_code == 200, undone.text
    after = _live(client, line["id"])
    assert (after["language"], after["script"]) == (line.get("language"), line.get("script"))
