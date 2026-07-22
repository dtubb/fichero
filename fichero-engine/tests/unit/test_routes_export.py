"""Tests for document export routes."""

import json
from types import SimpleNamespace
from urllib.parse import quote

from fichero.models.knowledge import ClaimType, EntityType
from fichero.loaders.xlsx_reader import read_xlsx_records
from fichero.models import Artifact, DocType, Document, FileType
from fichero.models import KnowledgeClaim, KnowledgeEntity


class TestMarkdownFolderExport:
    def test_forwards_library_header_to_export_service(
        self, client, monkeypatch, tmp_path
    ):
        captured: dict[str, object] = {}

        def fake_export_markdown_folder(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                output_path=str(kwargs["output_path"]),
                files=[],
                assets=[],
                document_count=0,
            )

        monkeypatch.setattr(
            "fichero.api.routes.export.export_markdown_folder",
            fake_export_markdown_folder,
        )

        library_path = "/tmp/Export Library.fichero"
        response = client.post(
            "/api/export/markdown-folder",
            headers={"X-Fichero-Library-Path": quote(library_path)},
            json={"output_path": str(tmp_path / "export")},
        )

        assert response.status_code == 200
        assert captured["package_path"] == library_path

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
        image_path = db.path.parent / "files" / "source.jpg"
        image_path.parent.mkdir(parents=True, exist_ok=True)
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
        image_path = db.path.parent / "files" / "photo.jpg"
        image_path.parent.mkdir(parents=True, exist_ok=True)
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

    def test_exports_docx_with_knowledge_graph_appendix(self, client, db, tmp_path):
        import zipfile

        doc = Document(
            id="word-kg-doc",
            name="KG Source",
            doc_type=DocType.file,
            file_type=FileType.text,
            page_content="Source text.",
        )
        entity = KnowledgeEntity(
            id="entity-pedro",
            canonical_name="Pedro",
            entity_type=EntityType.person,
            description="Witness",
            source_document_ids=[doc.id],
        )
        claim = KnowledgeClaim(
            id="claim-pedro",
            text="Pedro testified in 1933.",
            source_document_id=doc.id,
            source_page_label="4",
            source_excerpt="Pedro testified",
            entity_ids=[entity.id],
            claim_type=ClaimType.fact,
        )
        db.save(doc)
        db.save(entity)
        db.save(claim)

        output_path = tmp_path / "kg.docx"
        r = client.post(
            "/api/export/word",
            json={
                "target_id": doc.id,
                "output_path": str(output_path),
            },
        )

        assert r.status_code == 200
        with zipfile.ZipFile(output_path) as docx:
            document_xml = docx.read("word/document.xml").decode()

        assert "Knowledge Graph Appendix" in document_xml
        assert "Pedro (person): Witness" in document_xml
        assert "Pedro testified in 1933. [source: 4]" in document_xml
        assert "Excerpt: Pedro testified" in document_xml

    def test_word_export_can_omit_knowledge_graph_appendix(
        self, client, db, tmp_path
    ):
        import zipfile

        doc = Document(
            id="word-no-kg-doc",
            name="No KG Source",
            doc_type=DocType.file,
            file_type=FileType.text,
            page_content="Source text.",
        )
        entity = KnowledgeEntity(
            id="entity-hidden",
            canonical_name="Hidden",
            source_document_ids=[doc.id],
        )
        db.save(doc)
        db.save(entity)

        output_path = tmp_path / "no-kg.docx"
        r = client.post(
            "/api/export/word",
            json={
                "target_id": doc.id,
                "output_path": str(output_path),
                "include_knowledge_graph": False,
            },
        )

        assert r.status_code == 200
        with zipfile.ZipFile(output_path) as docx:
            document_xml = docx.read("word/document.xml").decode()

        assert "Knowledge Graph Appendix" not in document_xml
        assert "Hidden" not in document_xml

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


class TestExcelExport:
    def test_exports_xlsx_documents_entities_and_claims(self, client, db, tmp_path):
        folder = Document(
            id="folder-excel",
            name="Excel Export",
            doc_type=DocType.folder,
        )
        doc = Document(
            id="excel-doc",
            name="Excel Source",
            parent_id=folder.id,
            doc_type=DocType.file,
            file_type=FileType.text,
            page_content="Transcript text.",
            metadata={"box": "A1"},
        )
        entity = KnowledgeEntity(
            id="excel-entity",
            canonical_name="Maria",
            entity_type=EntityType.person,
            aliases=["María"],
            source_document_ids=[doc.id],
        )
        claim = KnowledgeClaim(
            id="excel-claim",
            text="Maria signed the letter.",
            source_document_id=doc.id,
            source_page_label="7",
            source_excerpt="Maria signed",
            entity_ids=[entity.id],
            claim_type=ClaimType.fact,
        )
        db.save(folder)
        db.save(doc)
        db.save(entity)
        db.save(claim)

        output_path = tmp_path / "export.xlsx"
        r = client.post(
            "/api/export/excel",
            json={
                "target_id": folder.id,
                "output_path": str(output_path),
            },
        )

        assert r.status_code == 200
        data = r.json()
        assert data["document_count"] == 1
        assert data["entity_count"] == 1
        assert data["claim_count"] == 1
        assert data["bytes_written"] > 0

        documents = read_xlsx_records(output_path, sheet_index=0)
        entities = read_xlsx_records(output_path, sheet_index=1)
        claims = read_xlsx_records(output_path, sheet_index=2)

        assert documents[0]["id"] == doc.id
        assert documents[0]["transcription"] == "Transcript text."
        assert documents[0]["metadata"] == '{"box": "A1"}'
        assert entities[0]["canonical_name"] == "Maria"
        assert entities[0]["entity_type"] == "person"
        assert claims[0]["text"] == "Maria signed the letter."
        assert claims[0]["source_page_label"] == "7"
        assert claims[0]["entity_ids"] == '["excel-entity"]'

    def test_excel_export_rejects_existing_file_without_overwrite(
        self, client, tmp_path
    ):
        output_path = tmp_path / "export.xlsx"
        output_path.write_bytes(b"existing")

        r = client.post(
            "/api/export/excel",
            json={"output_path": str(output_path)},
        )

        assert r.status_code == 409


class TestEleventySiteExport:
    def test_route_forwards_library_header_and_surfaces_oserror(
        self, client, monkeypatch, tmp_path
    ):
        captured: dict[str, object] = {}

        def fake_export_eleventy_site(**kwargs):
            captured.update(kwargs)
            raise OSError("disk full")

        monkeypatch.setattr(
            "fichero.api.routes.export.export_eleventy_site",
            fake_export_eleventy_site,
        )

        library_path = "/tmp/Site Library.fichero"
        response = client.post(
            "/api/export/eleventy-site",
            headers={"X-Fichero-Library-Path": quote(library_path)},
            json={"output_path": str(tmp_path / "site")},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "disk full"
        assert captured["package_path"] == library_path

    def test_publishes_collections_subcollections_and_scaffold(
        self, client, db, tmp_path
    ):
        # root/ → Coleccion A/ (collection) → Subseccion/ (subcollection) → doc
        root = Document(id="site-root", name="Archivo", doc_type=DocType.folder)
        coll = Document(
            id="coll-a", name="Coleccion A", parent_id=root.id,
            doc_type=DocType.folder,
        )
        sub = Document(
            id="sub-1", name="Subseccion", parent_id=coll.id,
            doc_type=DocType.folder,
        )
        doc = Document(
            id="doc-1", name="Carta Uno", parent_id=sub.id,
            doc_type=DocType.file, file_type=FileType.text,
            page_content="El contenido de la carta.",
        )
        for d in (root, coll, sub, doc):
            db.save(d)

        output_path = tmp_path / "site"
        r = client.post(
            "/api/export/eleventy-site",
            json={"target_id": root.id, "output_path": str(output_path)},
        )

        assert r.status_code == 200, r.text
        data = r.json()
        assert data["document_count"] == 1
        assert data["collection_count"] == 1  # "Coleccion A"

        # Buildable + deployable scaffolding exists.
        assert (output_path / "package.json").exists()
        assert (output_path / ".eleventy.js").exists()
        assert (output_path / "netlify.toml").exists()
        assert (output_path / "src" / "index.md").exists()

        # Folder hierarchy → collection/subcollection directories.
        page = output_path / "src" / "Coleccion-A" / "Subseccion" / "Carta-Uno.md"
        assert page.exists()
        body = page.read_text()
        assert "# Carta Uno" in body
        assert "El contenido de la carta." in body
        # Top-level folder is the 11ty collection tag.
        assert "Coleccion-A" in body
        assert not (output_path / "src" / "entities").exists()

    def test_rejects_non_empty_output_without_overwrite(self, client, tmp_path):
        output_path = tmp_path / "site"
        output_path.mkdir()
        (output_path / "existing.txt").write_text("x")

        r = client.post(
            "/api/export/eleventy-site",
            json={"output_path": str(output_path)},
        )
        assert r.status_code == 409

    def test_missing_target_returns_404(self, client, tmp_path):
        r = client.post(
            "/api/export/eleventy-site",
            json={"target_id": "nope", "output_path": str(tmp_path / "site")},
        )
        assert r.status_code == 404

    def test_publishes_entity_claim_and_provenance_indexes(self, client, db, tmp_path):
        root = Document(id="site-root-kg", name="Archivo", doc_type=DocType.folder)
        box = Document(
            id="site-box-kg",
            name="Caja 7",
            parent_id=root.id,
            doc_type=DocType.folder,
        )
        expediente = Document(
            id="site-exp-kg",
            name="Expediente 12",
            parent_id=box.id,
            doc_type=DocType.folder,
        )
        doc = Document(
            id="site-doc-kg",
            name="Carta Uno",
            parent_id=expediente.id,
            doc_type=DocType.file,
            file_type=FileType.text,
            page_label="1r",
            page_content="Pedro signed the petition.",
        )
        entity = KnowledgeEntity(
            id="site-entity-kg",
            canonical_name="Pedro",
            entity_type=EntityType.person,
            source_document_ids=[doc.id],
        )
        claim = KnowledgeClaim(
            id="site-claim-kg",
            text="Pedro signed the petition.",
            source_document_id=doc.id,
            source_page_label="1r",
            source_excerpt="Pedro signed",
            entity_ids=[entity.id],
            claim_type=ClaimType.fact,
        )
        for row in (root, box, expediente, doc, entity, claim):
            db.save(row)

        output_path = tmp_path / "site-kg"
        r = client.post(
            "/api/export/eleventy-site",
            json={"target_id": root.id, "output_path": str(output_path)},
        )

        assert r.status_code == 200, r.text
        entity_page = output_path / "src" / "entities" / "Pedro.md"
        claims_index = output_path / "src" / "claims" / "index.md"
        box_index = output_path / "src" / "box-collections" / "Caja-7.md"
        expediente_index = output_path / "src" / "expedientes" / "Expediente-12.md"

        assert entity_page.exists()
        assert claims_index.exists()
        assert box_index.exists()
        assert expediente_index.exists()

        entity_body = entity_page.read_text(encoding="utf-8")
        assert "[Carta Uno](../../Caja-7/Expediente-12/Carta-Uno/)" in entity_body
        assert "Expediente 12" in entity_body
        assert "Caja 7" in entity_body
        assert "localhost" not in entity_body
        assert "/api/" not in entity_body

        claims_body = claims_index.read_text(encoding="utf-8")
        assert "[Carta Uno](../Caja-7/Expediente-12/Carta-Uno/)" in claims_body

        search_page = output_path / "src" / "search.md"
        search_body = search_page.read_text(encoding="utf-8")
        assert '"title": "Carta Uno"' in search_body
        assert '"title": "Pedro"' in search_body
        assert '"url": "../Caja-7/Expediente-12/Carta-Uno/"' in search_body
        assert '"url": "../entities/Pedro/"' in search_body

    def test_publishes_special_character_entity_slug_and_claims_without_provenance(
        self, client, db, tmp_path
    ):
        root = Document(id="site-root-slug", name="Archivo", doc_type=DocType.folder)
        doc = Document(
            id="site-doc-slug",
            name='Carta "Niño"',
            parent_id=root.id,
            doc_type=DocType.file,
            file_type=FileType.text,
            page_content="Contenido exportado.",
        )
        entity = KnowledgeEntity(
            id="site-entity-slug",
            canonical_name='Señor / Archivo "A"',
            entity_type=EntityType.person,
            source_document_ids=[doc.id],
        )
        claim = KnowledgeClaim(
            id="site-claim-no-source",
            text="Afirmacion sin fuente.",
            entity_ids=[entity.id],
            claim_type=ClaimType.fact,
        )
        for row in (root, doc, entity, claim):
            db.save(row)

        output_path = tmp_path / "site-special-slug"
        r = client.post(
            "/api/export/eleventy-site",
            json={"target_id": root.id, "output_path": str(output_path)},
        )

        assert r.status_code == 200, r.text
        entity_files = sorted((output_path / "src" / "entities").glob("*.md"))
        assert [path.name for path in entity_files] == ["Se-or-Archivo-A.md"]
        assert '# Señor / Archivo "A"' in entity_files[0].read_text(encoding="utf-8")

        claims_index = output_path / "src" / "claims" / "index.md"
        assert claims_index.exists()
        assert "_No claims exported._" in claims_index.read_text(encoding="utf-8")

    def test_publishes_all_claim_provenance_sources_in_knowledge_indexes(
        self, client, db, tmp_path
    ):
        root = Document(id="site-root-chain", name="Archivo", doc_type=DocType.folder)
        primary = Document(
            id="site-doc-chain-primary",
            name="Source Letter",
            parent_id=root.id,
            doc_type=DocType.file,
            file_type=FileType.text,
            page_content="Primary source.",
        )
        secondary = Document(
            id="site-doc-chain-secondary",
            name="Later Summary",
            parent_id=root.id,
            doc_type=DocType.file,
            file_type=FileType.text,
            page_content="Secondary source.",
        )
        claim = KnowledgeClaim(
            id="site-claim-chain",
            text="Linked across both sources.",
            source_document_id=primary.id,
            source_ids=[secondary.id],
            claim_type=ClaimType.fact,
        )
        for row in (root, primary, secondary, claim):
            db.save(row)

        output_path = tmp_path / "site-chain"
        r = client.post(
            "/api/export/eleventy-site",
            json={"target_id": root.id, "output_path": str(output_path)},
        )

        assert r.status_code == 200, r.text
        claims_body = (output_path / "src" / "claims" / "index.md").read_text(
            encoding="utf-8"
        )
        assert "[Source Letter](../Source-Letter/)" in claims_body
        assert "[Later Summary](../Later-Summary/)" in claims_body

    def test_embeds_static_search_index_with_quotes_unicode_and_no_engine_dependency(
        self, client, db, tmp_path
    ):
        root = Document(id="site-root-search", name="Archivo", doc_type=DocType.folder)
        doc = Document(
            id="site-doc-search",
            name='Carta "Niño"',
            parent_id=root.id,
            doc_type=DocType.file,
            file_type=FileType.text,
            page_content='Linea con "comillas" y Bogotá.',
        )
        entity = KnowledgeEntity(
            id="site-entity-search",
            canonical_name="Señora Bogotá",
            entity_type=EntityType.person,
            source_document_ids=[doc.id],
            description="Cita “textual” para buscar.",
        )
        for row in (root, doc, entity):
            db.save(row)

        output_path = tmp_path / "site-search"
        r = client.post(
            "/api/export/eleventy-site",
            json={"target_id": root.id, "output_path": str(output_path)},
        )

        assert r.status_code == 200, r.text
        search_body = (output_path / "src" / "search.md").read_text(encoding="utf-8")
        index_json = search_body.split(
            '<script type="application/json" id="search-index">\n', 1
        )[1].split("\n</script>", 1)[0]
        entries = json.loads(index_json)

        assert {"title": 'Carta "Niño"', "kind": "document"} in [
            {"title": entry["title"], "kind": entry["kind"]} for entry in entries
        ]
        assert {"title": "Señora Bogotá", "kind": "entity"} in [
            {"title": entry["title"], "kind": entry["kind"]} for entry in entries
        ]
        assert 'Linea con "comillas" y Bogotá.' in {entry["text"] for entry in entries}
        assert "Type to search this export." in search_body
        assert "render('');" in search_body
        assert "fetch(" not in search_body
        assert "XMLHttpRequest" not in search_body
        assert "WebSocket" not in search_body
        assert "localhost" not in search_body
        assert "/api/" not in search_body
