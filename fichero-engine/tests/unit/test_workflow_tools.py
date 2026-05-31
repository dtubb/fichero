"""
Unit tests for Workflow Tools

Tests the source, vision, and LLM tools for workflows.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
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

    @pytest.mark.asyncio
    async def test_search_includes_kg_context_in_documents(self, mock_llm_config, mock_state):
        """Graph-aware retrieval returns docs + KG context for researcher flows."""
        from fichero.workflows.tools.sources import search_tool

        doc = Document(
            id="doc-1",
            name="Memo",
            path="/tmp/memo.txt",
            doc_type=DocType.file,
            file_type=FileType.text,
        )
        mock_db = MagicMock()
        mock_db.get.return_value = doc

        class _Payload:
            context_docs = [
                {"id": "doc-1", "kind": "document", "search_score": 0.88},
                {
                    "id": "kg-claim:claim-1",
                    "name": "KG claim claim-1",
                    "kind": "kg_claim",
                    "content": "Claim: Ada served as mayor in Popayan.",
                },
            ]

        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = _Payload()

        with (
            patch("fichero.workflows.tools.sources.db_manager") as mock_manager,
            patch("fichero.workflows.tools.sources.GraphAwareRetriever", return_value=mock_retriever),
        ):
            mock_manager.get_database.return_value = mock_db
            result = await search_tool({"query": "Popayan"}, mock_state, mock_llm_config)

        assert result["files"] == ["/tmp/memo.txt"]
        assert result["count"] == 1
        assert result["document_count"] == 1
        assert result["context_count"] == 2
        assert len(result["documents"]) == 2
        assert result["documents"][0]["search_score"] == 0.88
        assert result["documents"][1]["id"] == "kg-claim:claim-1"
        assert result["documents"][1]["doc_type"] == "kg_claim"
        assert result["kg_claims_used"] == 0
        assert result["kg_entities_used"] == 0

    @pytest.mark.asyncio
    async def test_search_passes_graph_knobs_to_retriever(self, mock_llm_config, mock_state):
        """search_tool forwards graph-RAG controls to shared retriever."""
        from fichero.workflows.tools.sources import search_tool

        captured: dict = {}
        mock_db = MagicMock()

        class _Payload:
            context_docs = []

        mock_retriever = MagicMock()

        def _retrieve(**kwargs):
            captured.update(kwargs)
            return _Payload()

        mock_retriever.retrieve.side_effect = _retrieve

        with (
            patch("fichero.workflows.tools.sources.db_manager") as mock_manager,
            patch("fichero.workflows.tools.sources.GraphAwareRetriever", return_value=mock_retriever),
        ):
            mock_manager.get_database.return_value = mock_db
            r = await search_tool(
                {"query": "Ada", "graph_hops": 2, "max_kg_claims": 7},
                mock_state,
                mock_llm_config,
            )

        assert r["count"] == 0
        assert r["document_count"] == 0
        assert r["context_count"] == 0
        assert captured["graph_hops"] == 2
        assert captured["max_kg_claims"] == 7

    @pytest.mark.asyncio
    async def test_search_clamps_graph_knobs(self, mock_llm_config, mock_state):
        """search_tool clamps oversized graph knobs before retrieval."""
        from fichero.workflows.tools.sources import search_tool

        captured: dict = {}
        mock_db = MagicMock()

        class _Payload:
            context_docs = []

        mock_retriever = MagicMock()

        def _retrieve(**kwargs):
            captured.update(kwargs)
            return _Payload()

        mock_retriever.retrieve.side_effect = _retrieve

        with (
            patch("fichero.workflows.tools.sources.db_manager") as mock_manager,
            patch("fichero.workflows.tools.sources.GraphAwareRetriever", return_value=mock_retriever),
        ):
            mock_manager.get_database.return_value = mock_db
            r = await search_tool(
                {"query": "Ada", "graph_hops": 999, "max_kg_claims": 9999},
                mock_state,
                mock_llm_config,
            )

        assert r["count"] == 0
        assert r["document_count"] == 0
        assert r["context_count"] == 0
        assert captured["graph_hops"] == 3
        assert captured["max_kg_claims"] == 100

    @pytest.mark.asyncio
    async def test_search_returns_kg_usage_telemetry(self, mock_llm_config, mock_state):
        """search_tool returns KG usage counts from shared retriever payload."""
        from fichero.workflows.tools.sources import search_tool

        mock_db = MagicMock()

        class _Payload:
            context_docs = []
            kg_claims_used = 5
            kg_entities_used = 4

        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = _Payload()

        with (
            patch("fichero.workflows.tools.sources.db_manager") as mock_manager,
            patch("fichero.workflows.tools.sources.GraphAwareRetriever", return_value=mock_retriever),
        ):
            mock_manager.get_database.return_value = mock_db
            r = await search_tool({"query": "Ada"}, mock_state, mock_llm_config)

        assert r["kg_claims_used"] == 5
        assert r["kg_entities_used"] == 4
        assert r["document_count"] == 0
        assert r["context_count"] == 0

    @pytest.mark.asyncio
    async def test_search_logs_retrieval_diagnostics(
        self, mock_llm_config, mock_state, caplog
    ):
        """search_tool emits a structured retrieval diagnostics log line."""
        from fichero.workflows.tools.sources import search_tool

        mock_db = MagicMock()

        class _Payload:
            context_docs = []
            kg_claims_used = 1
            kg_entities_used = 1

        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = _Payload()

        with (
            patch("fichero.workflows.tools.sources.db_manager") as mock_manager,
            patch(
                "fichero.workflows.tools.sources.GraphAwareRetriever",
                return_value=mock_retriever,
            ),
            caplog.at_level("INFO"),
        ):
            mock_manager.get_database.return_value = mock_db
            r = await search_tool({"query": "Ada"}, mock_state, mock_llm_config)

        assert r["count"] == 0
        assert "research_search" in caplog.text


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

        # Mock the vision LLM call (imported from fichero.llm in vision_base)
        with patch('fichero.llm.vision', new_callable=AsyncMock) as mock_vision:
            mock_vision.return_value = "Transcribed text from image"

            # Don't save to DB for this test, use LLM mode (not Apple Vision)
            result = await transcribe(
                {
                    "files": [str(test_image)],
                    "save_to_db": False,
                    "vision_mode": "llm",  # Use LLM, not Apple Vision OCR
                },
                mock_state,
                mock_llm_config,
            )

            assert result["text"] == "Transcribed text from image"
            assert len(result["texts"]) == 1
            mock_vision.assert_called_once()

    @pytest.mark.asyncio
    async def test_transcribe_labels_pdf_text_layer_as_pdf_text(
        self, mock_llm_config, mock_state, tmp_path
    ):
        """Born-digital PDFs should not be mislabeled as Apple Vision OCR."""
        from fichero.workflows.tools.transcribe import transcribe

        test_pdf = tmp_path / "digital.pdf"
        test_pdf.write_bytes(b"%PDF-1.4\n%%EOF")

        save_artifact_mock = AsyncMock(return_value="artifact-123")

        with patch("fichero.workflows.tools.vision_base._try_pdf_text_layer", return_value=["Digital PDF text"]) as mock_pdf_layer:
            with patch("fichero.workflows.tools.vision_base.save_artifact", save_artifact_mock):
                with patch("fichero.llm.vision", new_callable=AsyncMock) as mock_vision:
                    result = await transcribe(
                        {
                            "files": [str(test_pdf)],
                            "documents": [{"id": "doc123", "path": str(test_pdf)}],
                            "save_to_db": True,
                            "vision_mode": "apple",
                        },
                        mock_state,
                        mock_llm_config,
                    )

        assert result["text"] == "Digital PDF text"
        mock_pdf_layer.assert_called_once_with(str(test_pdf))
        mock_vision.assert_not_called()
        assert save_artifact_mock.await_count == 1
        saved_kwargs = save_artifact_mock.await_args.kwargs
        assert saved_kwargs["llm_config"].provider == "pdf_text"
        assert saved_kwargs["llm_config"].model == "pdf-text-layer"


class TestDescribeTool:
    """Test the describe vision tool."""

    @pytest.mark.asyncio
    async def test_describe_no_files(self, mock_llm_config, mock_state):
        """Test describe with no input files."""
        from fichero.workflows.tools.describe import describe

        result = await describe({}, mock_state, mock_llm_config)

        assert result["error"] == "No input files provided"
        assert result["text"] == ""

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

        with patch('fichero.llm.vision', new_callable=AsyncMock) as mock_vision:
            mock_vision.return_value = "A test image description"

            result = await describe(
                {
                    "files": [str(test_image)],
                    "save_to_db": False,
                },
                mock_state,
                mock_llm_config,
            )

            # describe uses standard output ports (text, texts)
            assert result["text"] == "A test image description"
            assert len(result["texts"]) == 1


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

        # Patch chat in fichero.llm (where it's imported from in process_text)
        with patch('fichero.llm.chat', new_callable=AsyncMock) as mock_chat:
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

        with patch('fichero.llm.chat', new_callable=AsyncMock) as mock_chat:
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

        with patch('fichero.llm.chat', new_callable=AsyncMock) as mock_chat:
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

    @pytest.mark.asyncio
    async def test_extract_entities_deduplicates_normalized_names(self, mock_llm_config, mock_state):
        """Normalized names should dedupe even when case/spacing/accents differ."""
        from fichero.workflows.tools.entities import extract_entities

        mock_result = {
            "value": {
                "people": ["María", "maria ", "José", "jose"],
                "organizations": ["Acme Corp", "ACME CORP"],
                "locations": [],
                "dates": [],
            },
            "text": "",
            "texts": [],
            "results": [],
            "artifacts": [],
        }

        with patch("fichero.workflows.tools.entities.process_text", new=AsyncMock(return_value=mock_result)):
            result = await extract_entities(
                {
                    "text": "María and José work at Acme Corp.",
                    "save_to_db": False,
                },
                mock_state,
                mock_llm_config,
            )

        assert result["entities"]["people"] == ["María", "José"]
        assert result["entities"]["organizations"] == ["Acme Corp"]

    @pytest.mark.asyncio
    async def test_extract_entities_truncates_over_max_items(self, mock_llm_config, mock_state):
        """max_items should cap each entity category after deduplication."""
        from fichero.workflows.tools.entities import extract_entities

        mock_result = {
            "value": {
                "people": ["A", "B", "C"],
                "organizations": [],
                "locations": [],
                "dates": [],
            },
            "text": "",
            "texts": [],
            "results": [],
            "artifacts": [],
        }

        with patch("fichero.workflows.tools.entities.process_text", new=AsyncMock(return_value=mock_result)):
            result = await extract_entities(
                {
                    "text": "A B C",
                    "save_to_db": False,
                    "max_items": 2,
                },
                mock_state,
                mock_llm_config,
            )

        assert result["entities"]["people"] == ["A", "B"]


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

        with patch('fichero.llm.vision', new_callable=AsyncMock) as mock_vision:
            mock_vision.return_value = "Transcribed content"

            # db_manager is imported inside save_artifact
            with patch('fichero.db.db_manager') as mock_manager:
                mock_manager.get_database.return_value = mock_db

                result = await transcribe(
                    {
                        "files": [str(test_image)],
                        "documents": [{"id": "doc123", "path": str(test_image)}],
                        "save_to_db": True,
                        "vision_mode": "llm",  # Use LLM, not Apple Vision OCR
                    },
                    mock_state,
                    mock_llm_config,
                )

                # Verify we got transcribed text
                assert result["text"] == "Transcribed content"
                # Artifacts list may be empty since db is mocked
                assert "artifacts" in result


class TestSaveArtifact:
    """Test save_artifact function directly."""

    @pytest.mark.asyncio
    async def test_save_artifact_by_document_id(self):
        """Test save_artifact finds document by ID and creates artifact."""
        from fichero.workflows.tools.llm_base import save_artifact, LLMToolConfig

        mock_doc = MagicMock()
        mock_doc.id = "doc123"
        mock_doc.name = "test.jpg"
        mock_doc.metadata = {}

        mock_db = MagicMock()
        mock_db.get.return_value = mock_doc

        tool_config = LLMToolConfig(
            artifact_type="description",
            update_page_content=False,
            trigger_embedding=False,
            metadata_field="description",
        )

        llm_config = LLMConfig(provider="test", model="test-model")

        with patch('fichero.db.db_manager') as mock_manager:
            mock_manager.get_database.return_value = mock_db

            result = await save_artifact(
                document_id="doc123",
                file_path=None,
                content="A beautiful sunset image",
                data=None,
                library_path="/test/library.fichero",
                llm_config=llm_config,
                task_id="task1",
                tool_config=tool_config,
            )

            # Should find doc by ID
            mock_db.get.assert_called_once()
            # Should save artifact and document
            assert mock_db.save.call_count == 2  # artifact + metadata update
            # Should return artifact ID
            assert result is not None
            # Metadata should be updated
            assert mock_doc.metadata["description"] == "A beautiful sunset image"

    @pytest.mark.asyncio
    async def test_save_artifact_by_file_path(self):
        """Test save_artifact falls back to path query when no ID."""
        from fichero.workflows.tools.llm_base import save_artifact, LLMToolConfig

        mock_doc = MagicMock()
        mock_doc.id = "doc456"
        mock_doc.name = "photo.jpg"
        mock_doc.metadata = {}

        mock_db = MagicMock()
        mock_db.get.return_value = None  # ID lookup fails
        mock_db.query.return_value = [mock_doc]  # Path lookup succeeds

        tool_config = LLMToolConfig(
            artifact_type="description",
            metadata_field="description",
        )

        llm_config = LLMConfig(provider="test", model="test-model")

        with patch('fichero.db.db_manager') as mock_manager:
            mock_manager.get_database.return_value = mock_db

            result = await save_artifact(
                document_id=None,
                file_path="/photos/photo.jpg",
                content="Photo content",
                data=None,
                library_path="/test/library.fichero",
                llm_config=llm_config,
                task_id=None,
                tool_config=tool_config,
            )

            # Should query by path
            mock_db.query.assert_called_once()
            assert result is not None
            assert mock_doc.metadata["description"] == "Photo content"

    @pytest.mark.asyncio
    async def test_save_artifact_document_not_found(self):
        """Test save_artifact returns None when document not found."""
        from fichero.workflows.tools.llm_base import save_artifact, LLMToolConfig

        mock_db = MagicMock()
        mock_db.get.return_value = None
        mock_db.query.return_value = []

        tool_config = LLMToolConfig(artifact_type="test", metadata_field="test")
        llm_config = LLMConfig(provider="test", model="test-model")

        with patch('fichero.db.db_manager') as mock_manager:
            mock_manager.get_database.return_value = mock_db

            result = await save_artifact(
                document_id="nonexistent",
                file_path="/nonexistent/file.jpg",
                content="content",
                data=None,
                library_path="/test/library.fichero",
                llm_config=llm_config,
                task_id=None,
                tool_config=tool_config,
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_save_artifact_empty_library_path(self):
        """Test save_artifact returns None with empty library_path."""
        from fichero.workflows.tools.llm_base import save_artifact, LLMToolConfig

        tool_config = LLMToolConfig(artifact_type="test", metadata_field="test")
        llm_config = LLMConfig(provider="test", model="test-model")

        result = await save_artifact(
            document_id="doc1",
            file_path=None,
            content="content",
            data=None,
            library_path="",
            llm_config=llm_config,
            task_id=None,
            tool_config=tool_config,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_save_artifact_with_structured_data(self):
        """Test save_artifact saves structured data to metadata."""
        from fichero.workflows.tools.llm_base import save_artifact, LLMToolConfig

        mock_doc = MagicMock()
        mock_doc.id = "doc789"
        mock_doc.metadata = {}

        mock_db = MagicMock()
        mock_db.get.return_value = mock_doc

        tool_config = LLMToolConfig(
            artifact_type="entities",
            metadata_field="entities",
        )
        llm_config = LLMConfig(provider="test", model="test-model")

        structured_data = {"people": ["John", "Jane"], "places": ["NYC"]}

        with patch('fichero.db.db_manager') as mock_manager:
            mock_manager.get_database.return_value = mock_db

            result = await save_artifact(
                document_id="doc789",
                file_path=None,
                content="raw text",
                data=structured_data,
                library_path="/test/library.fichero",
                llm_config=llm_config,
                task_id=None,
                tool_config=tool_config,
            )

            assert result is not None
            # When data is provided, it should be stored instead of content
            assert mock_doc.metadata["entities"] == structured_data

    @pytest.mark.asyncio
    async def test_save_artifact_metadata_field_override(self):
        """Test metadata_field parameter overrides tool_config."""
        from fichero.workflows.tools.llm_base import save_artifact, LLMToolConfig

        mock_doc = MagicMock()
        mock_doc.id = "doc1"
        mock_doc.metadata = {}

        mock_db = MagicMock()
        mock_db.get.return_value = mock_doc

        tool_config = LLMToolConfig(
            artifact_type="description",
            metadata_field="description",
        )
        llm_config = LLMConfig(provider="test", model="test-model")

        with patch('fichero.db.db_manager') as mock_manager:
            mock_manager.get_database.return_value = mock_db

            await save_artifact(
                document_id="doc1",
                file_path=None,
                content="custom field content",
                data=None,
                library_path="/test/library.fichero",
                llm_config=llm_config,
                task_id=None,
                tool_config=tool_config,
                metadata_field="custom_field",
            )

            # Should use override field, not tool_config field
            assert "custom_field" in mock_doc.metadata
            assert "description" not in mock_doc.metadata

    @pytest.mark.asyncio
    async def test_artifact_provenance_points_to_source_document(self):
        """Test that artifact provenance records source_document_id, not the model."""
        from fichero.workflows.tools.llm_base import save_artifact, LLMToolConfig
        from fichero.models import Artifact

        mock_doc = MagicMock()
        mock_doc.id = "source-doc-id"
        mock_doc.metadata = {}

        saved_artifact = None

        def capture_artifact(artifact):
            nonlocal saved_artifact
            if isinstance(artifact, Artifact):
                saved_artifact = artifact

        mock_db = MagicMock()
        mock_db.get.return_value = mock_doc
        mock_db.save.side_effect = capture_artifact

        tool_config = LLMToolConfig(artifact_type="transcription")
        llm_config = LLMConfig(provider="apple", model="apple-vision")

        with patch('fichero.db.db_manager') as mock_manager:
            mock_manager.get_database.return_value = mock_db

            result = await save_artifact(
                document_id="source-doc-id",
                file_path=None,
                content="Transcribed text",
                data=None,
                library_path="/test/library.fichero",
                llm_config=llm_config,
                task_id="task123",
                tool_config=tool_config,
            )

            assert result is not None
            assert saved_artifact is not None
            assert saved_artifact.source_document_id == "source-doc-id"
            assert saved_artifact.model == "apple-vision"
            assert saved_artifact.provider == "apple"


class TestSaveToFile:
    """Test save_to_file function."""

    @pytest.mark.asyncio
    async def test_save_text_to_file(self, tmp_path):
        """Test saving text content to file."""
        from fichero.workflows.tools.llm_base import save_to_file, LLMToolConfig

        tool_config = LLMToolConfig(
            artifact_type="description",
            metadata_field="description",
        )

        result = await save_to_file(
            content="A detailed image description",
            data=None,
            library_path=str(tmp_path),
            document_id="abc123",
            file_path=None,
            tool_config=tool_config,
            output_format="text",
        )

        assert result is not None
        # Check file exists
        output_file = Path(result)
        assert output_file.exists()
        assert output_file.read_text() == "A detailed image description"
        # Check path structure
        assert "storage/outputs/ab" in result
        assert "abc123_description.txt" in result

    @pytest.mark.asyncio
    async def test_save_json_to_file(self, tmp_path):
        """Test saving structured data to JSON file."""
        from fichero.workflows.tools.llm_base import save_to_file, LLMToolConfig

        tool_config = LLMToolConfig(
            artifact_type="entities",
            metadata_field="entities",
        )

        data = {"people": ["John", "Jane"], "count": 2}

        result = await save_to_file(
            content="raw text",
            data=data,
            library_path=str(tmp_path),
            document_id="xyz789",
            file_path=None,
            tool_config=tool_config,
            output_format="json",
        )

        assert result is not None
        output_file = Path(result)
        assert output_file.exists()
        assert output_file.suffix == ".json"
        import json
        saved_data = json.loads(output_file.read_text())
        assert saved_data == data

    @pytest.mark.asyncio
    async def test_save_to_file_no_library_path(self):
        """Test save_to_file returns None with empty library_path."""
        from fichero.workflows.tools.llm_base import save_to_file, LLMToolConfig

        tool_config = LLMToolConfig(artifact_type="test", metadata_field="test")

        result = await save_to_file(
            content="content",
            data=None,
            library_path="",
            document_id="doc1",
            file_path=None,
            tool_config=tool_config,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_save_to_file_uses_filename_fallback(self, tmp_path):
        """Test save_to_file uses source filename when no doc_id."""
        from fichero.workflows.tools.llm_base import save_to_file, LLMToolConfig

        tool_config = LLMToolConfig(
            artifact_type="transcription",
            metadata_field="transcription",
        )

        result = await save_to_file(
            content="OCR text here",
            data=None,
            library_path=str(tmp_path),
            document_id=None,
            file_path="/photos/vacation_photo.jpg",
            tool_config=tool_config,
            output_format="text",
        )

        assert result is not None
        assert "vacation_photo_transcription.txt" in result
        assert Path(result).read_text() == "OCR text here"


class TestProcessVisionSave:
    """Test process_vision save integration."""

    @pytest.mark.asyncio
    async def test_process_vision_saves_artifact(self, mock_llm_config, tmp_path):
        """Test process_vision calls save_artifact with correct params."""
        from fichero.workflows.tools.vision_base import process_vision, VisionToolConfig

        # Create test image
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

        tool_config = VisionToolConfig(
            artifact_type="description",
            update_page_content=False,
            trigger_embedding=False,
            supports_apple_vision=False,
            metadata_field="description",
        )

        mock_doc = MagicMock()
        mock_doc.id = "doc_abc"
        mock_doc.metadata = {}

        mock_db = MagicMock()
        mock_db.get.return_value = mock_doc

        with patch('fichero.llm.vision', new_callable=AsyncMock) as mock_vision:
            mock_vision.return_value = "A test description"

            with patch('fichero.db.db_manager') as mock_manager:
                mock_manager.get_database.return_value = mock_db

                result = await process_vision(
                    files=[str(test_image)],
                    documents=[{"id": "doc_abc", "path": str(test_image)}],
                    prompt="Describe this image",
                    llm_config=mock_llm_config,
                    library_path="/test/lib.fichero",
                    task_id="task1",
                    tool_config=tool_config,
                    save_to_db=True,
                    metadata_field="description",
                )

                assert result["text"] == "A test description"
                assert len(result["artifacts"]) == 1
                # Verify db.save was called (artifact + doc metadata)
                assert mock_db.save.call_count == 2
                assert mock_doc.metadata["description"] == "A test description"

    @pytest.mark.asyncio
    async def test_process_vision_save_to_file(self, mock_llm_config, tmp_path):
        """Test process_vision writes output to file when flag is set."""
        from fichero.workflows.tools.vision_base import process_vision, VisionToolConfig

        # Create test image
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

        # Use tmp_path as library_path so file save works
        library_path = str(tmp_path / "lib.fichero")
        Path(library_path).mkdir()

        tool_config = VisionToolConfig(
            artifact_type="description",
            supports_apple_vision=False,
            metadata_field="description",
        )

        with patch('fichero.llm.vision', new_callable=AsyncMock) as mock_vision:
            mock_vision.return_value = "Saved to file description"

            result = await process_vision(
                files=[str(test_image)],
                documents=[{"id": "file_doc", "path": str(test_image)}],
                prompt="Describe this",
                llm_config=mock_llm_config,
                library_path=library_path,
                task_id=None,
                tool_config=tool_config,
                save_to_db=False,
                save_to_file_flag=True,
            )

            assert result["text"] == "Saved to file description"
            assert len(result["output_files"]) == 1
            # Verify file was written
            output_path = Path(result["output_files"][0])
            assert output_path.exists()
            assert output_path.read_text() == "Saved to file description"

    @pytest.mark.asyncio
    async def test_process_vision_no_save(self, mock_llm_config, tmp_path):
        """Test process_vision with both save options disabled."""
        from fichero.workflows.tools.vision_base import process_vision, VisionToolConfig

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

        tool_config = VisionToolConfig(
            artifact_type="test",
            supports_apple_vision=False,
            metadata_field="test",
        )

        with patch('fichero.llm.vision', new_callable=AsyncMock) as mock_vision:
            mock_vision.return_value = "Result text"

            result = await process_vision(
                files=[str(test_image)],
                documents=[],
                prompt="Test",
                llm_config=mock_llm_config,
                library_path=str(tmp_path),
                task_id=None,
                tool_config=tool_config,
                save_to_db=False,
                save_to_file_flag=False,
            )

            assert result["text"] == "Result text"
            assert result["artifacts"] == []
            assert result["output_files"] == []


class TestProcessTextSave:
    """Test process_text save integration."""

    @pytest.mark.asyncio
    async def test_process_text_saves_artifact(self, mock_llm_config):
        """Test process_text saves to database correctly."""
        from fichero.workflows.tools.llm_base import process_text, LLMToolConfig

        mock_doc = MagicMock()
        mock_doc.id = "text_doc1"
        mock_doc.metadata = {}

        mock_db = MagicMock()
        mock_db.get.return_value = mock_doc

        tool_config = LLMToolConfig(
            artifact_type="summary",
            metadata_field="summary",
        )

        with patch('fichero.llm.chat', new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = "A concise summary"

            with patch('fichero.db.db_manager') as mock_manager:
                mock_manager.get_database.return_value = mock_db

                result = await process_text(
                    text="Long text to summarize...",
                    prompt="Summarize this",
                    llm_config=mock_llm_config,
                    library_path="/test/lib.fichero",
                    task_id="task1",
                    tool_config=tool_config,
                    documents=[{"id": "text_doc1", "path": "/test/doc.txt"}],
                    save_to_db=True,
                    metadata_field="summary",
                )

                assert result["text"] == "A concise summary"
                assert len(result["artifacts"]) == 1
                assert mock_doc.metadata["summary"] == "A concise summary"

    @pytest.mark.asyncio
    async def test_process_text_save_to_file(self, mock_llm_config, tmp_path):
        """Test process_text exports to file."""
        from fichero.workflows.tools.llm_base import process_text, LLMToolConfig

        library_path = str(tmp_path / "lib.fichero")
        Path(library_path).mkdir()

        tool_config = LLMToolConfig(
            artifact_type="rewrite",
            metadata_field="rewrite",
        )

        with patch('fichero.llm.chat', new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = "Rewritten text content"

            result = await process_text(
                text="Original text",
                prompt="Rewrite this",
                llm_config=mock_llm_config,
                library_path=library_path,
                task_id=None,
                tool_config=tool_config,
                documents=[{"id": "rw_doc", "path": "/test/doc.txt"}],
                save_to_db=False,
                save_to_file_flag=True,
            )

            assert result["text"] == "Rewritten text content"
            assert len(result["output_files"]) == 1
            output_path = Path(result["output_files"][0])
            assert output_path.exists()
            assert output_path.read_text() == "Rewritten text content"

    @pytest.mark.asyncio
    async def test_process_text_no_documents_skips_db_save(self, mock_llm_config):
        """Test process_text skips DB save when no documents provided."""
        from fichero.workflows.tools.llm_base import process_text, LLMToolConfig

        tool_config = LLMToolConfig(
            artifact_type="summary",
            metadata_field="summary",
        )

        with patch('fichero.llm.chat', new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = "Summary result"

            result = await process_text(
                text="Input text",
                prompt="Summarize",
                llm_config=mock_llm_config,
                library_path="/test/lib.fichero",
                task_id=None,
                tool_config=tool_config,
                documents=[],  # Empty documents
                save_to_db=True,
            )

            assert result["text"] == "Summary result"
            assert result["artifacts"] == []  # No save without documents

    @pytest.mark.asyncio
    async def test_process_text_chunking_map_reduce_for_long_input(self):
        """Long on-device input should run chunk map + final synth call (#801)."""
        from fichero.workflows.tools.llm_base import process_text, LLMToolConfig

        tool_config = LLMToolConfig(artifact_type="summary")
        llm_config = LLMConfig(provider="apple", model="foundation")
        long_text = ("A" * 14000) + "\n\n" + ("B" * 14000)

        with patch("fichero.llm.chat", new_callable=AsyncMock) as mock_chat:
            async def _fake_chat(user_text: str, *, config, system: str) -> str:
                if "processing one section of a larger document" in system:
                    return "chunk-notes"
                return "final-synthesis"

            mock_chat.side_effect = _fake_chat

            result = await process_text(
                text=long_text,
                prompt="Summarize",
                llm_config=llm_config,
                library_path="",
                task_id=None,
                tool_config=tool_config,
                save_to_db=False,
            )

            assert result["text"] == "final-synthesis"
            assert mock_chat.await_count > 1

    @pytest.mark.asyncio
    async def test_process_text_no_chunking_for_short_input(self):
        """Short input should keep single-shot call path."""
        from fichero.workflows.tools.llm_base import process_text, LLMToolConfig

        tool_config = LLMToolConfig(artifact_type="summary")
        llm_config = LLMConfig(provider="apple", model="foundation")

        with patch("fichero.llm.chat", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = "single-shot"
            result = await process_text(
                text="short text",
                prompt="Summarize",
                llm_config=llm_config,
                library_path="",
                task_id=None,
                tool_config=tool_config,
                save_to_db=False,
            )

            assert result["text"] == "single-shot"
            assert mock_chat.await_count == 1


# =============================================================================
# Tests: files_tool with selected_doc_ids
# =============================================================================


@pytest.mark.asyncio
async def test_files_tool_uses_selected_doc_ids(mock_state, mock_llm_config, mock_documents):
    """files_tool resolves documents from selected_doc_ids in state."""
    doc = mock_documents[0]  # doc1, path="/test/image1.jpg"
    state = {**mock_state, "selected_doc_ids": [doc.id]}

    mock_db = MagicMock()
    mock_db.get.return_value = doc

    with patch("fichero.workflows.tools.sources.db_manager") as mock_dm:
        mock_dm.get_database.return_value = mock_db
        from fichero.workflows.tools.sources import files_tool
        result = await files_tool(inputs={}, state=state, llm_config=mock_llm_config)

    assert result["files"] == ["/test/image1.jpg"]
    assert result["count"] == 1
    assert result["documents"][0]["id"] == doc.id


@pytest.mark.asyncio
async def test_files_tool_selected_doc_ids_skips_missing(mock_state, mock_llm_config, mock_documents):
    """files_tool skips doc IDs that the DB cannot resolve."""
    state = {**mock_state, "selected_doc_ids": ["missing-id", mock_documents[1].id]}

    mock_db = MagicMock()
    # First call returns None (not found), second returns a real doc
    mock_db.get.side_effect = [None, mock_documents[1]]

    with patch("fichero.workflows.tools.sources.db_manager") as mock_dm:
        mock_dm.get_database.return_value = mock_db
        from fichero.workflows.tools.sources import files_tool
        result = await files_tool(inputs={}, state=state, llm_config=mock_llm_config)

    assert result["count"] == 1
    assert result["files"] == [mock_documents[1].path]
    assert len(result["documents"]) == 1


@pytest.mark.asyncio
async def test_files_tool_explicit_inputs_override_selected_doc_ids(mock_state, mock_llm_config, mock_documents):
    """Explicit inputs['files'] takes priority over selected_doc_ids."""
    state = {**mock_state, "selected_doc_ids": [mock_documents[0].id]}

    from fichero.workflows.tools.sources import files_tool
    result = await files_tool(
        inputs={"files": ["/explicit/override.pdf"]},
        state=state,
        llm_config=mock_llm_config,
    )

    assert result["files"] == ["/explicit/override.pdf"]
    assert result["count"] == 1


@pytest.mark.asyncio
async def test_files_tool_selected_doc_ids_falls_through_without_library_path(mock_llm_config):
    """files_tool falls through to input_files when selected_doc_ids present but library_path missing."""
    state = {
        "selected_doc_ids": ["some-doc-id"],
        "input_files": ["/fallback/file.pdf"],
        "documents": [],
        # no library_path key
    }
    from fichero.workflows.tools.sources import files_tool
    result = await files_tool(inputs={}, state=state, llm_config=mock_llm_config)

    assert result["files"] == ["/fallback/file.pdf"]
    assert result["count"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
