from __future__ import annotations

import pytest
from fastapi import HTTPException

from fichero.models import Document
from fichero.api.routes.citation.bibliography import _parse_bibliography


def test_parse_bibliography_rejects_unknown_format_without_writing():
    with pytest.raises(HTTPException) as exc:
        _parse_bibliography("not a bibliography record", "unknown")

    assert exc.value.status_code == 400
    assert "Format not recognised" in exc.value.detail


def test_attach_record_sets_source_metadata_and_bibtex(client, db):
    doc = Document(name="paper.pdf")
    db.save(doc)

    response = client.post(
        f"/api/bibliography/document/{doc.id}/attach",
        json={
            "text": "@book{paper,\n  title = {A Test Work},\n  author = {Doe, Jane},\n  year = {1999}\n}",
            "format": "bibtex",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["document_id"] == doc.id
    assert payload["metadata"]["title"] == "A Test Work"
    assert payload["metadata"]["bibtex"].startswith("@")
    assert "A Test Work" in payload["metadata"]["bibtex"]
