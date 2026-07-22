"""
Integration tests for the backend data layer.

Tests the connections between:
- db.py (DuckDB + LanceDB)
- ingest.py
- loaders/
- keychain.py
- bookmarks.py
"""

from pathlib import Path
from unittest.mock import patch, MagicMock

from fichero.db import Database, SearchResult
from fichero.models.knowledge import EntityType, KnowledgeClaim, KnowledgeEntity
from fichero.models import DocType, Document, FileType
from fichero.ingest import ingest_file, ingest_folder, IngestMode

TEST_EMBEDDING_DIM = 1024


class TestDatabaseSearch:
    """Test search integration in db.py."""

    def test_embed_document_with_content(self, tmp_path):
        """Embedding works when document has page_content."""
        db = Database(tmp_path / "test.duckdb")

        doc = Document(
            name="letter.txt",
            page_content="Dear Sir, I am writing to inquire about the property.",
        )
        db.save(doc)

        # Mock the embedder to avoid loading model
        with patch.object(db, '_embed_text', return_value=[0.1] * TEST_EMBEDDING_DIM):
            result = db.embed(doc)

        assert result is True
        assert db.has_embedding(doc.id)
        db.close()

    def test_embed_skips_short_content(self, tmp_path):
        """Embedding skips documents with short/no content."""
        db = Database(tmp_path / "test.duckdb")

        doc = Document(name="x.txt", page_content="hi")
        db.save(doc)

        result = db.embed(doc)
        assert result is False
        db.close()

    def test_search_returns_results(self, tmp_path):
        """Search finds embedded documents."""
        db = Database(tmp_path / "test.duckdb")

        # Create and embed a document
        doc = Document(
            name="contract.pdf",
            page_content="This employment contract outlines the terms.",
        )
        db.save(doc)

        with patch.object(db, '_embed_text', return_value=[0.1] * TEST_EMBEDDING_DIM):
            db.embed(doc)

        with patch.object(db, '_embed_text', return_value=[0.1] * TEST_EMBEDDING_DIM):
            results, total_count, _stats = db.search("employment terms")

        assert len(results) >= 1
        assert total_count >= 1
        assert results[0].document_id == doc.id
        db.close()

    def test_search_prefers_indexed_pdf_pages_over_parent_document(self, tmp_path):
        """PDF search should return page-scoped hits when page embeddings exist."""
        db = Database(tmp_path / "test.duckdb")

        parent = Document(
            id="pdf-parent",
            name="archive.pdf",
            doc_type=DocType.file,
            file_type=FileType.pdf,
            page_content=(
                "Whole PDF text blob mentioning Camilo. "
                "This should not be returned when pages are indexed."
            ),
        )
        page1 = Document(
            id="pdf-parent-page-1",
            parent_id=parent.id,
            name="archive.pdf - Page 1",
            doc_type=DocType.page,
            sequence=1,
            page_content="A page about unrelated correspondence.",
        )
        page2 = Document(
            id="pdf-parent-page-2",
            parent_id=parent.id,
            name="archive.pdf - Page 2",
            doc_type=DocType.page,
            sequence=2,
            page_content="Camilo appears in this passage with context.",
        )
        db.save(parent)
        db.save(page1)
        db.save(page2)

        query_vector = [1.0, 0.0]
        db.save_embedding(parent, query_vector, parent.page_content)
        db.save_embedding(page1, [0.0, 1.0], page1.page_content)
        db.save_embedding(page2, query_vector, page2.page_content)

        with patch.object(db, "_embed_text", return_value=query_vector):
            results, total_count, _stats = db.search(
                "Camilo",
                min_score=0.55,
                search_type="semantic",
            )

        assert total_count == 1
        assert [result.document_id for result in results] == [page2.id]
        assert results[0].content_preview == page2.page_content
        db.close()

    def test_search_keeps_pdf_parent_when_page_children_are_not_indexed(self, tmp_path):
        """Legacy libraries with only parent embeddings still return results."""
        db = Database(tmp_path / "test.duckdb")

        parent = Document(
            id="pdf-parent",
            name="archive.pdf",
            doc_type=DocType.file,
            file_type=FileType.pdf,
            page_content="Whole PDF text blob mentioning Camilo.",
        )
        page = Document(
            id="pdf-parent-page-1",
            parent_id=parent.id,
            name="archive.pdf - Page 1",
            doc_type=DocType.page,
            sequence=1,
            page_content="Camilo appears here but has no embedding yet.",
        )
        db.save(parent)
        db.save(page)

        query_vector = [1.0, 0.0]
        db.save_embedding(parent, query_vector, parent.page_content)

        with patch.object(db, "_embed_text", return_value=query_vector):
            results, total_count, _stats = db.search(
                "Camilo",
                min_score=0.55,
                search_type="semantic",
            )

        assert total_count == 1
        assert [result.document_id for result in results] == [parent.id]
        db.close()

    def test_search_empty_query_returns_empty(self, tmp_path):
        """Search with empty query returns empty list."""
        db = Database(tmp_path / "test.duckdb")
        results, total_count, stats = db.search("")
        assert results == []
        assert total_count == 0
        assert stats.get("search_type") == "none"
        db.close()

    def test_embedding_stats(self, tmp_path):
        """embedding_stats reports correct counts."""
        db = Database(tmp_path / "test.duckdb")

        # Initially no embeddings
        stats = db.embedding_stats()
        assert stats["indexed_count"] == 0
        assert stats["entity_indexed_count"] == 0
        assert stats["claim_indexed_count"] == 0

        # Add embedding
        doc = Document(name="test.pdf", page_content="Some content here")
        entity = KnowledgeEntity(
            canonical_name="Marshall",
            entity_type=EntityType.person,
        )
        claim = KnowledgeClaim(
            text="Marshall kept a diary.",
            source_document_id=doc.id,
            subject_canonical="Marshall",
            predicate_verb="kept",
            object_phrase="a diary",
            source_excerpt="Marshall kept a diary.",
        )
        db.save(doc)
        db.save(entity)
        db.save(claim)

        with patch.object(db, '_embed_text', return_value=[0.1] * TEST_EMBEDDING_DIM), patch.object(
            db,
            "_embed_texts",
            side_effect=[
                [[0.1] * TEST_EMBEDDING_DIM],
                [[0.1] * TEST_EMBEDDING_DIM],
            ],
        ):
            db.embed(doc)
            db.embed_entities([entity])
            db.embed_claims([claim])

        stats = db.embedding_stats()
        assert stats["indexed_count"] == 1
        assert stats["entity_indexed_count"] == 1
        assert stats["claim_indexed_count"] == 1
        db.close()

    def test_entity_alias_expansion_resolves_related_surface_forms(self, tmp_path):
        """Entity query expands to canonical + known aliases."""
        db = Database(tmp_path / "test.duckdb")

        doc = Document(
            id="doc-libertador",
            name="chronicle.txt",
            page_content="El Libertador entered the city at dawn.",
        )
        entity = KnowledgeEntity(
            id="entity-bolivar",
            canonical_name="Simón Bolívar",
            aliases=["Bolívar", "El Libertador"],
        )
        claim = KnowledgeClaim(
            id="claim-bolivar",
            text="El Libertador entered the city at dawn.",
            source_document_id=doc.id,
            entity_ids=[entity.id],
        )
        db.save(doc)
        db.save(entity)
        db.save(claim)

        expanded_terms, matched_entity_ids = db._expand_query_with_entity_aliases("Bolívar")

        assert entity.id in matched_entity_ids
        assert "el libertador" in expanded_terms
        assert "simon bolivar" in expanded_terms
        db.close()

    def test_entity_bonus_doc_ids_empty_for_non_entity_query(self, tmp_path):
        """Regular terms should not resolve unrelated entities."""
        db = Database(tmp_path / "test.duckdb")

        doc = Document(
            id="doc-libertador-2",
            name="chronicle.txt",
            page_content="El Libertador entered the city at dawn.",
        )
        entity = KnowledgeEntity(
            id="entity-bolivar-2",
            canonical_name="Simón Bolívar",
            aliases=["Bolívar", "El Libertador"],
        )
        db.save(doc)
        db.save(entity)

        expanded_terms, matched_entity_ids = db._expand_query_with_entity_aliases(
            "unrelated term"
        )
        boosted_doc_ids = db._entity_bonus_doc_ids(matched_entity_ids)

        assert matched_entity_ids == set()
        assert boosted_doc_ids == set()
        assert "unrelated term" in expanded_terms
        db.close()

    def test_delete_embedding(self, tmp_path):
        """delete_embedding removes from index."""
        db = Database(tmp_path / "test.duckdb")

        doc = Document(name="test.pdf", page_content="Content to embed")
        db.save(doc)

        with patch.object(db, '_embed_text', return_value=[0.1] * TEST_EMBEDDING_DIM):
            db.embed(doc)

        assert db.has_embedding(doc.id)
        db.delete_embedding(doc.id)
        assert not db.has_embedding(doc.id)
        db.close()


class TestSaveWithAutoEmbed:
    """Test db.save() with auto_embed flag."""

    def test_save_auto_embed_creates_embedding(self, tmp_path):
        """save() with auto_embed=True creates embedding."""
        db = Database(tmp_path / "test.duckdb")

        doc = Document(
            name="letter.pdf",
            page_content="Long enough content for embedding",
        )

        with patch.object(db, '_embed_text', return_value=[0.1] * TEST_EMBEDDING_DIM):
            db.save(doc, auto_embed=True)

        assert db.has_embedding(doc.id)
        db.close()

    def test_save_no_auto_embed_by_default(self, tmp_path):
        """save() without auto_embed doesn't create embedding."""
        db = Database(tmp_path / "test.duckdb")

        doc = Document(
            name="letter.pdf",
            page_content="Long enough content for embedding",
        )
        db.save(doc)  # No auto_embed

        assert not db.has_embedding(doc.id)
        db.close()

    def test_save_auto_embed_skips_empty_content(self, tmp_path):
        """save() with auto_embed skips if no page_content."""
        db = Database(tmp_path / "test.duckdb")

        doc = Document(name="image.jpg")  # No page_content
        db.save(doc, auto_embed=True)

        assert not db.has_embedding(doc.id)
        db.close()


class TestIngestWithTextExtraction:
    """Test ingest with text extraction enabled."""

    def test_ingest_file_extract_text(self, tmp_path):
        """ingest_file with extract_text uses loaders."""
        # Create test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("Sample document content for testing.")

        # Mock the loader module
        mock_content = MagicMock()
        mock_content.text = "Extracted text from loader"

        async def mock_load_media(path):
            return mock_content

        with patch('fichero.loaders.load_media', mock_load_media):
            with patch('fichero.db.db') as mock_db:
                mock_db.save = MagicMock()
                mock_db.embed = MagicMock()

                doc = ingest_file(
                    test_file,
                    extract_text=True,
                    save=False,
                )

        assert doc.page_content == "Extracted text from loader"
        assert doc.metadata.get("text_extracted") is True

    def test_ingest_file_auto_embed(self, tmp_path):
        """ingest_file with auto_embed creates embedding."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Sample content")

        with patch('fichero.db.db') as mock_db:
            mock_db.save = MagicMock()
            mock_db.embed = MagicMock()

            async def mock_load_media(path):
                content = MagicMock()
                content.text = "Extracted text"
                return content

            with patch('fichero.loaders.load_media', mock_load_media):
                ingest_file(
                    test_file,
                    extract_text=True,
                    auto_embed=True,
                    save=True,
                )

            mock_db.embed.assert_called()

    def test_ingest_file_skips_non_extractable(self, tmp_path):
        """ingest_file skips extraction for images."""
        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(b"fake image content")

        with patch('fichero.db.db') as mock_db:
            mock_db.save = MagicMock()

            # load_media should NOT be called for images
            with patch('fichero.loaders.load_media') as mock_loader:
                ingest_file(
                    test_file,
                    extract_text=True,  # Enabled but should skip
                    save=True,
                )

                # Image files shouldn't have text extraction called
                mock_loader.assert_not_called()


class TestIngestFolderIntegration:
    """Test ingest_folder with all options."""

    def test_ingest_folder_with_text_extraction(self, tmp_path):
        """ingest_folder extracts text from documents."""
        folder = tmp_path / "docs"
        folder.mkdir()
        (folder / "doc1.txt").write_text("Content 1")
        (folder / "doc2.txt").write_text("Content 2")

        with patch('fichero.db.db') as mock_db:
            mock_db.save = MagicMock()
            mock_db.query = MagicMock(return_value=[])
            mock_db.embed = MagicMock()

            async def mock_load_media(path):
                content = MagicMock()
                content.text = f"Text from {path}"
                return content

            with patch('fichero.loaders.load_media', mock_load_media):
                docs = ingest_folder(
                    folder,
                    extract_text=True,
                    auto_embed=False,
                )

        assert len(docs) == 2
        # Both docs should have extracted text
        for doc in docs:
            assert doc.page_content is not None


class TestKeychainRubicon:
    """Test keychain uses Rubicon (not subprocess)."""

    def test_keychain_uses_security_command(self):
        """keychain.py uses macOS security command via subprocess."""
        import fichero.security.keychain as keychain

        # Check that the module uses subprocess to call security command
        source = Path(keychain.__file__).read_text()

        # Should use subprocess to call 'security' command-line tool
        assert "subprocess" in source
        assert "security" in source

    def test_keychain_has_service_name(self):
        """keychain.py should define a service name."""
        import fichero.security.keychain as keychain

        # Module should define SERVICE constant
        source = Path(keychain.__file__).read_text()
        assert "SERVICE" in source

    def test_keychain_is_available_check(self):
        """is_available() checks if running on macOS."""
        from fichero.security.keychain import is_available

        # Should return bool based on platform (True on macOS)
        result = is_available()
        assert isinstance(result, bool)


class TestSearchResultDataclass:
    """Test SearchResult dataclass."""

    def test_search_result_creation(self):
        """SearchResult holds all required fields."""
        result = SearchResult(
            document_id="abc123",
            score=0.95,
            content_preview="This is a preview...",
            metadata={"name": "test.pdf"},
        )

        assert result.document_id == "abc123"
        assert result.score == 0.95
        assert "preview" in result.content_preview

    def test_search_result_repr(self):
        """SearchResult has readable repr."""
        result = SearchResult(
            document_id="abc123",
            score=0.95,
            content_preview="Short preview",
            metadata={},
        )

        repr_str = repr(result)
        assert "abc123" in repr_str
        assert "0.95" in repr_str


class TestBookmarksIntegration:
    """Test bookmarks are created during ingest."""

    def test_ingest_link_mode_creates_bookmark(self, tmp_path):
        """LINK mode creates bookmark in metadata."""
        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(b"fake image")

        with patch('fichero.bookmarks.create_bookmark', return_value=b"fake_bookmark"):
            with patch('fichero.db.db') as mock_db:
                mock_db.save = MagicMock()

                doc = ingest_file(
                    test_file,
                    mode=IngestMode.LINK,
                    save=True,
                )

        # Bookmark should be base64 encoded in metadata
        assert "bookmark" in doc.metadata

    def test_ingest_copy_mode_no_bookmark(self, tmp_path):
        """COPY mode doesn't create bookmark."""
        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(b"fake image")

        # Create the destination for copy
        (tmp_path / "copy.jpg").write_bytes(b"fake image")

        with patch('fichero.ingest._copy_to_library', return_value=tmp_path / "copy.jpg"):
            with patch('fichero.db.db') as mock_db:
                mock_db.save = MagicMock()

                doc = ingest_file(
                    test_file,
                    mode=IngestMode.COPY,
                    save=True,
                )

        # No bookmark in copy mode
        assert "bookmark" not in doc.metadata
