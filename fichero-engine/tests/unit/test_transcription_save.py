"""
Tests for the #666 transcription-save fixes.

Three bugs were addressed:
1. db.py _parse_json_fields: NULL dict column caused ValidationError → now returns {}
2. llm_base.py save_artifact: non-dict doc.metadata caused silent failure → now guarded
3. vision_base.py: Apple Vision OCR stored text only on parent PDF, not page children
"""

import pytest
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_db():
    """Real Database instance backed by a temp DuckDB file."""
    from fichero.db import Database

    tmpdir = tempfile.mkdtemp()
    db_path = Path(tmpdir) / "test.duckdb"
    db = Database(db_path)
    yield db
    db.close()
    shutil.rmtree(tmpdir)


@pytest.fixture
def llm_config():
    from fichero.llm import LLMConfig

    return LLMConfig(provider="test", model="test-model")


# =============================================================================
# Fix 1: _parse_json_fields — NULL dict column → {} not None
# =============================================================================

class TestParseJsonFieldsNullMetadata:
    """db.py: _parse_json_fields must return {} for NULL dict columns."""

    def test_null_metadata_returns_empty_dict(self, temp_db):
        """Loading a document with NULL metadata gives metadata={}, not None."""
        from fichero.models import Document

        doc = Document(name="test.pdf", path="/test/test.pdf")
        temp_db.save(doc)

        temp_db.conn.execute(
            "UPDATE documents SET metadata = NULL WHERE id = ?",
            [doc.id],
        )

        retrieved = temp_db.get(Document, doc.id)
        assert retrieved is not None
        assert retrieved.metadata == {}

    def test_null_metadata_does_not_raise_validation_error(self, temp_db):
        """Loading a document with NULL metadata must not raise ValidationError."""
        from pydantic import ValidationError
        from fichero.models import Document

        doc = Document(name="scan.jpg", path="/scan.jpg")
        temp_db.save(doc)
        temp_db.conn.execute(
            "UPDATE documents SET metadata = NULL WHERE id = ?",
            [doc.id],
        )

        try:
            temp_db.get(Document, doc.id)
        except ValidationError as exc:
            pytest.fail(f"ValidationError raised when loading NULL metadata: {exc}")

    def test_non_null_metadata_still_round_trips(self, temp_db):
        """Normal metadata round-trip is unaffected by the NULL guard."""
        from fichero.models import Document

        doc = Document(
            name="photo.jpg",
            path="/photo.jpg",
            metadata={"width": 800, "height": 600},
        )
        temp_db.save(doc)

        retrieved = temp_db.get(Document, doc.id)
        assert retrieved.metadata == {"width": 800, "height": 600}


# =============================================================================
# Fix 2: save_artifact — guards against non-dict doc.metadata
# =============================================================================

class TestSaveArtifactNullMetadata:
    """llm_base.py: save_artifact must handle doc.metadata=None gracefully."""

    @pytest.mark.asyncio
    async def test_returns_artifact_id_when_metadata_is_none(self, llm_config):
        """save_artifact returns an artifact_id even when doc.metadata is None."""
        from fichero.workflows.tools.llm_base import save_artifact, LLMToolConfig

        mock_doc = MagicMock()
        mock_doc.id = "doc_null_meta"
        mock_doc.metadata = None  # Simulate NULL column from DB

        mock_db = MagicMock()
        mock_db.get.return_value = mock_doc

        tool_config = LLMToolConfig(
            artifact_type="transcription",
            update_page_content=True,
            trigger_embedding=False,
            metadata_field="transcription",
        )

        with patch("fichero.db.db_manager") as mock_manager:
            mock_manager.get_database.return_value = mock_db

            result = await save_artifact(
                document_id="doc_null_meta",
                file_path=None,
                content="Transcribed text",
                data=None,
                library_path="/lib.fichero",
                llm_config=llm_config,
                task_id=None,
                tool_config=tool_config,
            )

        assert result is not None
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_metadata_becomes_dict_with_field_set(self, llm_config):
        """save_artifact converts metadata from None to a dict and writes the field."""
        from fichero.workflows.tools.llm_base import save_artifact, LLMToolConfig

        mock_doc = MagicMock()
        mock_doc.id = "doc_meta_fix"
        mock_doc.metadata = None

        mock_db = MagicMock()
        mock_db.get.return_value = mock_doc

        tool_config = LLMToolConfig(
            artifact_type="transcription",
            update_page_content=False,
            trigger_embedding=False,
            metadata_field="transcription",
        )

        with patch("fichero.db.db_manager") as mock_manager:
            mock_manager.get_database.return_value = mock_db

            await save_artifact(
                document_id="doc_meta_fix",
                file_path=None,
                content="OCR output",
                data=None,
                library_path="/lib.fichero",
                llm_config=llm_config,
                task_id=None,
                tool_config=tool_config,
            )

        assert isinstance(mock_doc.metadata, dict)
        assert mock_doc.metadata.get("transcription") == "OCR output"

    @pytest.mark.asyncio
    async def test_artifact_id_returned_despite_metadata_decoration_failure(self, llm_config):
        """Artifact ID is returned even when the metadata-decoration db.save raises."""
        from fichero.workflows.tools.llm_base import save_artifact, LLMToolConfig

        mock_doc = MagicMock()
        mock_doc.id = "doc_phase2_fail"
        mock_doc.metadata = {}

        mock_db = MagicMock()
        mock_db.get.return_value = mock_doc
        # save(artifact) succeeds; save(doc) for metadata decoration raises
        mock_db.save.side_effect = [None, RuntimeError("disk full")]

        tool_config = LLMToolConfig(
            artifact_type="transcription",
            update_page_content=False,  # one save in phase 1, one in phase 2
            trigger_embedding=False,
            metadata_field="transcription",
        )

        with patch("fichero.db.db_manager") as mock_manager:
            mock_manager.get_database.return_value = mock_db

            result = await save_artifact(
                document_id="doc_phase2_fail",
                file_path=None,
                content="Some content",
                data=None,
                library_path="/lib.fichero",
                llm_config=llm_config,
                task_id=None,
                tool_config=tool_config,
            )

        # The artifact save succeeded (first db.save), so ID must be returned
        assert result is not None

    @pytest.mark.asyncio
    async def test_page_content_written_when_update_flag_set(self, llm_config):
        """save_artifact writes page_content to the document when configured."""
        from fichero.workflows.tools.llm_base import save_artifact, LLMToolConfig

        mock_doc = MagicMock()
        mock_doc.id = "doc_pc"
        mock_doc.metadata = {}

        mock_db = MagicMock()
        mock_db.get.return_value = mock_doc

        tool_config = LLMToolConfig(
            artifact_type="transcription",
            update_page_content=True,
            trigger_embedding=False,
            metadata_field=None,
        )

        with patch("fichero.db.db_manager") as mock_manager:
            mock_manager.get_database.return_value = mock_db

            result = await save_artifact(
                document_id="doc_pc",
                file_path=None,
                content="Full page text",
                data=None,
                library_path="/lib.fichero",
                llm_config=llm_config,
                task_id=None,
                tool_config=tool_config,
            )

        assert result is not None
        assert mock_doc.page_content == "Full page text"
        # artifact save + page_content save = 2 db.save calls
        assert mock_db.save.call_count == 2


# =============================================================================
# Fix 3: _propagate_to_page_children — per-page text to child Documents
# =============================================================================

class TestPropagateToPageChildren:
    """vision_base.py: _propagate_to_page_children writes per-page OCR to children."""

    @pytest.mark.asyncio
    async def test_writes_page_content_to_each_child(self):
        """Page texts are written to the matching child doc by sequence."""
        from fichero.workflows.tools.vision_base import _propagate_to_page_children

        page1 = MagicMock()
        page1.sequence = 1
        page1.metadata = {}
        page2 = MagicMock()
        page2.sequence = 2
        page2.metadata = {}
        page3 = MagicMock()
        page3.sequence = 3
        page3.metadata = {}

        mock_db = MagicMock()
        mock_db.query.return_value = [page1, page2, page3]

        with patch("fichero.db.db_manager") as mock_manager:
            mock_manager.get_database.return_value = mock_db

            await _propagate_to_page_children(
                "parent_pdf_id",
                ["Text from page 1", "Text from page 2", "Text from page 3"],
                "/lib.fichero",
            )

        assert page1.page_content == "Text from page 1"
        assert page2.page_content == "Text from page 2"
        assert page3.page_content == "Text from page 3"

    @pytest.mark.asyncio
    async def test_saves_and_embeds_each_updated_child(self):
        """db.save and db.embed are called once per page with non-empty text."""
        from fichero.workflows.tools.vision_base import _propagate_to_page_children

        page1 = MagicMock()
        page1.sequence = 1
        page1.metadata = {}
        page2 = MagicMock()
        page2.sequence = 2
        page2.metadata = {}

        mock_db = MagicMock()
        mock_db.query.return_value = [page1, page2]

        with patch("fichero.db.db_manager") as mock_manager:
            mock_manager.get_database.return_value = mock_db

            await _propagate_to_page_children(
                "parent_id",
                ["Page 1 text", "Page 2 text"],
                "/lib.fichero",
            )

        assert mock_db.save.call_count == 2
        assert mock_db.embed.call_count == 2

    @pytest.mark.asyncio
    async def test_skips_empty_page_text(self):
        """Empty strings in page_texts are not written to children."""
        from fichero.workflows.tools.vision_base import _propagate_to_page_children

        page1 = MagicMock()
        page1.sequence = 1
        page1.metadata = {}
        page2 = MagicMock()
        page2.sequence = 2
        page2.metadata = {}

        mock_db = MagicMock()
        mock_db.query.return_value = [page1, page2]

        with patch("fichero.db.db_manager") as mock_manager:
            mock_manager.get_database.return_value = mock_db

            await _propagate_to_page_children(
                "parent_id",
                ["Page 1 text", ""],  # page 2 has no OCR output
                "/lib.fichero",
            )

        assert page1.page_content == "Page 1 text"
        assert mock_db.save.call_count == 1
        assert mock_db.embed.call_count == 1

    @pytest.mark.asyncio
    async def test_no_children_does_nothing(self):
        """When parent has no page children, function exits without any DB writes."""
        from fichero.workflows.tools.vision_base import _propagate_to_page_children

        mock_db = MagicMock()
        mock_db.query.return_value = []

        with patch("fichero.db.db_manager") as mock_manager:
            mock_manager.get_database.return_value = mock_db

            await _propagate_to_page_children("orphan_id", ["text"], "/lib.fichero")

        mock_db.save.assert_not_called()
        mock_db.embed.assert_not_called()

    @pytest.mark.asyncio
    async def test_null_metadata_on_child_becomes_dict(self):
        """Children with metadata=None get it replaced with {} before save."""
        from fichero.workflows.tools.vision_base import _propagate_to_page_children

        page = MagicMock()
        page.sequence = 1
        page.metadata = None  # NULL in DB

        mock_db = MagicMock()
        mock_db.query.return_value = [page]

        with patch("fichero.db.db_manager") as mock_manager:
            mock_manager.get_database.return_value = mock_db

            await _propagate_to_page_children(
                "parent_id",
                ["Page text"],
                "/lib.fichero",
            )

        assert isinstance(page.metadata, dict)
        assert page.page_content == "Page text"

    @pytest.mark.asyncio
    async def test_sequence_maps_correctly_to_zero_indexed_texts(self):
        """sequence=2 maps to page_texts[1] (1-based → 0-indexed)."""
        from fichero.workflows.tools.vision_base import _propagate_to_page_children

        # Only a single page with sequence=2 (second page of a multi-page PDF)
        page = MagicMock()
        page.sequence = 2
        page.metadata = {}

        mock_db = MagicMock()
        mock_db.query.return_value = [page]

        with patch("fichero.db.db_manager") as mock_manager:
            mock_manager.get_database.return_value = mock_db

            await _propagate_to_page_children(
                "parent_id",
                ["First page text", "Second page text"],
                "/lib.fichero",
            )

        assert page.page_content == "Second page text"
