from fichero.models.knowledge import (
    Reference,
    ReferenceCitationLocation,
    ReferenceKind,
    ReferenceProvenance,
)
from fichero.models import ActionAudit, Document


def _make_reference() -> Reference:
    return Reference(
        title="A Sample Reference",
        authors=["Doe, Jane"],
        year=1942,
        kind=ReferenceKind.article,
        journal_or_book="Journal of Tests",
        doi="10.1234/example",
    )


class TestReferenceRoutes:
    def test_list_get_patch_reference(self, client, db):
        reference = _make_reference()
        db.save(reference)

        response = client.get("/api/references")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["items"][0]["title"] == "A Sample Reference"

        detail = client.get(f"/api/references/{reference.id}")
        assert detail.status_code == 200
        detail_data = detail.json()
        assert detail_data["reference"]["id"] == reference.id
        assert detail_data["provenance"] == []

        patch = client.patch(
            f"/api/references/{reference.id}",
            json={"notes": "Checked against catalog", "status": "verified"},
        )
        assert patch.status_code == 200
        patched = patch.json()
        assert patched["notes"] == "Checked against catalog"
        assert patched["status"] == "verified"
        assert patched["bibtex"].startswith("@article{")
        assert any(
            row.action_name == "reference.patch" and reference.id in row.target_ids
            for row in db.all(ActionAudit)
        )

    def test_non_bibtex_patch_preserves_extra_bibtex_fields(self, client, db):
        reference = Reference(
            bibtex="""@book{demo-key,
  author = {Doe, Jane},
  title = {A Sample Reference},
  year = {1942},
  editor = {Roe, Ann},
  edition = {2},
  url = {https://example.org}
}"""
        )
        db.save(reference)

        patch = client.patch(
            f"/api/references/{reference.id}",
            json={"status": "verified"},
        )
        assert patch.status_code == 200
        patched = patch.json()
        assert "editor = {Roe, Ann}" in patched["bibtex"]
        assert "edition = {2}" in patched["bibtex"]
        assert "url = {https://example.org}" in patched["bibtex"]
        assert patched["metadata"]["bibtex_cite_key"] == "demo-key"

    def test_document_citations_returns_self_and_links(self, client, db):
        document = Document(
            name="Source Document",
            source_metadata={
                "title": "Source Document",
                "authors": ["Smith, Alex"],
                "date": "1942",
                "publisher": "Archive Press",
            },
        )
        db.save(document)

        reference = _make_reference()
        db.save(reference)
        db.save(
            ReferenceProvenance(
                reference_id=reference.id,
                document_id=document.id,
                page="12",
                span_start=3,
                span_end=17,
                citation_location=ReferenceCitationLocation.bibliography,
            )
        )

        response = client.get(f"/api/documents/{document.id}/citations")
        assert response.status_code == 200
        data = response.json()
        assert data["self"]["title"] == "Source Document"
        assert len(data["references"]) == 1
        assert data["references"][0]["id"] == reference.id
        assert len(data["links"]) == 1
        assert data["links"][0]["citation_location"] == "bibliography"

    def test_delete_reference_with_provenance_returns_documents(self, client, db):
        document = Document(name="Source Document")
        db.save(document)

        reference = _make_reference()
        db.save(reference)
        db.save(
            ReferenceProvenance(
                reference_id=reference.id,
                document_id=document.id,
                page="1",
                citation_location=ReferenceCitationLocation.body,
            )
        )

        response = client.delete(f"/api/references/{reference.id}")
        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["documents"][0]["document_id"] == document.id

    def test_delete_reference_writes_action_audit(self, client, db):
        reference = _make_reference()
        db.save(reference)

        response = client.delete(f"/api/references/{reference.id}")
        assert response.status_code == 200
        assert response.json() == {"status": "deleted"}
        assert any(
            row.action_name == "reference.delete" and reference.id in row.target_ids
            for row in db.all(ActionAudit)
        )
