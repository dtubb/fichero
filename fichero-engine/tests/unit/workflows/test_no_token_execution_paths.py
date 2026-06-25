from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from fichero.models import DocType, Document, FileType, Status
from fichero.workflows.builder import build_graph
from fichero.workflows.runtime import build_initial_state
from fichero.workflows.types import EdgeDef, NodeDef, WorkflowDef

# Import tool modules for registry side effects before build_graph().
import fichero.workflows.tools  # noqa: F401


def _make_doc(
    doc_id: str,
    path: str,
    *,
    file_type: FileType,
    doc_type: DocType = DocType.file,
    parent_id: str | None = None,
    sequence: int | None = None,
) -> Document:
    return Document(
        id=doc_id,
        name=path.split("/")[-1],
        doc_type=doc_type,
        file_type=file_type,
        path=path if doc_type != DocType.page else None,
        parent_id=parent_id,
        sequence=sequence,
        status=Status.completed,
    )


def _workflow_for(tool_name: str) -> tuple[WorkflowDef, str]:
    tool_node_id = f"{tool_name}-node"
    return (
        WorkflowDef(
            name=f"{tool_name} no-token exec",
            nodes=[
                NodeDef(id="files-source", tool="files", config={}),
                NodeDef(id=tool_node_id, tool=tool_name, config={}),
            ],
            edges=[
                EdgeDef(
                    source="files-source",
                    target=tool_node_id,
                    source_port="files",
                    target_port="files",
                ),
                EdgeDef(
                    source="files-source",
                    target=tool_node_id,
                    source_port="documents",
                    target_port="documents",
                ),
            ],
        ),
        tool_node_id,
    )


def _run_workflow_for_selection(
    *,
    workflow: WorkflowDef,
    selected_doc_ids: list[str],
    docs_by_id: dict[str, Document],
    children_by_parent: dict[str, list[Document]] | None = None,
):
    mock_db = MagicMock()
    mock_db.get.side_effect = lambda _model, doc_id: docs_by_id.get(doc_id)
    child_map = children_by_parent or {}
    mock_db.query.side_effect = lambda _model, **kwargs: child_map.get(kwargs.get("parent_id"), [])

    with (
        patch("fichero.workflows.tools.sources.db_manager") as mock_mgr,
        patch(
            "fichero.workflows.tools.sources._resolve_abs_path",
            side_effect=lambda doc, _lib: doc.path,
        ),
    ):
        mock_mgr.get_database.return_value = mock_db
        final_state = asyncio.run(
            build_graph(workflow, enable_parallel=False).ainvoke(
                build_initial_state(
                    {"selected_doc_ids": selected_doc_ids},
                    library_path="/tmp/test.fichero",
                )
            )
        )
    return final_state


@pytest.mark.parametrize(
    ("suffix", "file_type"),
    [
        (".txt", FileType.text),
        (".docx", FileType.docx),
    ],
)
def test_transcribe_executes_digital_text_selection_without_external_calls(
    monkeypatch: pytest.MonkeyPatch,
    suffix: str,
    file_type: FileType,
):
    workflow, tool_node_id = _workflow_for("transcribe")
    doc = _make_doc(f"digital-{suffix[1:]}", f"/library/source{suffix}", file_type=file_type)
    captured: dict = {}

    async def fake_process_vision(**kwargs):
        captured["files"] = kwargs.get("files")
        captured["documents"] = kwargs.get("documents")
        return {
            "text": "digital text fixture",
            "value": "digital text fixture",
            "records": [{"doc_id": doc.id, "text": "digital text fixture"}],
            "page_records": [{"doc_id": doc.id, "text": "digital text fixture"}],
            "artifacts": [],
            "output_files": [],
            "error": None,
        }

    monkeypatch.setattr("fichero.workflows.tools.transcribe.process_vision", fake_process_vision)

    final_state = _run_workflow_for_selection(
        workflow=workflow,
        selected_doc_ids=[doc.id],
        docs_by_id={doc.id: doc},
    )

    assert not final_state.get("error")
    assert {"files-source", tool_node_id} <= set(final_state.get("completed_nodes") or [])
    assert captured["files"] == [doc.path]
    assert [item["id"] for item in captured["documents"]] == [doc.id]
    assert final_state["outputs"][tool_node_id]["records"][0]["doc_id"] == doc.id


def test_transcribe_executes_only_the_selected_pdf_page(
    monkeypatch: pytest.MonkeyPatch,
):
    workflow, tool_node_id = _workflow_for("transcribe")
    parent = _make_doc("pdf-parent", "/library/book.pdf", file_type=FileType.pdf)
    selected_page = _make_doc(
        "page-7",
        parent.path,
        file_type=FileType.pdf,
        doc_type=DocType.page,
        parent_id=parent.id,
        sequence=7,
    )
    sibling_page = _make_doc(
        "page-8",
        parent.path,
        file_type=FileType.pdf,
        doc_type=DocType.page,
        parent_id=parent.id,
        sequence=8,
    )
    captured: dict = {}

    async def fake_process_vision(**kwargs):
        captured["files"] = kwargs.get("files")
        captured["documents"] = kwargs.get("documents")
        return {
            "text": "page 7 fixture",
            "value": "page 7 fixture",
            "records": [{"doc_id": selected_page.id, "text": "page 7 fixture"}],
            "page_records": [{"doc_id": selected_page.id, "text": "page 7 fixture"}],
            "artifacts": [],
            "output_files": [],
            "error": None,
        }

    monkeypatch.setattr("fichero.workflows.tools.transcribe.process_vision", fake_process_vision)

    final_state = _run_workflow_for_selection(
        workflow=workflow,
        selected_doc_ids=[selected_page.id],
        docs_by_id={
            parent.id: parent,
            selected_page.id: selected_page,
            sibling_page.id: sibling_page,
        },
    )

    assert not final_state.get("error")
    assert captured["files"] == [parent.path]
    assert [item["id"] for item in captured["documents"]] == [selected_page.id]
    assert all(item["id"] != sibling_page.id for item in captured["documents"])
    assert final_state["outputs"][tool_node_id]["page_records"] == [
        {"doc_id": selected_page.id, "text": "page 7 fixture"}
    ]


@pytest.mark.parametrize(
    ("tool_name", "patch_target", "path", "file_type"),
    [
        ("audio_transcribe", "fichero.workflows.tools.audio_transcribe.process_audio", "/library/interview.mp3", FileType.audio),
        ("video_describe", "fichero.workflows.tools.video_describe.process_video", "/library/film.mov", FileType.video),
    ],
)
def test_media_tools_execute_selected_file_without_external_calls(
    monkeypatch: pytest.MonkeyPatch,
    tool_name: str,
    patch_target: str,
    path: str,
    file_type: FileType,
):
    workflow, tool_node_id = _workflow_for(tool_name)
    doc = _make_doc(tool_name, path, file_type=file_type)
    captured: dict = {}

    async def fake_media_process(**kwargs):
        captured["files"] = kwargs.get("files")
        captured["documents"] = kwargs.get("documents")
        return {
            "text": f"{tool_name} fixture",
            "value": f"{tool_name} fixture",
            "records": [{"doc_id": doc.id, "text": f"{tool_name} fixture"}],
            "artifacts": [],
            "output_files": [],
            "error": None,
        }

    monkeypatch.setattr(patch_target, fake_media_process)

    final_state = _run_workflow_for_selection(
        workflow=workflow,
        selected_doc_ids=[doc.id],
        docs_by_id={doc.id: doc},
    )

    assert not final_state.get("error")
    assert {"files-source", tool_node_id} <= set(final_state.get("completed_nodes") or [])
    assert captured["files"] == [doc.path]
    assert [item["id"] for item in captured["documents"]] == [doc.id]
    assert final_state["outputs"][tool_node_id]["records"][0]["doc_id"] == doc.id
