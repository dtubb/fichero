"""
Integration tests for the user-edit protection stamp (#672).

The unit-level tests in test_user_edit_protection.py cover save_artifact
branching on the metadata flag. These tests close the other half of the
contract: the PUT /api/documents/{id} route is what actually writes the
page_content_user_edited_at timestamp on save. Without this coverage, a
future refactor that moves the stamp out of the route would leave unit
tests green while the feature silently regresses.
"""

from __future__ import annotations

import pytest
from fichero_server.models import Document, DocType, Status


@pytest.fixture
def sample_doc(db):
    doc = Document(
        name="letter.jpg",
        doc_type=DocType.file,
        status=Status.pending,
    )
    db.save(doc)
    return doc


class TestUserEditRouteStamp:
    def test_page_content_edit_stamps_metadata(self, client, sample_doc):
        """Editing page_content via the route populates the user-edited timestamp."""
        response = client.put(
            f"/api/documents/{sample_doc.id}",
            json={"page_content": "user-edited text"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["page_content"] == "user-edited text"
        assert "page_content_user_edited_at" in body.get("metadata", {})

    def test_non_page_content_update_does_not_stamp(self, client, sample_doc):
        """Name-only updates must NOT set the user-edit flag — otherwise every
        rename would lock subsequent workflow transcriptions."""
        response = client.put(
            f"/api/documents/{sample_doc.id}",
            json={"name": "renamed.jpg"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "renamed.jpg"
        assert "page_content_user_edited_at" not in body.get("metadata", {})

    def test_existing_metadata_preserved_alongside_stamp(self, client, db):
        """User-edit stamp merges with existing metadata, doesn't replace it."""
        doc = Document(
            name="doc.jpg",
            doc_type=DocType.file,
            metadata={"tag": "hello", "author": "alice"},
        )
        db.save(doc)

        response = client.put(
            f"/api/documents/{doc.id}",
            json={"page_content": "fresh edit"},
        )
        assert response.status_code == 200
        metadata = response.json().get("metadata", {})
        assert metadata.get("tag") == "hello"
        assert metadata.get("author") == "alice"
        assert "page_content_user_edited_at" in metadata

    def test_explicit_metadata_update_also_stamps(self, client, sample_doc):
        """If the client sends both metadata and page_content, the stamp is added
        on top of the incoming metadata, not dropped."""
        response = client.put(
            f"/api/documents/{sample_doc.id}",
            json={
                "page_content": "new text",
                "metadata": {"source": "manual"},
            },
        )
        assert response.status_code == 200
        metadata = response.json().get("metadata", {})
        assert metadata.get("source") == "manual"
        assert "page_content_user_edited_at" in metadata
