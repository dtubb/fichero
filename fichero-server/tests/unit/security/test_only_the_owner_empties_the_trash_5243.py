"""`safety.trash.who-may-empty` / `who-may-put-back` (#5243, manager ruling 2026-11-05): with accounts on, an editor can delete
and put back but only the library's owner can empty the Trash for good; in a personal library the caller is the owner.
"""

from __future__ import annotations

from fichero_server.models import Document
from tests.unit.security.test_mutation_authz import _grant, multiuser_client, users  # noqa: F401  (fixtures)


def test_an_editor_puts_back_but_only_the_owner_empties(db, app_db, users, multiuser_client):  # noqa: F811
    client, login, library_path = multiuser_client
    _grant(app_db, users.owner, library_path, "owner")
    _grant(app_db, users.editor, library_path, "editor")
    doc = Document(name="Letters")
    db.save(doc)
    editor, owner = login("editor"), login("owner")

    assert client.delete(f"/api/documents/{doc.id}", headers=editor).status_code == 204
    put_back = client.post(f"/api/documents/{doc.id}/restore", headers=editor)
    assert put_back.status_code == 200, "whoever could delete it may put it back"
    assert client.delete(f"/api/documents/{doc.id}", headers=editor).status_code == 204

    refused = client.post("/api/documents/trash/empty", headers=editor)
    assert refused.status_code == 403, refused.text
    assert db.get(Document, doc.id) is not None, "a refused empty removes nothing"

    emptied = client.post("/api/documents/trash/empty", headers=owner)
    assert emptied.status_code == 200, emptied.text
    assert db.get(Document, doc.id) is None
