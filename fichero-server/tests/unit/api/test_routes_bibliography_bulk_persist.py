"""Hardening coverage for the #3328 bulk import+persist route.

POST /api/bibliography/import/persist parses BibTeX/RIS/CSL-JSON and persists
each entry as a child Document. The route forwards to the audited
``bibliography.bulk_import`` action, so these tests exercise the full
route -> registry -> _bulk_import_impl chain via the authenticated client.
"""

from __future__ import annotations

from fichero_server.models import DocType, Document

TWO_BIBTEX = (
    "@book{a,\n  title = {First Work},\n  author = {Doe, Jane},\n  year = {1999}\n}\n"
    "@article{b,\n  title = {Second Work},\n  author = {Roe, Ann},\n  year = {2001}\n}\n"
)


def _persist(client, **body):
    return client.post("/api/bibliography/import/persist", json=body)


def test_persists_entries_as_children_of_new_collection(client, db):
    """Happy path: no target -> a folder is auto-created and each entry becomes
    one child file document carrying its parsed source_metadata."""
    response = _persist(client, text=TWO_BIBTEX, format="bibtex")
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["count"] == 2
    assert len(payload["document_ids"]) == 2
    titles = {e["title"] for e in payload["entries"]}
    assert titles == {"First Work", "Second Work"}

    children = [db.get(Document, doc_id) for doc_id in payload["document_ids"]]
    assert all(c is not None for c in children)
    assert all(c.doc_type == DocType.file for c in children)
    # All children share one auto-created folder parent.
    parent_ids = {c.parent_id for c in children}
    assert len(parent_ids) == 1
    parent = db.get(Document, parent_ids.pop())
    assert parent is not None and parent.doc_type == DocType.folder
    # Metadata round-trips onto the child.
    child_titles = {c.source_metadata["title"] for c in children}
    assert child_titles == {"First Work", "Second Work"}


def test_persists_under_existing_target_document(client, db):
    """target_document_id -> children hang off that parent, no folder created."""
    parent = Document(name="My Collection", doc_type=DocType.folder)
    db.save(parent)

    response = _persist(
        client, text=TWO_BIBTEX, format="bibtex", target_document_id=parent.id
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["count"] == 2

    for doc_id in payload["document_ids"]:
        child = db.get(Document, doc_id)
        assert child is not None
        assert child.parent_id == parent.id


def test_empty_input_is_rejected(client):
    """Valid format but nothing parsable -> 400, not a silent empty success."""
    response = _persist(client, text="   ", format="bibtex")
    assert response.status_code == 400
    assert "parsable" in response.json()["detail"].lower()


def test_unrecognised_format_is_rejected(client):
    """An explicit unknown format hint -> 400 rather than a 500."""
    response = _persist(client, text="whatever", format="not-a-format")
    assert response.status_code == 400
    assert "recognised" in response.json()["detail"].lower()


def test_missing_target_document_is_404(client):
    """A target_document_id that does not exist -> 404, nothing persisted."""
    response = _persist(
        client, text=TWO_BIBTEX, format="bibtex", target_document_id="does-not-exist"
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
