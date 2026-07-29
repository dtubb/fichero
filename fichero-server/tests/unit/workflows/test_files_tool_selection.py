"""
Regression tests for files_tool selection behaviour.

These tests guard against the LangGraph channel-drop bug where
selected_doc_ids was silently lost because it wasn't declared in the
State TypedDict (introduced in build_initial_state → app.ainvoke path).

Two test layers:
  1. State channel survival — proves selected_doc_ids reaches node state.
  2. files_tool end-to-end — proves the tool returns the right files.
"""

import pytest
from unittest.mock import MagicMock, patch

from langgraph.graph import StateGraph, START, END

from fichero_server.models import Document, DocType, FileType, Status
from fichero_server.workflows.builder import build_graph
from fichero_server.workflows.runtime import build_initial_state
from fichero_server.workflows.types import State, WorkflowDef, NodeDef


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_doc(doc_id: str, path: str) -> Document:
    return Document(
        id=doc_id,
        name=path.split("/")[-1],
        doc_type=DocType.file,
        path=path,
        status=Status.completed,
    )


def _files_only_workflow() -> tuple[WorkflowDef, str]:
    """A minimal workflow with just a Files source node."""
    files_node_id = "FILES-NODE-001"
    workflow = WorkflowDef(
        name="Test",
        nodes=[NodeDef(id=files_node_id, tool="files", config={})],
        edges=[],
    )
    return workflow, files_node_id


# ---------------------------------------------------------------------------
# Layer 1: State channel survival
# ---------------------------------------------------------------------------

class TestSelectedDocIdsSurvivesStateInit:
    """
    Regression guard: selected_doc_ids must be preserved through LangGraph
    channel initialisation so it arrives at nodes unchanged.

    If State TypedDict stops declaring selected_doc_ids, LangGraph will
    silently drop it and this test will fail.
    """

    @pytest.mark.asyncio
    async def test_selected_doc_ids_reaches_node(self):
        """selected_doc_ids from build_initial_state arrives inside the node."""
        captured: dict = {}

        async def capture_node(state: State) -> dict:
            captured["selected_doc_ids"] = state.get("selected_doc_ids")
            return {}

        graph = StateGraph(State)
        graph.add_node("capture", capture_node)
        graph.add_edge(START, "capture")
        graph.add_edge("capture", END)
        app = graph.compile()

        initial_state = build_initial_state(
            {"selected_doc_ids": ["doc-abc", "doc-xyz"]},
            library_path="/tmp/test.fichero",
        )
        await app.ainvoke(initial_state)

        assert captured["selected_doc_ids"] == ["doc-abc", "doc-xyz"], (
            "selected_doc_ids was dropped by LangGraph — check State TypedDict declaration"
        )

    @pytest.mark.asyncio
    async def test_empty_selection_does_not_raise(self):
        """Empty selected_doc_ids is valid and preserved."""
        captured: dict = {}

        async def capture_node(state: State) -> dict:
            captured["selected_doc_ids"] = state.get("selected_doc_ids")
            return {}

        graph = StateGraph(State)
        graph.add_node("capture", capture_node)
        graph.add_edge(START, "capture")
        graph.add_edge("capture", END)
        app = graph.compile()

        initial_state = build_initial_state(
            {"selected_doc_ids": []},
            library_path="/tmp/test.fichero",
        )
        await app.ainvoke(initial_state)

        assert captured["selected_doc_ids"] == []

    @pytest.mark.asyncio
    async def test_missing_selection_defaults_to_empty_list(self):
        """When selected_doc_ids is absent from inputs, state gets []."""
        captured: dict = {}

        async def capture_node(state: State) -> dict:
            captured["selected_doc_ids"] = state.get("selected_doc_ids")
            return {}

        graph = StateGraph(State)
        graph.add_node("capture", capture_node)
        graph.add_edge(START, "capture")
        graph.add_edge("capture", END)
        app = graph.compile()

        initial_state = build_initial_state({}, library_path="/tmp/test.fichero")
        await app.ainvoke(initial_state)

        assert captured["selected_doc_ids"] == []


# ---------------------------------------------------------------------------
# Layer 2: files_tool end-to-end via real build_graph
# ---------------------------------------------------------------------------

class TestFilesToolEndToEnd:
    """
    End-to-end tests for files_tool using the real workflow builder.
    Database calls are mocked so no filesystem is needed.
    """

    @pytest.mark.asyncio
    async def test_files_tool_returns_selected_docs(self):
        """
        files_tool must resolve selected_doc_ids from state into file paths.

        This is the primary regression: running Transcribe from the contextual
        menu sends selected_doc_ids, which used to be dropped by LangGraph and
        now must reach files_tool via state.
        """
        workflow, files_node_id = _files_only_workflow()
        doc = _make_doc("doc-abc", "/library/letter.pdf")

        mock_db = MagicMock()
        mock_db.get.return_value = doc

        with patch("fichero_server.workflows.tools.sources.db_manager") as mock_mgr:
            mock_mgr.get_database.return_value = mock_db

            app = build_graph(workflow, enable_parallel=False)
            initial_state = build_initial_state(
                {"selected_doc_ids": ["doc-abc"]},
                library_path="/tmp/test.fichero",
            )
            final_state = await app.ainvoke(initial_state)

        output = final_state["outputs"][files_node_id]
        assert output["count"] == 1
        assert "/library/letter.pdf" in output["files"]
        mock_db.get.assert_called_once_with(Document, "doc-abc")

    @pytest.mark.asyncio
    async def test_files_tool_empty_config_falls_through_to_selection(self):
        """
        Files node with file_ids: [] in config must fall through to
        selected_doc_ids, not return 0 files.

        This is the other half of the original bug: config injected inputs["files"] = []
        which was truthy under the old `is not None` check.
        """
        workflow, files_node_id = _files_only_workflow()
        # Simulate the Files node config that the Swift editor writes
        workflow.nodes[0].config = {"files": []}

        doc = _make_doc("doc-xyz", "/library/report.pdf")
        mock_db = MagicMock()
        mock_db.get.return_value = doc

        with patch("fichero_server.workflows.tools.sources.db_manager") as mock_mgr:
            mock_mgr.get_database.return_value = mock_db

            app = build_graph(workflow, enable_parallel=False)
            initial_state = build_initial_state(
                {"selected_doc_ids": ["doc-xyz"]},
                library_path="/tmp/test.fichero",
            )
            final_state = await app.ainvoke(initial_state)

        output = final_state["outputs"][files_node_id]
        assert output["count"] == 1, (
            "files_tool returned 0 files — empty config list short-circuited selection"
        )
        assert "/library/report.pdf" in output["files"]

    @pytest.mark.asyncio
    async def test_files_tool_with_no_selection_returns_empty(self):
        """No selection and no input_files → files_tool returns 0 files gracefully."""
        workflow, files_node_id = _files_only_workflow()

        with patch("fichero_server.workflows.tools.sources.db_manager"):
            app = build_graph(workflow, enable_parallel=False)
            initial_state = build_initial_state(
                {"selected_doc_ids": []},
                library_path="/tmp/test.fichero",
            )
            final_state = await app.ainvoke(initial_state)

        output = final_state["outputs"][files_node_id]
        assert output["count"] == 0
        assert output["files"] == []

    @pytest.mark.asyncio
    async def test_files_tool_multi_selection(self):
        """Multiple selected docs all resolve to file paths."""
        workflow, files_node_id = _files_only_workflow()

        docs = {
            "doc-1": _make_doc("doc-1", "/library/a.pdf"),
            "doc-2": _make_doc("doc-2", "/library/b.pdf"),
            "doc-3": _make_doc("doc-3", "/library/c.pdf"),
        }
        mock_db = MagicMock()
        mock_db.get.side_effect = lambda model, doc_id: docs.get(doc_id)

        with patch("fichero_server.workflows.tools.sources.db_manager") as mock_mgr:
            mock_mgr.get_database.return_value = mock_db

            app = build_graph(workflow, enable_parallel=False)
            initial_state = build_initial_state(
                {"selected_doc_ids": ["doc-1", "doc-2", "doc-3"]},
                library_path="/tmp/test.fichero",
            )
            final_state = await app.ainvoke(initial_state)

        output = final_state["outputs"][files_node_id]
        assert output["count"] == 3
        assert set(output["files"]) == {"/library/a.pdf", "/library/b.pdf", "/library/c.pdf"}

    @pytest.mark.asyncio
    async def test_files_tool_folder_selection_preserves_media_and_pdf_pages(self):
        """Default workflows use files_tool; guard its mixed-media routing."""
        workflow, files_node_id = _files_only_workflow()
        folder = Document(id="folder", name="Folder", doc_type=DocType.folder)
        image = _make_doc("image", "/library/scan.jpg")
        image.file_type = FileType.image
        docx = _make_doc("docx", "/library/report.docx")
        docx.file_type = FileType.docx
        audio = _make_doc("audio", "/library/interview.mp3")
        audio.file_type = FileType.audio
        video = _make_doc("video", "/library/film.mov")
        video.file_type = FileType.video
        pdf = _make_doc("pdf", "/library/book.pdf")
        pdf.file_type = FileType.pdf
        page1 = Document(id="page-1", name="Page 1", doc_type=DocType.page, parent_id="pdf", sequence=1)
        page2 = Document(id="page-2", name="Page 2", doc_type=DocType.page, parent_id="pdf", sequence=2)

        children = {
            "folder": [image, docx, audio, video, pdf],
            "pdf": [page2, page1],
        }
        mock_db = MagicMock()
        mock_db.get.return_value = folder
        mock_db.query.side_effect = lambda _model, **kwargs: children.get(kwargs.get("parent_id"), [])

        with (
            patch("fichero_server.workflows.tools.sources.db_manager") as mock_mgr,
            patch("fichero_server.workflows.tools.sources._resolve_abs_path", side_effect=lambda doc, _lib: doc.path),
        ):
            mock_mgr.get_database.return_value = mock_db
            app = build_graph(workflow, enable_parallel=False)
            initial_state = build_initial_state(
                {"selected_doc_ids": ["folder"]},
                library_path="/tmp/test.fichero",
            )
            final_state = await app.ainvoke(initial_state)

        output = final_state["outputs"][files_node_id]
        assert output["count"] == 6
        assert output["files"] == [
            "/library/scan.jpg",
            "/library/report.docx",
            "/library/interview.mp3",
            "/library/film.mov",
            "/library/book.pdf",
            "/library/book.pdf",
        ]
        assert [doc["id"] for doc in output["documents"]] == [
            "image",
            "docx",
            "audio",
            "video",
            "page-1",
            "page-2",
        ]

    @pytest.mark.asyncio
    async def test_files_tool_direct_page_selection_keeps_page_doc_with_parent_path(self):
        """Selecting one PDF page should process one page, not the whole PDF."""
        workflow, files_node_id = _files_only_workflow()
        parent = _make_doc("pdf", "/library/book.pdf")
        parent.file_type = FileType.pdf
        page = Document(
            id="page-7",
            name="Page 7",
            doc_type=DocType.page,
            parent_id=parent.id,
            sequence=7,
        )

        mock_db = MagicMock()
        mock_db.get.side_effect = lambda _model, doc_id: {"page-7": page, "pdf": parent}.get(doc_id)

        with (
            patch("fichero_server.workflows.tools.sources.db_manager") as mock_mgr,
            patch("fichero_server.workflows.tools.sources._resolve_abs_path", side_effect=lambda doc, _lib: doc.path),
        ):
            mock_mgr.get_database.return_value = mock_db
            app = build_graph(workflow, enable_parallel=False)
            initial_state = build_initial_state(
                {"selected_doc_ids": ["page-7"]},
                library_path="/tmp/test.fichero",
            )
            final_state = await app.ainvoke(initial_state)

        output = final_state["outputs"][files_node_id]
        assert output["count"] == 1
        assert output["files"] == ["/library/book.pdf"]
        assert [doc["id"] for doc in output["documents"]] == ["page-7"]
        assert output["documents"][0]["parent_id"] == "pdf"
        assert output["documents"][0]["sequence"] == 7
