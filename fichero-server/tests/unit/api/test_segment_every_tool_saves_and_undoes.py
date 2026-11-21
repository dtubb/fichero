"""Every segment tool's edit is saved and undoable: sent through the actions door as the app sends it, read back by the
page read the app reloads with, and taken back by one undo.

Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.every-tool-works` (every tool in the segment
toolbar does its job on a real page, its result is saved, surviving a reload, and undoable; a test per tool that drives
its commit path and checks the stored segments). This is the engine half: the request each tool's commit sends
(`SegmentEditRunner` -> `POST /api/actions/invoke`), then `GET /api/segments/document/{doc_id}`, then
`POST /api/actions/audit/{audit_id}/undo` and the read again. The app's gestures are not driven here.
"""
from __future__ import annotations

import pytest

from tests.unit.api.test_regenerate_outline import H, W, _page
from tests.unit.api.test_segment_create_from_stroke import _wobbly

pytestmark = pytest.mark.source_model


def _box(x, y, w, h):
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def _invoke(client, name, params):
    response = client.post("/api/actions/invoke", json={"name": name, "params": params})
    assert response.status_code == 200, response.text
    return response.json()


def _reload(client, doc) -> dict[str, dict]:
    """The page's live segments as the app reads them on opening the page: {id: segment}."""
    response = client.get(f"/api/segments/document/{doc.id}")
    assert response.status_code == 200, response.text
    return {row["id"]: row for row in response.json()["segments"]}


def _undo(client, done):
    response = client.post(f"/api/actions/audit/{done['audit_id']}/undo")
    assert response.status_code == 200, response.text


def _line(client, doc, pass_id, y):
    return _invoke(client, "segment.create", {
        "document_id": doc.id, "pass_id": pass_id, "kind": "line",
        "anchor": {"document_id": doc.id, "polygon": _box(0.1, y, 0.8, 0.05)},
        "baseline": [[0.1, y + 0.04], [0.9, y + 0.04]],
    })["result"]["segment_ids"][0]


def _version(client, doc, sid) -> int:
    return _reload(client, doc)[sid]["version"]


def test_the_box_tool_s_segment_is_saved_and_one_undo_takes_it_away(db, client):
    doc, pass_id = _page(db, client, [])

    done = _invoke(client, "segment.create", {
        "document_id": doc.id, "pass_id": pass_id, "kind": "region",
        "anchor": {"document_id": doc.id, "rect": [0.1, 0.1, 0.3, 0.2]},
    })
    [made] = done["result"]["segment_ids"]

    assert _reload(client, doc)[made]["kind"] == "region"
    _undo(client, done)
    assert made not in _reload(client, doc)


def test_the_marker_s_closed_stroke_is_saved_and_one_undo_takes_it_away(db, client):
    doc, pass_id = _page(db, client, [])
    loop = _wobbly([(100, 100), (500, 100), (500, 300), (100, 300), (100, 100)])

    done = _invoke(client, "segment.create", {
        "document_id": doc.id, "pass_id": pass_id, "kind": "region", "smoothing": 0.5,
        "anchor": {"document_id": doc.id, "polygon": loop},
    })
    [made] = done["result"]["segment_ids"]

    assert 4 <= len(_reload(client, doc)[made]["anchor"]["polygon"]) <= 8
    _undo(client, done)
    assert made not in _reload(client, doc)


def test_the_line_brush_s_stroke_is_saved_as_a_line_and_one_undo_takes_it_away(db, client):
    doc, pass_id = _page(db, client, [])
    stroke = [[(100 + i) / W, 200 / H, 30] for i in range(0, 600, 2)]

    done = _invoke(client, "segment.create", {
        "document_id": doc.id, "pass_id": pass_id, "kind": "line", "brush_stroke": stroke,
        "anchor": {"document_id": doc.id, "shapes": [{"kind": "path", "points": [p[:2] for p in stroke]}]},
    })
    [made] = done["result"]["segment_ids"]

    saved = _reload(client, doc)[made]
    assert saved["kind"] == "line" and len(saved["baseline"]) == 2
    _undo(client, done)
    assert made not in _reload(client, doc)


def test_the_knife_s_cut_is_saved_as_two_lines_and_one_undo_puts_back_the_one(db, client):
    doc, pass_id = _page(db, client, [])
    line = _line(client, doc, pass_id, 0.2)
    polygon = _reload(client, doc)[line]["anchor"]["polygon"]

    done = _invoke(client, "segment.split", {
        "cut_path": [[0.5, 0.15], [0.5, 0.3]], "expected_versions": {line: _version(client, doc, line)},
    })
    [split] = done["result"]["splits"]

    saved = _reload(client, doc)
    assert {line, *split["new_segment_ids"]} <= saved.keys() and len(split["new_segment_ids"]) == 1
    _undo(client, done)
    after = _reload(client, doc)
    assert split["new_segment_ids"][0] not in after
    assert after[line]["anchor"]["polygon"] == polygon


def test_combine_s_join_is_saved_as_one_line_and_one_undo_puts_back_both(db, client):
    doc, pass_id = _page(db, client, [])
    a, b = _line(client, doc, pass_id, 0.2), _line(client, doc, pass_id, 0.26)

    done = _invoke(client, "segment.merge", {
        "segment_ids": [a, b], "keep_id": a,
        "expected_versions": {a: _version(client, doc, a), b: _version(client, doc, b)},
        "join_geometry": True, "move_into_region": True,
    })

    saved = _reload(client, doc)
    assert a in saved and b not in saved
    _undo(client, done)
    assert {a, b} <= _reload(client, doc).keys()


def test_a_drag_s_move_is_saved_and_one_undo_puts_it_back(db, client):
    doc, pass_id = _page(db, client, [])
    line = _line(client, doc, pass_id, 0.2)
    polygon = _reload(client, doc)[line]["anchor"]["polygon"]

    done = _invoke(client, "segment.translate", {
        "segments": [{"segment_id": line, "expected_version": _version(client, doc, line)}], "dx": 0.0, "dy": 0.1,
    })

    assert _reload(client, doc)[line]["anchor"]["polygon"][0] == pytest.approx([0.1, 0.3])
    _undo(client, done)
    assert _reload(client, doc)[line]["anchor"]["polygon"] == polygon


def test_delete_is_saved_and_one_undo_brings_the_segment_back(db, client):
    doc, pass_id = _page(db, client, [])
    line = _line(client, doc, pass_id, 0.2)

    done = _invoke(client, "segment.delete", {
        "segment_ids": [line], "expected_versions": {line: _version(client, doc, line)},
    })

    assert line not in _reload(client, doc)
    _undo(client, done)
    assert line in _reload(client, doc)
