"""#6175 end to end, through the route and payload the app sends: the sidebar's delete is
`POST /api/actions/invoke {"name": "document.delete", "params": {"doc_id": ...}}`, once per item, and a
multi-selection's Cmd-Z is ONE `POST /api/actions/audit/undo` with every row it wrote
(`UndoableChange.batch`). Deleting a child never takes the parent or a sibling
(`delete.never-deletes-the-parent`); Undo puts every item back in its folder and order, with the rows it
held before, and makes no new artifact (no reader pass, no embedding, no thumbnail is redone).
Temp library (`client`/`db` fixtures), never a real one."""
from __future__ import annotations

from fichero_server.models import Artifact, DocType, Document


def _doc(db, name, parent=None, order=0, doc_type=DocType.folder):
    doc = Document(name=name, doc_type=doc_type, parent_id=parent, sort_order=order)
    db.save(doc)
    return doc


def _delete(client, doc):
    r = client.post("/api/actions/invoke", json={"name": "document.delete", "params": {"doc_id": doc.id}})
    assert r.status_code == 200, r.text
    return r.json()["audit_id"]


def _gone(db, doc):
    return db.get(Document, doc.id).deleted_at is not None


def test_deleting_an_only_child_leaves_the_parent(client, db):
    parent = _doc(db, "Parent")
    child = _doc(db, "Child", parent.id)

    _delete(client, child)

    assert _gone(db, child)
    assert not _gone(db, parent)


def test_deleting_one_of_several_children_leaves_the_parent_and_every_sibling(client, db):
    parent = _doc(db, "Parent")
    kids = [_doc(db, f"Kid {i}", parent.id, i) for i in range(4)]

    _delete(client, kids[1])

    assert _gone(db, kids[1])
    assert not _gone(db, parent)
    assert [k.name for k in kids if not _gone(db, k)] == ["Kid 0", "Kid 2", "Kid 3"]


def _state(db, docs):
    return [db.get(Document, d.id).model_dump(mode="json", exclude={"updated_at"}) for d in docs]


def test_a_batch_delete_undone_as_one_set_puts_every_item_back_in_its_place_and_order(client, db):
    parent = _doc(db, "Parent")
    kids = [_doc(db, f"Kid {i}", parent.id, i, DocType.file) for i in range(4)]
    grandchild = _doc(db, "Page", kids[2].id, 0, DocType.page)
    db.save(Artifact(document_id=grandchild.id, artifact_type="transcription", content="x"))
    everything = [parent, *kids, grandchild]
    before = _state(db, everything)
    artifacts_before = sorted(a.model_dump_json() for a in db.all(Artifact))

    audit_ids = [_delete(client, kids[0]), _delete(client, kids[2])]
    assert _gone(db, kids[0]) and _gone(db, kids[2]) and _gone(db, grandchild)
    assert not _gone(db, parent) and not _gone(db, kids[1]) and not _gone(db, kids[3])

    r = client.post("/api/actions/audit/undo", json={"audit_ids": audit_ids})
    assert r.status_code == 200, r.text

    assert _state(db, everything) == before, "every row back as it was: folder, order, deleted flags"
    assert sorted(a.model_dump_json() for a in db.all(Artifact)) == artifacts_before, "no artifact made or changed"
