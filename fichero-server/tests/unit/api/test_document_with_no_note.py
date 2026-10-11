"""`openapi.mcp.refusals-in-words`: a document with no note answers an empty note, not an error.

WHY (2026-10-11, the hands-on MCP pass): an agent asking for a page's note got 404 "Document note not found", an
error for what is only an absence, and could not tell it from a page that does not exist. The app never reads this
route (its notes come through /api/notes), so nothing relied on the 404.
"""
from __future__ import annotations

from fichero_server.models import Document


def test_a_document_with_no_note_answers_an_empty_note(client, db):
    page = Document(name="f. 1r")
    db.save(page)
    r = client.get(f"/api/documents/{page.id}/notes")
    assert r.status_code == 200, r.text
    assert r.json()["document_id"] == page.id and r.json()["content"] == ""


def test_a_written_note_is_answered_and_a_missing_document_is_still_404(client, db):
    page = Document(name="f. 1v")
    db.save(page)
    assert client.put(f"/api/documents/{page.id}/notes", json={"content": "Hand B from here"}).status_code == 200
    assert client.get(f"/api/documents/{page.id}/notes").json()["content"] == "Hand B from here"
    assert client.get("/api/documents/no-such-document/notes").status_code == 404
