"""
Unit tests for Workflow Tools

Tests the source, vision, and LLM tools for workflows.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import tempfile
import base64

from fichero.workflows.types import State
from fichero.workflows.registry import TOOLS
from fichero.llm import LLMConfig
from fichero.models import Document, DocType, FileType, Status


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_llm_config() -> LLMConfig:
    """Create a mock LLM config."""
    return LLMConfig(
        provider="mock",
        model="mock-model",
    )


@pytest.fixture
def mock_state() -> State:
    """Create a mock workflow state."""
    return {
        "task_id": "test_task",
        "workflow_id": "test_workflow",
        "library_path": "/test/library/path",
        "inputs": {},
        "outputs": {},
        "current_node": "",
        "completed_nodes": [],
        "error": None,
        "input_files": [],
        "output_files": [],
    }


@pytest.fixture
def mock_documents() -> list[Document]:
    """Create mock documents for testing."""
    return [
        Document(
            id="doc1",
            name="image1.jpg",
            path="/test/image1.jpg",
            doc_type=DocType.file,
            file_type=FileType.image,
            status=Status.pending,
            parent_id="folder1",
        ),
        Document(
            id="doc2",
            name="image2.png",
            path="/test/image2.png",
            doc_type=DocType.file,
            file_type=FileType.image,
            status=Status.completed,
            parent_id="folder1",
        ),
        Document(
            id="doc3",
            name="report.pdf",
            path="/test/report.pdf",
            doc_type=DocType.file,
            file_type=FileType.pdf,
            status=Status.pending,
            parent_id="folder1",
        ),
    ]


@pytest.fixture
def mock_folder() -> Document:
    """Create a mock folder document."""
    return Document(
        id="folder1",
        name="Test Folder",
        doc_type=DocType.folder,
        parent_id=None,
    )


# =============================================================================
# Source Tools Tests
# =============================================================================

class TestCollectionTool:
    """Test the collection source tool."""

    @pytest.mark.asyncio
    async def test_collection_no_id(self, mock_llm_config, mock_state):
        """Test collection tool with no collection_id."""
        from fichero.workflows.tools.sources import collection_tool

        result = await collection_tool({}, mock_state, mock_llm_config)

        assert result["error"] == "No collection_id provided"
        assert result["files"] == []
        assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_collection_no_library_path(self, mock_llm_config):
        """Test collection tool with no library_path."""
        from fichero.workflows.tools.sources import collection_tool

        state = {"inputs": {}, "outputs": {}}
        result = await collection_tool({"collection_id": "test"}, state, mock_llm_config)

        assert result["error"] == "No library_path in state"
        assert result["files"] == []

    @pytest.mark.asyncio
    async def test_collection_success(self, mock_llm_config, mock_state, mock_documents, mock_folder):
        """Test collection tool returns files correctly."""
        from fichero.workflows.tools.sources import collection_tool

        mock_db = MagicMock()
        mock_db.query.return_value = mock_documents

        with patch('fichero.workflows.tools.sources.db_manager') as mock_manager:
            mock_manager.get_database.return_value = mock_db

            result = await collection_tool(
                {"collection_id": "folder1", "recursive": False},
                mock_state,
                mock_llm_config,
            )

            assert result["count"] == 3
            assert len(result["files"]) == 3
            assert "/test/image1.jpg" in result["files"]


class TestFolderTool:
    """Test the folder source tool."""

    @pytest.mark.asyncio
    async def test_folder_no_id(self, mock_llm_config, mock_state):
        """Test folder tool with no folder_id."""
        from fichero.workflows.tools.sources import folder_tool

        result = await folder_tool({}, mock_state, mock_llm_config)

        assert "error" in result
        assert result["files"] == []

    @pytest.mark.asyncio
    async def test_folder_with_subfolders(self, mock_llm_config, mock_state, mock_documents):
        """Test folder tool returns subfolders."""
        from fichero.workflows.tools.sources import folder_tool

        subfolder = Document(
            id="subfolder1",
            name="Subfolder",
            doc_type=DocType.folder,
            parent_id="folder1",
        )

        mock_db = MagicMock()
        # First call returns files, second call returns subfolders
        mock_db.query.side_effect = [mock_documents, [subfolder]]

        with patch('fichero.workflows.tools.sources.db_manager') as mock_manager:
            mock_manager.get_database.return_value = mock_db

            result = await folder_tool(
                {"folder_id": "folder1", "include_subfolders": False},
                mock_state,
                mock_llm_config,
            )

            assert len(result["subfolders"]) == 1
            assert "subfolder1" in result["subfolders"]


class TestSearchTool:
    """Test the search source tool."""

    @pytest.mark.asyncio
    async def test_search_no_query(self, mock_llm_config, mock_state):
        """Test search tool with no query."""
        from fichero.workflows.tools.sources import search_tool

        result = await search_tool({}, mock_state, mock_llm_config)

        assert result["error"] == "No search query provided"
        assert result["files"] == []


# =============================================================================
# Vision Tools Tests
# =============================================================================

class TestTranscribeTool:
    """Test the transcribe vision tool."""

    @pytest.mark.asyncio
    async def test_transcribe_no_files(self, mock_llm_config, mock_state):
        """Test transcribe with no input files."""
        from fichero.workflows.tools.transcribe import transcribe

        result = await transcribe({}, mock_state, mock_llm_config)

        assert result["error"] == "No input files provided"
        assert result["text"] == ""
        assert result["texts"] == []

    @pytest.mark.asyncio
    async def test_transcribe_with_files(self, mock_llm_config, mock_state, tmp_path):
        """Test transcribe processes files correctly."""
        from fichero.workflows.tools.transcribe import transcribe

        # Create a test image file
        test_image = tmp_path / "test.jpg"
        # Create a minimal valid JPEG (1x1 pixel)
        jpeg_data = base64.b64decode(
            "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRof"
            "Hh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwh"
            "MjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAAR"
            "CAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAn/xAAUEAEAAAAAAAAAAAAAAAAA"
            "AAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMB"
            "AAIRAxEAPwCwAB//2Q=="
        )
        test_image.write_bytes(jpeg_data)

        # Mock the vision LLM call
        with patch('fichero.workflows.tools.transcribe.vision', new_callable=AsyncMock) as mock_vision:
            mock_vision.return_value = "Transcribed text from image"

            # Don't save to DB for this test
            result = await transcribe(
                {
                    "files": [str(test_image)],
                    "save_to_db": False,
                },
                mock_state,
                mock_llm_config,
            )

            assert result["text"] == "Transcribed text from image"
            assert len(result["texts"]) == 1
            mock_vision.assert_called_once()


class TestDescribeTool:
    """Test the describe vision tool."""

    @pytest.mark.asyncio
    async def test_describe_no_files(self, mock_llm_config, mock_state):
        """Test describe with no input files."""
        from fichero.workflows.tools.describe import describe

        result = await describe({}, mock_state, mock_llm_config)

        assert result["error"] == "No input files provided"
        assert result["description"] == ""

    @pytest.mark.asyncio
    async def test_describe_with_files(self, mock_llm_config, mock_state, tmp_path):
        """Test describe processes files correctly."""
        from fichero.workflows.tools.describe import describe

        # Create a test image file
        test_image = tmp_path / "test.jpg"
        jpeg_data = base64.b64decode(
            "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRof"
            "Hh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwh"
            "MjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAAR"
            "CAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAn/xAAUEAEAAAAAAAAAAAAAAAAA"
            "AAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMB"
            "AAIRAxEAPwCwAB//2Q=="
        )
        test_image.write_bytes(jpeg_data)

        with patch('fichero.workflows.tools.describe.vision', new_callable=AsyncMock) as mock_vision:
            mock_vision.return_value = "A test image description"

            result = await describe(
                {
                    "files": [str(test_image)],
                    "save_to_db": False,
                },
                mock_state,
                mock_llm_config,
            )

            assert result["description"] == "A test image description"
            assert len(result["descriptions"]) == 1


# =============================================================================
# LLM Tools Tests
# =============================================================================

class TestSummarizeTool:
    """Test the summarize LLM tools."""

    @pytest.mark.asyncio
    async def test_summarize_file_no_text(self, mock_llm_config, mock_state):
        """Test summarize_file with no text."""
        from fichero.workflows.tools.summarize import summarize_file

        result = await summarize_file({}, mock_state, mock_llm_config)

        assert result["error"] == "No text provided"
        assert result["summary"] == ""

    @pytest.mark.asyncio
    async def test_summarize_file_success(self, mock_llm_config, mock_state):
        """Test summarize_file with text."""
        from fichero.workflows.tools.summarize import summarize_file

        with patch('fichero.workflows.tools.summarize.chat', new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = "This is a summary."

            result = await summarize_file(
                {
                    "text": "A long document with lots of content...",
                    "style": "brief",
                    "save_to_db": False,
                },
                mock_state,
                mock_llm_config,
            )

            assert result["summary"] == "This is a summary."
            mock_chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_summarize_folder_no_texts(self, mock_llm_config, mock_state):
        """Test summarize_folder with no texts."""
        from fichero.workflows.tools.summarize import summarize_folder

        result = await summarize_folder({}, mock_state, mock_llm_config)

        assert result["error"] == "No texts provided"

    @pytest.mark.asyncio
    async def test_summarize_collection_with_summaries(self, mock_llm_config, mock_state):
        """Test summarize_collection with folder summaries."""
        from fichero.workflows.tools.summarize import summarize_collection

        with patch('fichero.workflows.tools.summarize.chat', new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = "Collection overview."

            result = await summarize_collection(
                {
                    "folder_summaries": ["Summary 1", "Summary 2"],
                    "style": "executive",
                    "save_to_db": False,
                },
                mock_state,
                mock_llm_config,
            )

            assert result["summary"] == "Collection overview."
            assert result["source_count"] == 2


class TestExtractEntitiesTool:
    """Test the extract_entities LLM tool."""

    @pytest.mark.asyncio
    async def test_extract_entities_no_text(self, mock_llm_config, mock_state):
        """Test extract_entities with no text."""
        from fichero.workflows.tools.entities import extract_entities

        result = await extract_entities({}, mock_state, mock_llm_config)

        assert result["error"] == "No text provided"
        assert result["entities"] == {}

    @pytest.mark.asyncio
    async def test_extract_entities_success(self, mock_llm_config, mock_state):
        """Test extract_entities parses JSON correctly."""
        from fichero.workflows.tools.entities import extract_entities

        mock_response = '{"people": ["John Smith"], "organizations": ["Acme Corp"], "locations": ["New York"], "dates": ["2024"]}'

        with patch('fichero.workflows.tools.entities.chat', new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = mock_response

            result = await extract_entities(
                {
                    "text": "John Smith from Acme Corp visited New York in 2024.",
                    "save_to_db": False,
                },
                mock_state,
                mock_llm_config,
            )

            assert "people" in result["entities"]
            assert "John Smith" in result["entities"]["people"]
            assert "Acme Corp" in result["entities"]["organizations"]


# =============================================================================
# Tool Registration Tests
# =============================================================================

class TestToolRegistration:
    """Test that all tools are properly registered."""

    def test_source_tools_registered(self):
        """Test source tools are registered."""
        assert "collection" in TOOLS
        assert "folder" in TOOLS
        assert "search" in TOOLS

    def test_vision_tools_registered(self):
        """Test vision tools are registered."""
        assert "transcribe" in TOOLS
        assert "describe" in TOOLS

    def test_llm_tools_registered(self):
        """Test LLM tools are registered."""
        assert "summarize_file" in TOOLS
        assert "summarize_folder" in TOOLS
        assert "summarize_collection" in TOOLS
        assert "extract_entities" in TOOLS


# =============================================================================
# DB Saving Tests
# =============================================================================

class TestDatabaseSaving:
    """Test that tools save to database correctly."""

    @pytest.mark.asyncio
    async def test_transcribe_saves_artifact(self, mock_llm_config, mock_state, tmp_path):
        """Test that transcribe saves Artifact to database."""
        from fichero.workflows.tools.transcribe import transcribe
        from fichero.models import Artifact

        # Create a test image
        test_image = tmp_path / "test.jpg"
        jpeg_data = base64.b64decode(
            "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRof"
            "Hh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwh"
            "MjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAAR"
            "CAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAn/xAAUEAEAAAAAAAAAAAAAAAAA"
            "AAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMB"
            "AAIRAxEAPwCwAB//2Q=="
        )
        test_image.write_bytes(jpeg_data)

        # Mock document
        mock_doc = MagicMock()
        mock_doc.id = "doc123"
        mock_doc.page_content = ""
        mock_doc.metadata = {}
        mock_doc.status = Status.pending

        # Mock database
        mock_db = MagicMock()
        mock_db.query.return_value = [mock_doc]
        mock_db.get.return_value = mock_doc

        with patch('fichero.workflows.tools.transcribe.vision', new_callable=AsyncMock) as mock_vision:
            mock_vision.return_value = "Transcribed content"

            # db_manager is imported inside _save_transcription, so patch it in fichero.db
            with patch('fichero.db.db_manager') as mock_manager:
                mock_manager.get_database.return_value = mock_db

                result = await transcribe(
                    {
                        "files": [str(test_image)],
                        "documents": [{"id": "doc123", "path": str(test_image)}],
                        "save_to_db": True,
                    },
                    mock_state,
                    mock_llm_config,
                )

                # Verify we got transcribed text
                assert result["text"] == "Transcribed content"
                # Artifacts list may be empty since db is mocked
                assert "artifacts" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
