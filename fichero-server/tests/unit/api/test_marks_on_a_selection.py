"""A mark attaches to the SELECTION (Q6, ruled 2026-09-27): the selected segments, each with the
stretch of its reading it covers, or -- as before -- to an area drawn over the page.

Real segments: the Clm 13027 38r page imported through the library. What breaks without these: a
highlight on a selection that remembers only a rectangle (so it cannot follow its words, and cannot
export as ONE PDF markup annotation with a quad per run), or a mark attached to another page's line.
"""

from __future__ import annotations

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.models import Segment
from tests.unit.api.test_page_text_follows_the_file import CLM, _import


def _lines(db, doc_id: str) -> list[Segment]:
    return sorted((s for s in db.all(Segment) if s.document_id == doc_id and s.kind == "line"),
                  key=lambda s: s.metadata["file_position"])


def test_a_highlight_on_two_selected_lines_keeps_them_and_is_drawn_over_both(db, client):
    doc_id = _import(db, CLM)
    first, second = _lines(db, doc_id)[:2]
    response = client.post("/api/annotations", json={
        "document_id": doc_id, "kind": "highlight",
        "targets": [{"segment_id": first.id, "char_start": 0, "char_end": 7},
                    {"segment_id": second.id}],
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert [t["segment_id"] for t in body["targets"]] == [first.id, second.id]
    assert body["targets"][0]["char_start"] == 0 and body["targets"][0]["char_end"] == 7
    # Drawn at the union of the two lines' boxes.
    left, top, width, height = body["anchor"]["rect"]
    for line in (first, second):
        x, y, w, h = line.anchor.rect
        assert left <= x + 1e-9 and top <= y + 1e-9
        assert x + w <= left + width + 1e-9 and y + h <= top + height + 1e-9


def test_a_mark_drawn_over_an_area_is_unchanged(db, client):
    doc_id = _import(db, CLM)
    response = client.post("/api/annotations", json={
        "document_id": doc_id, "kind": "highlight",
        "anchor": {"document_id": doc_id, "rect": [0.1, 0.1, 0.2, 0.05]},
    })
    assert response.status_code == 200, response.text
    assert response.json()["targets"] == []
    assert response.json()["anchor"]["rect"] == [0.1, 0.1, 0.2, 0.05]


def test_a_segment_of_another_page_is_refused(db, client):
    doc_a = _import(db, CLM)
    from tests.unit.api.test_page_text_follows_the_file import SYRIAC
    doc_b = _import(db, SYRIAC)
    other = next(s for s in db.all(Segment) if s.document_id == doc_b)
    response = client.post("/api/annotations", json={
        "document_id": doc_a, "kind": "highlight", "targets": [{"segment_id": other.id}],
    })
    assert response.status_code == 422
    assert "another page" in response.json()["detail"]


def test_an_unknown_segment_is_refused(db, client):
    doc_id = _import(db, CLM)
    response = client.post("/api/annotations", json={
        "document_id": doc_id, "kind": "highlight", "targets": [{"segment_id": "0" * 32}],
    })
    assert response.status_code == 404


def test_a_range_must_name_both_ends_in_order(db, client):
    doc_id = _import(db, CLM)
    line = _lines(db, doc_id)[0]
    for bad in ({"segment_id": line.id, "char_start": 5},
                {"segment_id": line.id, "char_start": 9, "char_end": 3}):
        response = client.post("/api/annotations", json={
            "document_id": doc_id, "kind": "highlight", "targets": [bad]})
        assert response.status_code == 422, bad


def test_a_mark_on_a_selection_undoes(db, client):
    doc_id = _import(db, CLM)
    line = _lines(db, doc_id)[0]
    from fichero_server.actions.registry import ActionContext, registry
    from fichero_server.models.knowledge import Annotation
    made = registry.invoke(db, "annotation.create", {
        "document_id": doc_id, "kind": "bookmark", "targets": [{"segment_id": line.id}],
    }, ActionContext(actor="historian", is_bootstrap=True))
    assert db.get(Annotation, made.result["id"]) is not None
    assert client.post(f"/api/actions/audit/{made.audit_id}/undo").status_code == 200
    assert db.get(Annotation, made.result["id"]) is None
