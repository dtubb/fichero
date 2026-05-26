"""Tests for document export routes."""

from fichero.models import Artifact, DocType, Document, FileType


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
