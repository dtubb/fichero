"""Tests for artifact routes.

Artifacts are versioned outputs from AI/ML processing steps (transcription, entities,
summaries, etc.). They are always linked to a Document. SwiftUI uses these routes to
display processed results alongside source documents.
"""

from datetime import datetime

from fichero.models import ActionAudit, Artifact, Document, DocType, FileType, Status


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_doc(db, name: str = "test.jpg") -> Document:
    doc = Document(
        name=name,
        doc_type=DocType.file,
        file_type=FileType.image,
        path=f"/path/{name}",
        status=Status.completed,
    )
    db.save(doc)
    return doc


def _make_artifact(db, doc_id: str, artifact_type: str = "transcription", content: str = "text") -> Artifact:
    a = Artifact(
        document_id=doc_id,
        artifact_type=artifact_type,
        content=content,
        version=1,
        created_at=datetime.now(),
    )
    db.save(a)
    return a


# ---------------------------------------------------------------------------
# POST /api/artifacts/
# ---------------------------------------------------------------------------


class TestCreateArtifact:
    def test_create_artifact_persists_for_document(self, client, db):
        doc = _make_doc(db)

        r = client.post(
            "/api/artifacts/",
            json={
                "document_id": doc.id,
                "artifact_type": "transcription",
                "content": "imported transcript",
                "data": {"source": "manifest-import"},
                "provider": "manifest-importer",
                "model": "fichero-corpus-import-v1",
                "step_name": "import_manifest",
                "confidence": 1.0,
            },
        )

        assert r.status_code == 200
        body = r.json()
        assert body["document_id"] == doc.id
        assert body["artifact_type"] == "transcription"
        assert body["content"] == "imported transcript"
        assert body["data"]["source"] == "manifest-import"
        assert body["provider"] == "manifest-importer"
        assert body["model"] == "fichero-corpus-import-v1"
        assert body["confidence"] == 1.0

        listed = client.get(
            f"/api/artifacts/document/{doc.id}?include_descendants=false"
        ).json()
        assert listed["count"] == 1
        assert listed["items"][0]["id"] == body["id"]

    def test_create_artifact_rejects_missing_document(self, client):
        r = client.post(
            "/api/artifacts/",
            json={"document_id": "missing", "artifact_type": "transcription"},
        )
        assert r.status_code == 404

    def test_create_artifact_writes_action_audit_and_emits(self, client, db, monkeypatch):
        doc = _make_doc(db)
        calls: list[tuple] = []
        monkeypatch.setattr(
            "fichero.api.change_stream.emit_change",
            lambda *a, **k: calls.append((a, k)),
        )

        r = client.post(
            "/api/artifacts/",
            json={"document_id": doc.id, "artifact_type": "transcription"},
        )

        assert r.status_code == 200
        artifact_id = r.json()["id"]
        audits = [row for row in db.all(ActionAudit) if row.action_name == "artifact.create"]
        assert len(audits) == 1
        assert audits[0].target_ids == [artifact_id]
        assert calls[-1][1]["type"] == "artifact.created"
        assert calls[-1][1]["artifact_ids"] == [artifact_id]


# ---------------------------------------------------------------------------
# GET /api/artifacts/document/{doc_id}
# ---------------------------------------------------------------------------


class TestListDocumentArtifacts:
    def test_returns_empty_for_doc_with_no_artifacts(self, client, db):
        doc = _make_doc(db)
        r = client.get(f"/api/artifacts/document/{doc.id}")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 0
        assert data["items"] == []

    def test_returns_artifact_for_document(self, client, db):
        doc = _make_doc(db)
        _make_artifact(db, doc.id, "transcription", "hello world")
        r = client.get(f"/api/artifacts/document/{doc.id}")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 1
        assert data["items"][0]["artifact_type"] == "transcription"

    def test_404_for_missing_document(self, client):
        r = client.get("/api/artifacts/document/nonexistent-id")
        assert r.status_code == 404

    def test_page_doc_returns_parent_artifacts(self, client, db):
        # Transcribe workflows save artifacts on the parent PDF, not per page.
        # Querying a page document must surface the parent's artifacts.
        parent = _make_doc(db, "report.pdf")
        page = Document(
            name="report.pdf - Page 1",
            doc_type=DocType.page,
            parent_id=parent.id,
            status=Status.completed,
        )
        db.save(page)
        _make_artifact(db, parent.id, "transcription", "full text")
        r = client.get(f"/api/artifacts/document/{page.id}")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 1
        assert data["items"][0]["artifact_type"] == "transcription"

    def test_strict_scope_excludes_parent_and_sibling_artifacts(self, client, db):
        """V2 strict per-document scope (#721): with
        ``include_descendants=false``, querying a page must return ONLY
        artifacts whose ``document_id`` matches the page's id — not the
        parent folder's container artifacts (Catalogue, Dates, Events,
        etc.) and not sibling pages' artifacts. This was the bug: the
        Artifacts tab in the inspector was using the legacy
        ``include_descendants=true`` default and bleeding folder-level
        artifacts onto every child page.
        """
        folder = Document(
            name="case-folder",
            doc_type=DocType.folder,
            status=Status.completed,
        )
        db.save(folder)
        page_a = Document(
            name="page_a.jpg",
            doc_type=DocType.file,
            file_type=FileType.image,
            parent_id=folder.id,
            status=Status.completed,
        )
        page_b = Document(
            name="page_b.jpg",
            doc_type=DocType.file,
            file_type=FileType.image,
            parent_id=folder.id,
            status=Status.completed,
        )
        db.save(page_a)
        db.save(page_b)

        # Folder-level container artifacts (what a Catalogue workflow writes).
        _make_artifact(db, folder.id, "catalogue", "folder catalogue")
        _make_artifact(db, folder.id, "dates", "folder dates")
        _make_artifact(db, folder.id, "people", "folder people")
        # A page-level artifact on page_a.
        _make_artifact(db, page_a.id, "transcription", "page A text")
        # A sibling page-level artifact on page_b.
        _make_artifact(db, page_b.id, "transcription", "page B text")

        # Strict scope: page_a sees ONLY its own transcription.
        r = client.get(
            f"/api/artifacts/document/{page_a.id}?include_descendants=false"
        )
        assert r.status_code == 200
        data = r.json()
        artifact_types = sorted(a["artifact_type"] for a in data["items"])
        assert artifact_types == ["transcription"], (
            f"strict scope leaked artifacts: {artifact_types}"
        )
        assert all(
            a["document_id"] == page_a.id for a in data["items"]
        ), "strict scope returned an artifact whose document_id != requested doc"

    def test_legacy_scope_still_aggregates_for_v1_callers(self, client, db):
        """Backwards-compat check: the legacy ``include_descendants=true``
        mode (and the API default) MUST keep aggregating doc + parent +
        children. V1 inspector callers depend on this. The fix for #721
        is in the V2 callers (Inspector, Artifacts tab) — the endpoint
        contract for both modes stays.
        """
        folder = Document(
            name="case-folder",
            doc_type=DocType.folder,
            status=Status.completed,
        )
        db.save(folder)
        page = Document(
            name="page.jpg",
            doc_type=DocType.file,
            file_type=FileType.image,
            parent_id=folder.id,
            status=Status.completed,
        )
        db.save(page)
        _make_artifact(db, folder.id, "catalogue", "folder catalogue")
        _make_artifact(db, page.id, "transcription", "page text")

        # Legacy mode: page sees its own + parent's artifacts.
        r = client.get(
            f"/api/artifacts/document/{page.id}?include_descendants=true"
        )
        assert r.status_code == 200
        data = r.json()
        artifact_types = sorted(a["artifact_type"] for a in data["items"])
        assert artifact_types == ["catalogue", "transcription"], (
            f"legacy mode broke aggregation: {artifact_types}"
        )

    def test_filter_by_artifact_type(self, client, db):
        doc = _make_doc(db)
        _make_artifact(db, doc.id, "transcription")
        _make_artifact(db, doc.id, "summary")
        r = client.get(f"/api/artifacts/document/{doc.id}?artifact_type=summary")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 1
        assert data["items"][0]["artifact_type"] == "summary"

    def test_pagination_limit(self, client, db):
        doc = _make_doc(db)
        for i in range(5):
            _make_artifact(db, doc.id, "transcription", f"page {i}")
        r = client.get(f"/api/artifacts/document/{doc.id}?limit=2")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 5
        assert len(data["items"]) == 2

    def test_pagination_offset(self, client, db):
        doc = _make_doc(db)
        for i in range(3):
            _make_artifact(db, doc.id, "transcription", f"page {i}")
        r = client.get(f"/api/artifacts/document/{doc.id}?offset=2")
        assert r.status_code == 200
        data = r.json()
        assert len(data["items"]) == 1

    def test_page_child_artifacts_ordered_by_sequence(self, client, db):
        """Page-child artifacts must come back in page-sequence order (ascending),
        not creation-time order (#1271).  Create artifacts in reverse creation
        order so that any created_at-descending sort would return them wrong."""
        from datetime import timedelta

        parent = Document(
            name="report.pdf",
            doc_type=DocType.file,
            file_type=FileType.pdf,
            path="/path/report.pdf",
            status=Status.completed,
        )
        db.save(parent)

        page1 = Document(name="report.pdf - Page 1", doc_type=DocType.page, parent_id=parent.id, sequence=1, status=Status.completed)
        page2 = Document(name="report.pdf - Page 2", doc_type=DocType.page, parent_id=parent.id, sequence=2, status=Status.completed)
        page3 = Document(name="report.pdf - Page 3", doc_type=DocType.page, parent_id=parent.id, sequence=3, status=Status.completed)
        db.save(page1)
        db.save(page2)
        db.save(page3)

        # Artifacts created in reverse page order so created_at DESC would give [3,2,1].
        base = datetime(2024, 1, 1, 12, 0, 0)
        a3 = Artifact(document_id=page3.id, artifact_type="transcription", content="page 3 text", version=1, created_at=base)
        a2 = Artifact(document_id=page2.id, artifact_type="transcription", content="page 2 text", version=1, created_at=base + timedelta(seconds=1))
        a1 = Artifact(document_id=page1.id, artifact_type="transcription", content="page 1 text", version=1, created_at=base + timedelta(seconds=2))
        db.save(a3)
        db.save(a2)
        db.save(a1)

        r = client.get(f"/api/artifacts/document/{parent.id}")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 3
        contents = [a["content"] for a in data["items"]]
        assert contents == ["page 1 text", "page 2 text", "page 3 text"], (
            f"Expected ascending page order but got: {contents}"
        )

    def test_response_fields_present(self, client, db):
        doc = _make_doc(db)
        a = _make_artifact(db, doc.id, "transcription", "content here")
        r = client.get(f"/api/artifacts/document/{doc.id}")
        assert r.status_code == 200
        artifact = r.json()["items"][0]
        assert artifact["id"] == a.id
        assert artifact["document_id"] == doc.id
        assert artifact["content"] == "content here"
        assert "created_at" in artifact


# ---------------------------------------------------------------------------
# GET /api/artifacts/{artifact_id}
# ---------------------------------------------------------------------------


class TestGetArtifact:
    def test_returns_artifact_by_id(self, client, db):
        doc = _make_doc(db)
        a = _make_artifact(db, doc.id)
        r = client.get(f"/api/artifacts/{a.id}")
        assert r.status_code == 200
        assert r.json()["id"] == a.id

    def test_404_for_unknown_id(self, client):
        r = client.get("/api/artifacts/no-such-id")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/artifacts/ (list all)
# ---------------------------------------------------------------------------


class TestListAllArtifacts:
    def test_empty_library_returns_empty(self, client):
        r = client.get("/api/artifacts/")
        assert r.status_code == 200
        assert r.json()["count"] == 0

    def test_returns_all_artifacts(self, client, db):
        doc = _make_doc(db)
        _make_artifact(db, doc.id, "transcription")
        _make_artifact(db, doc.id, "summary")
        r = client.get("/api/artifacts/")
        assert r.status_code == 200
        assert r.json()["count"] == 2

    def test_filter_by_type(self, client, db):
        doc = _make_doc(db)
        _make_artifact(db, doc.id, "transcription")
        _make_artifact(db, doc.id, "entities")
        r = client.get("/api/artifacts/?artifact_type=entities")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 1
        assert data["items"][0]["artifact_type"] == "entities"

    def test_pagination(self, client, db):
        doc = _make_doc(db)
        for i in range(10):
            _make_artifact(db, doc.id, "transcription", f"p{i}")
        r = client.get("/api/artifacts/?limit=3&offset=7")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 10
        assert len(data["items"]) == 3


# ---------------------------------------------------------------------------
# GET /api/artifacts/types
# ---------------------------------------------------------------------------


class TestListArtifactTypes:
    def test_empty_returns_empty_list(self, client):
        r = client.get("/api/artifacts/types")
        assert r.status_code == 200
        assert r.json()["items"] == []

    def test_returns_unique_types_sorted(self, client, db):
        doc = _make_doc(db)
        _make_artifact(db, doc.id, "transcription")
        _make_artifact(db, doc.id, "summary")
        _make_artifact(db, doc.id, "transcription")  # duplicate type
        r = client.get("/api/artifacts/types")
        assert r.status_code == 200
        types = r.json()["items"]
        assert types == sorted(set(types))
        assert "transcription" in types
        assert "summary" in types
        assert types.count("transcription") == 1


# ---------------------------------------------------------------------------
# DELETE /api/artifacts/{artifact_id}
# ---------------------------------------------------------------------------


class TestDeleteArtifact:
    def test_delete_existing_artifact(self, client, db):
        doc = _make_doc(db)
        a = _make_artifact(db, doc.id)
        r = client.delete(f"/api/artifacts/{a.id}")
        assert r.status_code == 204

    def test_delete_removes_from_listing(self, client, db):
        doc = _make_doc(db)
        a = _make_artifact(db, doc.id)
        client.delete(f"/api/artifacts/{a.id}")
        r = client.get("/api/artifacts/")
        assert r.json()["count"] == 0

    def test_delete_nonexistent_returns_404(self, client):
        r = client.delete("/api/artifacts/no-such-id")
        assert r.status_code == 404

    def test_delete_writes_action_audit_and_emits(self, client, db, monkeypatch):
        doc = _make_doc(db)
        artifact = _make_artifact(db, doc.id)
        calls: list[tuple] = []
        monkeypatch.setattr(
            "fichero.api.change_stream.emit_change",
            lambda *a, **k: calls.append((a, k)),
        )

        r = client.delete(f"/api/artifacts/{artifact.id}")

        assert r.status_code == 204
        audits = [row for row in db.all(ActionAudit) if row.action_name == "artifact.delete"]
        assert len(audits) == 1
        assert audits[0].target_ids == [artifact.id]
        assert calls[-1][1]["type"] == "artifact.deleted"
        assert calls[-1][1]["artifact_ids"] == [artifact.id]


# ---------------------------------------------------------------------------
# include_descendants query (V2 inspector — strict per-document scope)
# ---------------------------------------------------------------------------


class TestIncludeDescendantsScope:
    """V2 inspector passes include_descendants=false to avoid
    'delete pops back' confusion where the parent artifact reappeared
    after deleting a sibling on the child.
    """

    def test_default_includes_parent_artifacts_for_page_doc(self, client, db):
        # Parent PDF holds the transcription; page child has none of its own.
        parent = _make_doc(db, name="parent.pdf")
        page = Document(
            name="page-1",
            doc_type=DocType.file,
            file_type=FileType.image,
            parent_id=parent.id,
            status=Status.completed,
        )
        db.save(page)
        _make_artifact(db, parent.id, "transcription", "from-parent")

        # Default behavior (V1): aggregate parent + children.
        r = client.get(f"/api/artifacts/document/{page.id}")
        assert r.status_code == 200
        contents = [a["content"] for a in r.json()["items"]]
        assert "from-parent" in contents

    def test_strict_scope_excludes_parent_artifacts(self, client, db):
        parent = _make_doc(db, name="parent.pdf")
        page = Document(
            name="page-1",
            doc_type=DocType.file,
            file_type=FileType.image,
            parent_id=parent.id,
            status=Status.completed,
        )
        db.save(page)
        _make_artifact(db, parent.id, "transcription", "from-parent")

        r = client.get(
            f"/api/artifacts/document/{page.id}",
            params={"include_descendants": "false"},
        )
        assert r.status_code == 200
        assert r.json()["count"] == 0

    def test_strict_scope_returns_own_artifact(self, client, db):
        doc = _make_doc(db)
        _make_artifact(db, doc.id, "transcription", "own")

        r = client.get(
            f"/api/artifacts/document/{doc.id}",
            params={"include_descendants": "false"},
        )
        assert r.status_code == 200
        assert r.json()["count"] == 1
        assert r.json()["items"][0]["content"] == "own"


# ---------------------------------------------------------------------------
# PUT /api/artifacts/{artifact_id} (V2 inspector edit)
# ---------------------------------------------------------------------------


class TestUpdateArtifact:
    def test_update_content_persists(self, client, db):
        doc = _make_doc(db)
        a = _make_artifact(db, doc.id, content="original")

        r = client.put(
            f"/api/artifacts/{a.id}",
            json={"content": "edited"},
        )
        assert r.status_code == 200
        assert r.json()["content"] == "edited"

        # Reload to confirm persistence.
        r2 = client.get(f"/api/artifacts/{a.id}")
        assert r2.json()["content"] == "edited"

    def test_update_preserves_provenance(self, client, db):
        doc = _make_doc(db)
        a = Artifact(
            document_id=doc.id,
            artifact_type="transcription",
            content="x",
            version=3,
            provider="dashscope",
            model="qwen3-vl-32b-instruct",
            created_at=datetime.now(),
        )
        db.save(a)

        client.put(f"/api/artifacts/{a.id}", json={"content": "y"})

        r = client.get(f"/api/artifacts/{a.id}")
        body = r.json()
        # Editing the content keeps the tool that made it on record.
        assert body["provider"] == "dashscope"
        assert body["model"] == "qwen3-vl-32b-instruct"
        assert body["version"] == 3

    def test_update_reviewed_flag(self, client, db):
        doc = _make_doc(db)
        a = _make_artifact(db, doc.id)

        r = client.put(f"/api/artifacts/{a.id}", json={"reviewed": True})
        assert r.status_code == 200
        assert r.json()["reviewed"] is True

    def test_update_nonexistent_returns_404(self, client):
        r = client.put("/api/artifacts/no-such-id", json={"content": "x"})
        assert r.status_code == 404

    def test_update_writes_action_audit_and_emits(self, client, db, monkeypatch):
        doc = _make_doc(db)
        artifact = _make_artifact(db, doc.id, content="before")
        calls: list[tuple] = []
        monkeypatch.setattr(
            "fichero.api.change_stream.emit_change",
            lambda *a, **k: calls.append((a, k)),
        )

        r = client.put(f"/api/artifacts/{artifact.id}", json={"content": "after"})

        assert r.status_code == 200
        audits = [row for row in db.all(ActionAudit) if row.action_name == "artifact.update"]
        assert len(audits) == 1
        assert audits[0].target_ids == [artifact.id]
        assert calls[-1][1]["type"] == "artifact.updated"
        assert calls[-1][1]["artifact_ids"] == [artifact.id]
