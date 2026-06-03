"""Tests for document export routes."""

import json

from fichero.models import (
    Artifact,
    DocType,
    Document,
    FileType,
    KnowledgeClaim,
    KnowledgeEntity,
)


class TestMarkdownFolderExport:
    def test_exports_folder_markdown_and_assets(self, client, db, tmp_path):
        folder = Document(
            id="folder-export",
            name="Archive Box",
            doc_type=DocType.folder,
        )
        text_doc = Document(
            id="doc-text",
            name="Letter One",
            parent_id=folder.id,
            doc_type=DocType.file,
            file_type=FileType.text,
            page_content="This is the letter transcription.",
        )
        image_path = tmp_path / "source.jpg"
        image_path.write_bytes(b"fake image bytes")
        image_doc = Document(
            id="doc-image",
            name="Photo One",
            parent_id=folder.id,
            doc_type=DocType.file,
            file_type=FileType.image,
            path=str(image_path),
        )
        artifact = Artifact(
            document_id=image_doc.id,
            artifact_type="transcription",
            content="Handwritten caption.",
        )
        db.save(folder)
        db.save(text_doc)
        db.save(image_doc)
        db.save(artifact)

        output_path = tmp_path / "export"
        r = client.post(
            "/api/export/markdown-folder",
            json={
                "target_id": folder.id,
                "output_path": str(output_path),
            },
        )

        assert r.status_code == 200
        data = r.json()
        assert data["document_count"] == 2
        assert (output_path / "index.md").exists()
        assert (output_path / "knowledge-graph.md").exists()

        letter = (output_path / "Letter-One.md").read_text()
        assert "# Letter One" in letter
        assert "This is the letter transcription." in letter

        photo = (output_path / "Photo-One.md").read_text()
        assert "![Photo One](assets/Photo-One.jpg)" in photo
        assert "Handwritten caption." in photo
        assert (
            output_path / "assets" / "Photo-One.jpg"
        ).read_bytes() == b"fake image bytes"
        assert data["assets"][0]["document_id"] == image_doc.id

    def test_rejects_non_empty_output_without_overwrite(self, client, tmp_path):
        output_path = tmp_path / "export"
        output_path.mkdir()
        (output_path / "existing.md").write_text("keep", encoding="utf-8")

        r = client.post(
            "/api/export/markdown-folder",
            json={"output_path": str(output_path)},
        )

        assert r.status_code == 409

    def test_missing_target_returns_404(self, client, tmp_path):
        r = client.post(
            "/api/export/markdown-folder",
            json={
                "target_id": "no-such-doc",
                "output_path": str(tmp_path / "export"),
            },
        )

        assert r.status_code == 404


class TestWordExport:
    def test_exports_docx_with_text_and_image_media(self, client, db, tmp_path):
        import zipfile

        folder = Document(
            id="folder-word",
            name="Word Export",
            doc_type=DocType.folder,
        )
        image_path = tmp_path / "photo.jpg"
        image_path.write_bytes(b"jpg bytes")
        image_doc = Document(
            id="word-image",
            name="Image Page",
            parent_id=folder.id,
            doc_type=DocType.file,
            file_type=FileType.image,
            path=str(image_path),
            page_content="Image transcription.",
        )
        db.save(folder)
        db.save(image_doc)

        output_path = tmp_path / "export.docx"
        r = client.post(
            "/api/export/word",
            json={
                "target_id": folder.id,
                "output_path": str(output_path),
            },
        )

        assert r.status_code == 200
        data = r.json()
        assert data["document_count"] == 1
        assert data["bytes_written"] > 0

        with zipfile.ZipFile(output_path) as docx:
            names = set(docx.namelist())
            document_xml = docx.read("word/document.xml").decode()

        assert "word/media/image1.jpg" in names
        assert "Image transcription." in document_xml
        assert "<w:tbl>" in document_xml

    def test_word_export_rejects_existing_file_without_overwrite(
        self, client, tmp_path
    ):
        output_path = tmp_path / "export.docx"
        output_path.write_bytes(b"existing")

        r = client.post(
            "/api/export/word",
            json={"output_path": str(output_path)},
        )

        assert r.status_code == 409


class TestJsonExport:
    def test_exports_document_artifacts_and_scoped_kg(self, client, db, tmp_path):
        folder = Document(
            id="folder-json",
            name="JSON Export",
            doc_type=DocType.folder,
        )
        doc = Document(
            id="doc-json",
            name="Letter JSON",
            parent_id=folder.id,
            doc_type=DocType.file,
            file_type=FileType.text,
            page_content="Primary transcription.",
        )
        other_doc = Document(
            id="doc-other",
            name="Other",
            doc_type=DocType.file,
            file_type=FileType.text,
        )
        artifact = Artifact(
            id="artifact-json",
            document_id=doc.id,
            artifact_type="summary",
            content="Artifact summary.",
        )
        entity = KnowledgeEntity(
            id="entity-json",
            canonical_name="Maria Perez",
            source_document_ids=[doc.id],
        )
        other_entity = KnowledgeEntity(
            id="entity-other",
            canonical_name="Unrelated",
            source_document_ids=[other_doc.id],
        )
        claim = KnowledgeClaim(
            id="claim-json",
            text="Maria Perez testified.",
            source_document_id=doc.id,
            entity_ids=[entity.id],
            confidence=0.8,
        )
        other_claim = KnowledgeClaim(
            id="claim-other",
            text="Unrelated claim.",
            source_document_id=other_doc.id,
        )
        for item in [
            folder,
            doc,
            other_doc,
            artifact,
            entity,
            other_entity,
            claim,
            other_claim,
        ]:
            db.save(item)

        output_path = tmp_path / "export.json"
        r = client.post(
            "/api/export/json",
            json={
                "target_id": folder.id,
                "output_path": str(output_path),
            },
        )

        assert r.status_code == 200
        data = r.json()
        assert data["document_count"] == 1
        assert data["artifact_count"] == 1
        assert data["entity_count"] == 1
        assert data["claim_count"] == 1
        assert data["bytes_written"] > 0

        payload = json.loads(output_path.read_text(encoding="utf-8"))
        assert payload["doc"]["id"] == folder.id
        assert [item["id"] for item in payload["documents"]] == [doc.id]
        assert payload["transcription"] == "Primary transcription.\n\nsummary: Artifact summary."
        assert [item["id"] for item in payload["artifacts"]] == [artifact.id]
        assert [item["id"] for item in payload["kg"]["entities"]] == [entity.id]
        assert [item["id"] for item in payload["kg"]["claims"]] == [claim.id]

    def test_json_export_rejects_existing_file_without_overwrite(
        self, client, tmp_path
    ):
        output_path = tmp_path / "export.json"
        output_path.write_text("{}", encoding="utf-8")

        r = client.post(
            "/api/export/json",
            json={"output_path": str(output_path)},
        )

        assert r.status_code == 409

    def test_json_export_missing_target_returns_404(self, client, tmp_path):
        r = client.post(
            "/api/export/json",
            json={
                "target_id": "no-such-doc",
                "output_path": str(tmp_path / "export.json"),
            },
        )

        assert r.status_code == 404


class TestHtmlExport:
    def test_exports_static_site_with_search_assets_and_kg(
        self, client, db, tmp_path
    ):
        folder = Document(
            id="folder-html",
            name="HTML Export",
            doc_type=DocType.folder,
        )
        image_path = tmp_path / "source.jpg"
        image_path.write_bytes(b"image bytes")
        doc = Document(
            id="doc-html",
            name="Photo Letter",
            parent_id=folder.id,
            doc_type=DocType.file,
            file_type=FileType.image,
            path=str(image_path),
            page_content="Searchable transcription.",
        )
        artifact = Artifact(
            id="artifact-html",
            document_id=doc.id,
            artifact_type="summary",
            content="HTML summary.",
        )
        entity = KnowledgeEntity(
            id="entity-html",
            canonical_name="Juan Perez",
            source_document_ids=[doc.id],
        )
        claim = KnowledgeClaim(
            id="claim-html",
            text="Juan Perez appears in the letter.",
            source_document_id=doc.id,
            entity_ids=[entity.id],
        )
        for item in [folder, doc, artifact, entity, claim]:
            db.save(item)

        output_path = tmp_path / "site"
        r = client.post(
            "/api/export/html",
            json={
                "target_id": folder.id,
                "output_path": str(output_path),
            },
        )

        assert r.status_code == 200
        data = r.json()
        assert data["document_count"] == 1
        assert data["assets"][0]["document_id"] == doc.id

        assert (output_path / "index.html").exists()
        assert (output_path / "js" / "search.js").exists()
        assert (output_path / "assets" / "Photo-Letter.jpg").read_bytes() == b"image bytes"

        index_html = (output_path / "index.html").read_text(encoding="utf-8")
        page_html = (
            output_path / "docs" / "photo-letter" / "index.html"
        ).read_text(encoding="utf-8")
        search_js = (output_path / "js" / "search.js").read_text(encoding="utf-8")

        assert "Photo Letter" in index_html
        assert "Searchable transcription." in page_html
        assert "../../assets/Photo-Letter.jpg" in page_html
        assert "Juan Perez" in page_html
        assert "Juan Perez appears in the letter." in page_html
        assert "Searchable transcription." in search_js

    def test_html_export_rejects_non_empty_output_without_overwrite(
        self, client, tmp_path
    ):
        output_path = tmp_path / "site"
        output_path.mkdir()
        (output_path / "index.html").write_text("existing", encoding="utf-8")

        r = client.post(
            "/api/export/html",
            json={"output_path": str(output_path)},
        )

        assert r.status_code == 409

    def test_html_export_missing_target_returns_404(self, client, tmp_path):
        r = client.post(
            "/api/export/html",
            json={
                "target_id": "no-such-doc",
                "output_path": str(tmp_path / "site"),
            },
        )

        assert r.status_code == 404
