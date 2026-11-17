"""Show Image remembered on the source survives every read the app takes of it (#6657,
`layers.toggle.image-remembered-on-the-source`).

Spec: docs/contributor_manual/specs/ui/layers-on-the-source.md. The app writes `view.show_image` into the source's metadata
with `PUT /api/documents/{id}` and reads it back from whatever document it holds: the one it fetched, or the folder listing
(`/view`, `/children`) that a folder load replaces its cache with. A listing without the metadata would drop the setting on
the next folder load.
"""
from __future__ import annotations


def test_show_image_is_kept_by_the_update_and_every_listing(client):
    folder = client.post("/api/documents", json={"name": "Box", "doc_type": "folder"}).json()
    image = client.post("/api/documents", json={"name": "p1.jpg", "parent_id": folder["id"], "doc_type": "file",
                                                "metadata": {"note": "kept"}}).json()

    saved = client.put(f"/api/documents/{image['id']}", json={"metadata": {"note": "kept", "view.show_image": False}})
    assert saved.status_code == 200, saved.text
    assert saved.json()["metadata"] == {"note": "kept", "view.show_image": False}

    assert client.get(f"/api/documents/{image['id']}").json()["metadata"]["view.show_image"] is False
    children = client.get(f"/api/documents/{folder['id']}/children").json()
    items = children if isinstance(children, list) else children.get("items") or children.get("children") or []
    assert [d["metadata"].get("view.show_image") for d in items if d["id"] == image["id"]] == [False]
    view = client.get(f"/api/documents/{folder['id']}/view").json()
    listed = [d for key in ("children", "items", "documents") for d in (view.get(key) or []) if d.get("id") == image["id"]]
    assert listed and listed[0]["metadata"].get("view.show_image") is False, view.keys()
