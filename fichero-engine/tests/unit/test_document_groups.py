from fichero.models import DocType, Document


def test_group_and_ungroup_restore_each_child_parent_and_order(client, db):
    left_parent = Document(name="Left", doc_type=DocType.folder)
    right_parent = Document(name="Right", doc_type=DocType.folder)
    first = Document(name="Page one", parent_id=left_parent.id, sort_order=3)
    second = Document(name="Page two", parent_id=right_parent.id, sort_order=7)
    for document in (left_parent, right_parent, first, second):
        db.save(document)

    grouped = client.post("/api/documents/groups", json={"name": "Letter", "child_ids": [first.id, second.id]})
    assert grouped.status_code == 200
    group_id = grouped.json()["id"]
    assert db.get(Document, first.id).parent_id == group_id

    ungrouped = client.post(f"/api/documents/groups/{group_id}/ungroup")
    assert ungrouped.status_code == 200
    assert db.get(Document, first.id).parent_id == left_parent.id
    assert db.get(Document, first.id).sort_order == 3
    assert db.get(Document, second.id).parent_id == right_parent.id
    assert db.get(Document, second.id).sort_order == 7
    assert db.get(Document, group_id) is None
