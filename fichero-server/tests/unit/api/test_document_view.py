"""The ONE outline endpoint (Mandate 1, approved 2026-08-24).

GET /api/documents/{id}/view answers "where am I, what's in here, what does
it have" in one response — ancestors root-first, level-aware children, and
the anchor's attachment summary. These pin the contract the five client
tree-constructions migrate onto.
"""

from fichero_server.models import Artifact, DocType, Document, Rendition
from fichero_server.models.knowledge import Annotation, KnowledgeEntity


def _doc(db, name, parent_id=None, doc_type=DocType.file):
    doc = Document(name=name, parent_id=parent_id, doc_type=doc_type)
    db.save(doc)
    return doc


class TestDocumentView:
    def test_missing_document_is_a_declared_404(self, client):
        r = client.get("/api/documents/nope/view")
        assert r.status_code == 404

    def test_ancestors_are_root_first_and_children_ride_along(self, client, db):
        root = _doc(db, "Root", doc_type=DocType.folder)
        mid = _doc(db, "Mid", parent_id=root.id, doc_type=DocType.folder)
        leaf = _doc(db, "Leaf", parent_id=mid.id)
        sibling = _doc(db, "Sibling", parent_id=mid.id)

        r = client.get(f"/api/documents/{leaf.id}/view")
        assert r.status_code == 200
        body = r.json()
        assert [a["name"] for a in body["ancestors"]] == ["Root", "Mid"]
        assert body["document"]["id"] == leaf.id
        assert body["children"] == []

        r = client.get(f"/api/documents/{mid.id}/view")
        names = {c["name"] for c in r.json()["children"]}
        assert names == {"Leaf", "Sibling"}
        assert sibling.id in {c["id"] for c in r.json()["children"]}

    def test_doc_prefixed_ids_resolve(self, client, db):
        doc = _doc(db, "Prefixed")
        r = client.get(f"/api/documents/doc:{doc.id}/view")
        assert r.status_code == 200
        assert r.json()["document"]["id"] == doc.id

    def test_parent_cycle_terminates(self, client, db):
        a = _doc(db, "A", doc_type=DocType.folder)
        b = _doc(db, "B", parent_id=a.id, doc_type=DocType.folder)
        a.parent_id = b.id  # malformed cycle — must not walk forever
        db.save(a)
        r = client.get(f"/api/documents/{b.id}/view")
        assert r.status_code == 200
        assert len(r.json()["ancestors"]) <= 2

    def test_attachments_summarise_the_anchor_only(self, client, db):
        folder = _doc(db, "Folder", doc_type=DocType.folder)
        page = _doc(db, "Page", parent_id=folder.id)
        db.save(Rendition(document_id=page.id, role="original", path="/x/p.jpg"))
        db.save(Artifact(document_id=page.id, artifact_type="transcription", content="hi"))
        db.save(Annotation(document_id=page.id, kind="note", text="n"))
        db.save(
            KnowledgeEntity(canonical_name="Pedro", source_document_ids=[page.id])
        )
        # The sibling's attachments must NOT bleed into the anchor's summary.
        other = _doc(db, "Other", parent_id=folder.id)
        db.save(Artifact(document_id=other.id, artifact_type="transcription", content="x"))

        r = client.get(f"/api/documents/{page.id}/view")
        att = r.json()["attachments"]
        assert len(att["renditions"]) == 1
        assert len(att["artifacts"]) == 1
        assert att["artifacts"][0]["document_id"] == page.id
        assert att["annotation_count"] == 1
        assert att["entity_count"] == 1

    def test_flags_skip_halves(self, client, db):
        folder = _doc(db, "Folder", doc_type=DocType.folder)
        _doc(db, "Child", parent_id=folder.id)
        r = client.get(
            f"/api/documents/{folder.id}/view?children=false&attachments=false"
        )
        body = r.json()
        assert body["children"] == []
        assert body["attachments"] is None
