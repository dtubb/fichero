"""A kind's queued items are named by their files (`activity.pane.children-are-what-it-works-on`, #6599, #6588).

Spec: `docs/contributor_manual/specs/ui/activity-pane.md`. A job of its own (thumbnails, text, embed) opens to the files in
flight, BY NAME, never an id: each queued item carries its document's name; a subject that is no document has none.
"""
from __future__ import annotations

from fichero_server.execution import jobs
from fichero_server.models import DocType, Document


def test_each_queued_item_carries_its_files_name(client, db):
    doc = Document(name="IMG_0412.jpg", doc_type=DocType.file)
    db.save(doc)
    jobs._ensure(db)
    jobs.enqueue(db, "pages-6599", doc.id)
    jobs.enqueue(db, "pages-6599", "not-a-document")
    items = client.get("/api/activity/jobs/kind/pages-6599/items").json()["items"]
    named = {i["subject"]: i.get("name") for i in items}
    assert named[doc.id] == "IMG_0412.jpg"
    assert named["not-a-document"] is None
