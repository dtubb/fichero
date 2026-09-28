"""The Reader's typing messages land in the engine as the app sends them (#5154).

The app turns the served page's `lineEdited` / `lineSplit` / `lineJoin` into `representation.create`,
`segment.split` and `segment.merge` (`ReaderTextEdit`). This sends exactly those shapes -- through
`POST /api/actions/invoke`, the call the app makes -- on the real imported Syriac page.
"""

from __future__ import annotations

import fichero_server.api.main  # noqa: F401  (registers every action)
from tests.unit.api.test_page_text_follows_the_file import SYRIAC, _import


def _lines(client, doc_id: str) -> list[dict]:
    body = client.get(f"/api/segments/document/{doc_id}").json()
    real = next(p for p in body["passes"] if not p["provisional"])
    return sorted((s for s in body["segments"] if s["pass_id"] == real["id"] and s["kind"] == "line"),
                  key=lambda s: s["anchor"]["rect"])


def _invoke(client, name: str, params: dict):
    response = client.post("/api/actions/invoke", json={"name": name, "params": params})
    assert response.status_code == 200, response.text
    return response.json()


def test_typing_is_a_new_reading_correcting_the_one_typed_over(db, client):
    doc_id = _import(db, SYRIAC)
    line = _lines(client, doc_id)[0]
    [shown] = client.get(f"/api/segments/{line['id']}/readings").json()["items"]
    _invoke(client, "representation.create", {
        "document_id": doc_id, "segment_id": line["id"], "kind": "transcription",
        "content": shown["content"] + " typed", "corrects_representation_id": shown["id"],
    })
    items = client.get(f"/api/segments/{line['id']}/readings").json()["items"]
    assert len(items) == 2                                          # the old reading is kept
    assert next(i for i in items if i["id"] != shown["id"])["corrects_representation_id"] == shown["id"]


def test_return_splits_the_line_with_box_only_anchors_and_code_point_spans_and_backspace_joins_it(db, client):
    doc_id = _import(db, SYRIAC)
    line = _lines(client, doc_id)[0]
    [shown] = client.get(f"/api/segments/{line['id']}/readings").json()["items"]
    length = len(shown["content"])
    cut = length // 2
    x, y, w, h = line["anchor"]["rect"]
    anchor = {k: line["anchor"][k] for k in ("document_id", "space", "rotation", "granularity") if line["anchor"].get(k) is not None}
    split = _invoke(client, "segment.split", {
        "segment_id": line["id"], "expected_version": line["version"], "parts": [
            {"anchor": dict(anchor, rect=[x, y, w * cut / length, h]), "reading_span": [0, cut]},
            {"anchor": dict(anchor, rect=[x + w * cut / length, y, w * (1 - cut / length), h]), "reading_span": [cut, length]},
        ]})
    new_id = split["result"]["new_segment_ids"][0]
    after = {s["id"]: s for s in _lines(client, doc_id)}
    assert new_id in after and line["id"] in after
    first = client.get(f"/api/segments/{line['id']}/readings").json()["items"]
    second = client.get(f"/api/segments/{new_id}/readings").json()["items"]
    assert any(r["content"] == shown["content"][:cut] for r in first)
    assert any(r["content"] == shown["content"][cut:] for r in second)

    kept, joined = after[line["id"]], after[new_id]
    _invoke(client, "segment.merge", {
        "segment_ids": [kept["id"], joined["id"]], "keep_id": kept["id"],
        "expected_versions": {kept["id"]: kept["version"], joined["id"]: joined["version"]},
    })
    assert new_id not in {s["id"] for s in _lines(client, doc_id)}
