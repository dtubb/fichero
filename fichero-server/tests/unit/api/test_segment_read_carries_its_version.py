"""The app can edit a segment safely: the list it reads carries each segment's version (#5152).

Editing an imported page's boxes goes through `segment.update` / `segment.delete` / `segment.merge`,
which take `expected_version` so a stale edit is REFUSED (`source.edit.stale-is-refused`) rather than
overwriting somebody's change. The app's only read of a page's segments is the list route, and it did
not say the version -- so the app could not make a safe edit at all. These go through the exact
calls the app makes: the list route, then `POST /api/actions/invoke`.
"""

from __future__ import annotations

import fichero_server.api.main  # noqa: F401  (registers every action)
from tests.unit.api.test_page_text_follows_the_file import SYRIAC, _import


def _segments(client, doc_id: str) -> list[dict]:
    body = client.get(f"/api/segments/document/{doc_id}").json()
    real = next(p for p in body["passes"] if not p["provisional"])
    return [s for s in body["segments"] if s["pass_id"] == real["id"]]


def _move(client, segment: dict, expected_version: int):
    anchor = dict(segment["anchor"])
    x, y, w, h = anchor["rect"]
    anchor["rect"] = [x + 0.01, y, w, h]
    anchor.pop("polygon", None)
    return client.post("/api/actions/invoke", json={"name": "segment.update", "params": {
        "segment_id": segment["id"], "expected_version": expected_version, "anchor": anchor,
    }})


def test_every_real_segment_says_its_version_and_an_edit_with_it_lands(db, client):
    doc_id = _import(db, SYRIAC)
    segments = _segments(client, doc_id)
    assert segments and all(s["version"] == 1 for s in segments)

    line = next(s for s in segments if s["kind"] == "line")
    moved = _move(client, line, line["version"])
    assert moved.status_code == 200, moved.text
    assert moved.json()["ok"] and moved.json()["audit_id"]          # what ⌘Z inverts
    after = next(s for s in _segments(client, doc_id) if s["id"] == line["id"])
    assert after["version"] == 2
    assert abs(after["anchor"]["rect"][0] - (line["anchor"]["rect"][0] + 0.01)) < 1e-9


def test_an_edit_with_the_version_it_read_before_someone_else_s_is_refused(db, client):
    doc_id = _import(db, SYRIAC)
    line = next(s for s in _segments(client, doc_id) if s["kind"] == "line")
    assert _move(client, line, line["version"]).status_code == 200
    stale = _move(client, line, line["version"])                    # the version it read, now old
    assert stale.status_code == 409, stale.text
