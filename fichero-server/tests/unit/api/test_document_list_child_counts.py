"""#5399 — the plain document list said every folder had 0 children.

WHY: `/roots` and `/{id}/children` filled the transient `child_count` (#3355), but `GET /api/documents`
did not, so the MCP's `fichero_docs_list` and the CLI's `docs list` reported the Sergio notebooks
(49 and 104 photos) as empty. An agent reading that list concludes there is nothing to read. One
folder must have one count on every listing surface.
"""
from __future__ import annotations

from fichero_server.models import Document


def test_the_plain_list_counts_a_folders_children_like_roots_does(client, db):
    folder = Document(name="SM_NPQ_C01")
    db.save(folder)
    for n in range(3):
        db.save(Document(name=f"photo_{n}.jpg", parent_id=folder.id))
    empty = Document(name="empty")
    db.save(empty)

    listed = {d["id"]: d["child_count"] for d in client.get("/api/documents").json()["items"]}
    roots = {d["id"]: d["child_count"] for d in client.get("/api/documents/roots").json()["items"]}

    assert listed[folder.id] == 3 == roots[folder.id]
    assert listed[empty.id] == 0
