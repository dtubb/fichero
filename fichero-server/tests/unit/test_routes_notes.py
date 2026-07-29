"""Tests for zettelkasten notes routes (#917)."""

from fichero_server.models.knowledge import Note, NoteKind, NoteLink
from fichero_server.models import DocType, Document


class TestNotesCRUD:
    def test_create_get_patch_delete_note(self, client):
        create = client.post(
            "/api/notes",
            json={
                "title": "Bridge note",
                "body": "A short zettel body",
                "kind": "zettel",
                "tags": ["bridge", "archive"],
            },
        )
        assert create.status_code == 200
        note = create.json()
        note_id = note["id"]
        assert note["title"] == "Bridge note"

        get_response = client.get(f"/api/notes/{note_id}")
        assert get_response.status_code == 200
        assert get_response.json()["id"] == note_id

        patch = client.patch(f"/api/notes/{note_id}", json={"kind": "hub", "tags": ["hub"]})
        assert patch.status_code == 200
        assert patch.json()["kind"] == "hub"
        assert patch.json()["tags"] == ["hub"]

        delete = client.delete(f"/api/notes/{note_id}")
        assert delete.status_code == 204
        missing = client.get(f"/api/notes/{note_id}")
        assert missing.status_code == 404

    def test_list_notes_filters(self, client, db):
        db.save(Note(title="Hub", body="network", kind=NoteKind.hub, tags=["kg"]))
        db.save(Note(title="Inbox", body="todo", kind=NoteKind.inbox, tags=["todo"]))

        by_kind = client.get("/api/notes?kind=hub")
        assert by_kind.status_code == 200
        assert by_kind.json()["count"] == 1
        assert by_kind.json()["items"][0]["kind"] == "hub"

        by_tag = client.get("/api/notes?tag=todo")
        assert by_tag.status_code == 200
        assert by_tag.json()["count"] == 1
        assert by_tag.json()["items"][0]["title"] == "Inbox"

        by_query = client.get("/api/notes?q=network")
        assert by_query.status_code == 200
        assert by_query.json()["count"] == 1
        assert by_query.json()["items"][0]["title"] == "Hub"

    def test_linked_structure_node_id_create_patch_and_filter(self, client, db):
        created = client.post(
            "/api/notes",
            json={
                "title": "Section note",
                "body": "Attached to outline section",
                "linked_structure_node_id": "node-1",
            },
        )
        assert created.status_code == 200
        note_id = created.json()["id"]
        assert created.json()["linked_structure_node_id"] == "node-1"

        db.save(Note(title="Other", body="Detached", linked_structure_node_id="node-2"))

        filtered = client.get("/api/notes?linked_structure_node_id=node-1")
        assert filtered.status_code == 200
        assert filtered.json()["count"] == 1
        assert filtered.json()["items"][0]["id"] == note_id

        patched = client.patch(
            f"/api/notes/{note_id}",
            json={"linked_structure_node_id": "node-3"},
        )
        assert patched.status_code == 200
        assert patched.json()["linked_structure_node_id"] == "node-3"

    def test_page_scoped_note_create_list_and_delete(self, client, db):
        page = Document(id="page-note-1", name="Page 1", doc_type=DocType.page)
        db.save(page)

        created = client.post(
            "/api/notes",
            json={
                "title": "Page note",
                "body": "Scoped to a page",
                "page_id": page.id,
            },
        )
        assert created.status_code == 200
        payload = created.json()
        assert payload["page_id"] == page.id
        assert page.id in payload["linked_document_ids"]

        listed = client.get("/api/notes", params={"page_id": page.id})
        assert listed.status_code == 200
        assert listed.json()["count"] == 1
        assert listed.json()["items"][0]["id"] == payload["id"]

        deleted = client.delete(f"/api/notes/{payload['id']}")
        assert deleted.status_code == 204
        assert db.get(Note, payload["id"]) is None

    def test_folder_scoped_note_create_list_and_delete(self, client, db):
        folder = Document(id="folder-note-1", name="Folder 1", doc_type=DocType.folder)
        db.save(folder)

        created = client.post(
            "/api/notes",
            json={
                "title": "Folder note",
                "body": "Scoped to a folder",
                "folder_id": folder.id,
            },
        )
        assert created.status_code == 200
        payload = created.json()
        assert payload["folder_id"] == folder.id
        assert folder.id in payload["linked_document_ids"]

        listed = client.get("/api/notes", params={"folder_id": folder.id})
        assert listed.status_code == 200
        assert listed.json()["count"] == 1
        assert listed.json()["items"][0]["id"] == payload["id"]

        deleted = client.delete(f"/api/notes/{payload['id']}")
        assert deleted.status_code == 204
        assert db.get(Note, payload["id"]) is None


class TestNoteLinks:
    def test_create_and_delete_link(self, client, db):
        source = Note(title="Source", body="source body")
        target = Note(title="Target", body="target body")
        db.save(source)
        db.save(target)

        link_response = client.post(
            f"/api/notes/{source.id}/links",
            json={"target_note_id": target.id, "link_type": "supports", "annotation": "evidence"},
        )
        assert link_response.status_code == 200
        link = link_response.json()
        assert link["source_note_id"] == source.id
        assert link["target_note_id"] == target.id
        assert link["link_type"] == "supports"

        delete_response = client.delete(f"/api/notes/{source.id}/links/{link['id']}")
        assert delete_response.status_code == 204
        assert db.get(NoteLink, link["id"]) is None

    def test_backlinks_and_forward_links(self, client, db):
        a = Note(title="A", body="A")
        b = Note(title="B", body="B")
        c = Note(title="C", body="C")
        db.save(a)
        db.save(b)
        db.save(c)
        db.save(NoteLink(source_note_id=a.id, target_note_id=b.id, link_type="references"))
        db.save(NoteLink(source_note_id=c.id, target_note_id=b.id, link_type="supports"))

        backlinks = client.get(f"/api/notes/{b.id}/backlinks")
        assert backlinks.status_code == 200
        backlink_titles = {item["title"] for item in backlinks.json()["items"]}
        assert backlink_titles == {"A", "C"}

        forward = client.get(f"/api/notes/{a.id}/forward-links")
        assert forward.status_code == 200
        assert forward.json()["count"] == 1
        assert forward.json()["items"][0]["title"] == "B"

    def test_rejects_self_link(self, client, db):
        note = Note(title="Solo", body="Only note")
        db.save(note)
        response = client.post(
            f"/api/notes/{note.id}/links",
            json={"target_note_id": note.id, "link_type": "free"},
        )
        assert response.status_code == 400
        assert "Cannot link a note to itself" in response.json()["detail"]
