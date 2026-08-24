"""GET /api/documents/{doc_id}/view — the Mandate-1 outline endpoint.

Shipped 2026-08-24 morning; these are its first route tests (found missing
during the overnight sweep). Ancestors root-first, tier-aware children, the
flag halves, the declared 404 — and the #3322 listing sort added so the grid
can migrate without losing its server ordering.
"""

from __future__ import annotations

import pytest

from fichero_server.models import DocType, Document


@pytest.fixture()
def tree(client, db):
    root = Document(name="root", doc_type=DocType.folder)
    db.save(root)
    mid = Document(name="mid", doc_type=DocType.folder, parent_id=root.id)
    db.save(mid)
    leaf = Document(name="leaf", doc_type=DocType.file, parent_id=mid.id)
    db.save(leaf)
    older = Document(
        name="older", doc_type=DocType.file, parent_id=mid.id,
        date_original="1933-01-06", date_jdn=2427079,
    )
    db.save(older)
    newer = Document(
        name="newer", doc_type=DocType.file, parent_id=mid.id,
        date_original="1933-01-07", date_jdn=2427080,
    )
    db.save(newer)
    return {"root": root, "mid": mid, "leaf": leaf, "older": older, "newer": newer}


def _view(client, doc_id, **params):
    response = client.get(f"/api/documents/{doc_id}/view", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_ancestors_come_back_root_first(client, tree):
    body = _view(client, tree["leaf"].id)
    assert [a["name"] for a in body["ancestors"]] == ["root", "mid"]
    assert body["document"]["name"] == "leaf"


def test_children_and_attachment_flags_skip_their_halves(client, tree):
    body = _view(client, tree["mid"].id, children=False, attachments=False)
    assert body["children"] == []
    assert body["attachments"] is None

    body = _view(client, tree["mid"].id)
    assert {c["name"] for c in body["children"]} == {"leaf", "older", "newer"}
    assert body["attachments"] is not None


def test_document_date_sort_orders_children_like_the_children_route(client, tree):
    asc = _view(client, tree["mid"].id, sort_by="document_date")
    desc = _view(client, tree["mid"].id, sort_by="document_date", sort_direction="desc")
    dated_asc = [c["name"] for c in asc["children"] if c["name"] != "leaf"]
    dated_desc = [c["name"] for c in desc["children"] if c["name"] != "leaf"]
    assert dated_asc == ["older", "newer"]
    assert dated_desc == ["newer", "older"]


def test_invalid_sort_is_a_loud_400_never_a_silent_order(client, tree):
    response = client.get(
        f"/api/documents/{tree['mid'].id}/view", params={"sort_by": "name"}
    )
    assert response.status_code == 400


def test_unknown_document_is_a_declared_404(client):
    response = client.get("/api/documents/no-such-doc/view")
    assert response.status_code == 404
