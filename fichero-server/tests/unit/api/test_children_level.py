"""GET /documents/{id}/children?level= — the tier selector on the wire."""
from __future__ import annotations
from fichero_server.models import Document
import fichero_server.api.routes.document.documents  # noqa: F401


def _folder_with_opening(db):
    folder = Document(name="diary", doc_type="folder")
    db.save(folder)
    opening = Document(name="IMG_001", parent_id=folder.id, prototype_key="opening", sequence=1)
    db.save(opening)
    for p in (1, 2):
        db.save(Document(name=f"IMG_001_part_{p}", parent_id=opening.id,
                         prototype_key="page", sequence=p))
    db.save(Document(name="IMG_009", parent_id=folder.id, prototype_key="page", sequence=9))
    return folder


def test_default_is_stored_and_unchanged(client, db):
    folder = _folder_with_opening(db)
    body = client.get(f"/api/documents/{folder.id}/children").json()
    assert sorted(i["name"] for i in body["items"]) == ["IMG_001", "IMG_009"]


def test_content_level_expands_the_opening_and_keeps_the_whole_page(client, db):
    folder = _folder_with_opening(db)
    body = client.get(f"/api/documents/{folder.id}/children?level=content").json()
    assert sorted(i["name"] for i in body["items"]) == [
        "IMG_001_part_1", "IMG_001_part_2", "IMG_009",
    ]


def test_count_matches_the_resolved_items(client, db):
    folder = _folder_with_opening(db)
    body = client.get(f"/api/documents/{folder.id}/children?level=content").json()
    assert body["count"] == len(body["items"]) == 3


def test_an_unknown_level_is_rejected_not_silently_ignored(client, db):
    folder = _folder_with_opening(db)
    r = client.get(f"/api/documents/{folder.id}/children?level=nonsense")
    assert r.status_code >= 400
