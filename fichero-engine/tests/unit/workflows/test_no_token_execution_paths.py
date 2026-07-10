from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from tests.integration._seedlib import seed

from fichero.db import db_manager
from fichero.models import DocType, Document, FileType, Status, Workflow
from fichero.workflows.builder import build_graph
from fichero.workflows.default_workflows import _load_preset_files
from fichero.workflows import registry as workflow_registry
from fichero.workflows.runtime import build_initial_state
from fichero.workflows.runtime import to_workflow_def
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


def _workflow_from_preset(name: str, *, provider_name: str | None = None) -> WorkflowDef:
    preset = next(p for p in _load_preset_files() if p["name"] == name)
    if provider_name is not None:
        preset = {
            **preset,
            "nodes": [
                {
                    **node,
                    "config": {
                        **node.get("config", {}),
                        **({"provider_name": provider_name} if node["tool"] != "files" else {}),
                    },
                }
                for node in preset["nodes"]
            ],
        }
    return to_workflow_def(
        Workflow(
            id=f"no-token-{name.lower().replace(' ', '-')}",
            name=preset["name"],
            description=preset.get("description", ""),
            nodes=preset["nodes"],
            edges=preset["edges"],
            config=preset.get("config", {}),
            folder_path=preset.get("folder_path", "/"),
        )
    )


def _run_workflow_for_selection(
    *,
    workflow: WorkflowDef,
    selected_doc_ids: list[str],
    docs_by_id: dict[str, Document],
    children_by_parent: dict[str, list[Document]] | None = None,
    library_path: str = "/tmp/test.fichero",
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
                    library_path=library_path,
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
    "case_name",
    ["text", "docx", "selected_page", "whole_pdf", "folder", "multi_file"],
)
def test_transcribe_no_token_selection_matrix(
    monkeypatch: pytest.MonkeyPatch,
    case_name: str,
):
    workflow, tool_node_id = _workflow_for("transcribe")
    captured: dict = {}

    async def fake_process_vision(**kwargs):
        captured["files"] = kwargs.get("files")
        captured["documents"] = kwargs.get("documents")
        records = []
        for doc in kwargs.get("documents") or []:
            doc_id = doc.get("id")
            if doc_id:
                records.append({"doc_id": doc_id, "text": f"fixture::{doc_id}"})
        text = "\n\n".join(record["text"] for record in records)
        return {
            "text": text,
            "value": text,
            "records": records,
            "page_records": records,
            "artifacts": [],
            "output_files": [],
            "error": None,
        }

    monkeypatch.setattr("fichero.workflows.tools.transcribe.process_vision", fake_process_vision)

    if case_name == "text":
        doc = _make_doc("text-1", "/library/source.txt", file_type=FileType.text)
        selected_doc_ids = [doc.id]
        docs_by_id = {doc.id: doc}
        children_by_parent = None
        expected_files = [doc.path]
        expected_docs = [doc.id]
    elif case_name == "docx":
        doc = _make_doc("docx-1", "/library/source.docx", file_type=FileType.docx)
        selected_doc_ids = [doc.id]
        docs_by_id = {doc.id: doc}
        children_by_parent = None
        expected_files = [doc.path]
        expected_docs = [doc.id]
    elif case_name == "selected_page":
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
        selected_doc_ids = [selected_page.id]
        docs_by_id = {
            parent.id: parent,
            selected_page.id: selected_page,
            sibling_page.id: sibling_page,
        }
        children_by_parent = {parent.id: [selected_page, sibling_page]}
        expected_files = [parent.path]
        expected_docs = [selected_page.id]
    elif case_name == "whole_pdf":
        parent = _make_doc("pdf-parent", "/library/book.pdf", file_type=FileType.pdf)
        page_1 = _make_doc(
            "page-1",
            parent.path,
            file_type=FileType.pdf,
            doc_type=DocType.page,
            parent_id=parent.id,
            sequence=1,
        )
        page_2 = _make_doc(
            "page-2",
            parent.path,
            file_type=FileType.pdf,
            doc_type=DocType.page,
            parent_id=parent.id,
            sequence=2,
        )
        selected_doc_ids = [parent.id]
        docs_by_id = {parent.id: parent, page_1.id: page_1, page_2.id: page_2}
        children_by_parent = {parent.id: [page_1, page_2]}
        expected_files = [parent.path, parent.path]
        expected_docs = [page_1.id, page_2.id]
    elif case_name == "folder":
        folder = _make_doc(
            "folder-1",
            "/library/folder",
            file_type=FileType.text,
            doc_type=DocType.folder,
        )
        file_1 = _make_doc("file-1", "/library/folder/a.txt", file_type=FileType.text, parent_id=folder.id)
        file_2 = _make_doc("file-2", "/library/folder/b.docx", file_type=FileType.docx, parent_id=folder.id)
        selected_doc_ids = [folder.id]
        docs_by_id = {folder.id: folder, file_1.id: file_1, file_2.id: file_2}
        children_by_parent = {folder.id: [file_1, file_2]}
        expected_files = [file_1.path, file_2.path]
        expected_docs = [file_1.id, file_2.id]
    else:
        file_1 = _make_doc("file-1", "/library/a.txt", file_type=FileType.text)
        file_2 = _make_doc("file-2", "/library/b.txt", file_type=FileType.text)
        selected_doc_ids = [file_1.id, file_2.id]
        docs_by_id = {file_1.id: file_1, file_2.id: file_2}
        children_by_parent = None
        expected_files = [file_1.path, file_2.path]
        expected_docs = [file_1.id, file_2.id]

    final_state = _run_workflow_for_selection(
        workflow=workflow,
        selected_doc_ids=selected_doc_ids,
        docs_by_id=docs_by_id,
        children_by_parent=children_by_parent,
    )

    assert not final_state.get("error"), case_name
    assert captured["files"] == expected_files, case_name
    assert [item["id"] for item in captured["documents"]] == expected_docs, case_name
    assert [record["doc_id"] for record in final_state["outputs"][tool_node_id]["records"]] == expected_docs, case_name
    assert [record["doc_id"] for record in final_state["outputs"][tool_node_id]["page_records"]] == expected_docs, case_name


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


def test_transcribe_htr_runs_without_tokens_and_keeps_page_scope(
    monkeypatch: pytest.MonkeyPatch,
):
    workflow = _workflow_from_preset("Transcribe HTR", provider_name="mock")
    node_ids = {node.tool: node.id for node in workflow.nodes}
    parent = _make_doc("pdf-parent", "/library/book.pdf", file_type=FileType.pdf)
    page_1 = _make_doc(
        "page-1",
        parent.path,
        file_type=FileType.pdf,
        doc_type=DocType.page,
        parent_id=parent.id,
        sequence=1,
    )
    page_2 = _make_doc(
        "page-2",
        parent.path,
        file_type=FileType.pdf,
        doc_type=DocType.page,
        parent_id=parent.id,
        sequence=2,
    )
    captured: dict = {}

    async def fake_process_vision(**kwargs):
        captured.setdefault("calls", []).append(kwargs)
        records = []
        for doc in kwargs.get("documents") or []:
            doc_id = doc.get("id")
            if doc_id:
                records.append({"doc_id": doc_id, "text": f"htr::{doc_id}"})
        text = "\n\n".join(record["text"] for record in records)
        return {
            "text": text,
            "value": text,
            "records": records,
            "page_records": records,
            "artifacts": [],
            "output_files": [],
            "error": None,
        }

    async def fake_search(inputs, state, llm_config):
        del inputs, state, llm_config
        return {"files": [], "documents": [], "count": 0}

    monkeypatch.setattr("fichero.workflows.tools.transcribe.process_vision", fake_process_vision)
    monkeypatch.setattr(
        "fichero.workflows.tools.transcribe_review.process_vision",
        fake_process_vision,
    )
    monkeypatch.setattr(
        "fichero.llm.resolve_model_alias_for_capability",
        lambda *args, **kwargs: ("openai", "gpt-4o"),
    )
    monkeypatch.setitem(workflow_registry.TOOLS, "search", fake_search)

    final_state = _run_workflow_for_selection(
        workflow=workflow,
        selected_doc_ids=[parent.id],
        docs_by_id={
            parent.id: parent,
            page_1.id: page_1,
            page_2.id: page_2,
        },
        children_by_parent={parent.id: [page_1, page_2]},
    )

    assert not final_state.get("error")
    assert len(captured["calls"]) >= 1
    assert [item["id"] for item in captured["calls"][0]["documents"]] == [page_1.id, page_2.id]
    assert [record["doc_id"] for record in final_state["outputs"][node_ids["transcribe_review"]]["records"]] == [
        page_1.id,
        page_2.id,
    ]


def test_catalogue_full_pipeline_runs_from_folder_with_stubs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    workflow = _workflow_from_preset("Catalogue", provider_name="mock")
    library_path, folder, docs_by_id, expected_doc_ids = _seed_full_pipeline_folder(tmp_path)
    node_ids = {node.tool: node.id for node in workflow.nodes}

    async def fake_entities(**kwargs):
        del kwargs
        from fichero.workflows.tools.extract_all import _EntitiesOnly, _EntityOnly

        return _EntitiesOnly(
            people=[_EntityOnly(name="Ada Mock", aliases=[])],
            places=[_EntityOnly(name="Mockton", aliases=[])],
            organizations=[],
            dates=[],
            events=[],
        )

    async def fake_claims_for_entity(
        chunk_text: str,
        entity_name: str,
        entity_type: str,
        llm_config,
        instructions: str,
        extraction_sem,
    ) -> list[dict]:
        del chunk_text, entity_type, llm_config, instructions, extraction_sem
        if entity_name == "Ada Mock":
            return [
                {
                    "name": entity_name,
                    "verb": "signed",
                    "object": "the ledger",
                    "source_text": "Ada Mock signed the ledger in Mockton.",
                    "epistemic_status": "confirmed",
                    "claim_type": "fact",
                }
            ]
        if entity_name == "Mockton":
            return [
                {
                    "name": entity_name,
                    "verb": "is",
                    "object": "the town where Ada signed the ledger",
                    "source_text": "Ada Mock signed the ledger in Mockton.",
                    "epistemic_status": "confirmed",
                    "claim_type": "fact",
                }
            ]
        return []

    monkeypatch.setattr(
        "fichero.llm.resolve_model_alias_for_capability",
        lambda *args, **kwargs: ("openai", "gpt-4o"),
    )
    monkeypatch.setattr(
        "fichero.workflows.tools.extract_entities_only.chat_structured_with_fallback",
        fake_entities,
    )
    monkeypatch.setattr(
        "fichero.workflows.tools.extract_svo_only._extract_claims_for_entity",
        fake_claims_for_entity,
    )
    monkeypatch.setattr(
        "fichero.kg.entity_vectors.find_similar",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "fichero.kg.entity_vectors.index_entity",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "fichero.kg.rebuild.rebuild_kg",
        lambda *args, **kwargs: {"entities": 0, "claims": 0, "triples_written": 0},
    )
    monkeypatch.setattr(
        "fichero.workflows.tools.kg_persist_finalize._vector_row_count",
        lambda *args, **kwargs: 0,
    )
    monkeypatch.setattr(
        "fichero.db.Database.embed_entities",
        lambda self, entities: 0,
    )
    monkeypatch.setattr(
        "fichero.db.Database.embed_claims",
        lambda self, claims: 0,
    )
    monkeypatch.setattr(
        "fichero.db.Database._embed_texts",
        lambda self, texts: [[1.0] + ([0.0] * 1023) for _ in texts],
    )

    final_state = _run_workflow_for_selection(
        workflow=workflow,
        selected_doc_ids=[folder.id],
        docs_by_id=docs_by_id,
        children_by_parent={folder.id: [docs_by_id[doc_id] for doc_id in expected_doc_ids]},
        library_path=str(library_path),
    )

    assert not final_state.get("error")
    assert set(node_ids.values()) <= set(final_state.get("completed_nodes") or [])
    assert final_state["outputs"][node_ids["files"]]["count"] == 2
    assert final_state["outputs"][node_ids["import_artifacts"]]["summary"]["documents_processed"] == 2
    assert final_state["outputs"][node_ids["extract_entities_only"]]["summary"]["documents_processed"] == 2
    assert final_state["outputs"][node_ids["extract_svo_only"]]["summary"]["documents_processed"] == 2
    assert final_state["outputs"][node_ids["merge_dedup_only"]]["summary"]["documents_scoped"] == 2
    assert final_state["outputs"][node_ids["kg_persist_finalize"]]["summary"]["documents_scoped"] == 2


def _seed_full_pipeline_folder(tmp_path):
    library_path = tmp_path / "catalogue-full-pipeline.fichero"
    seed(library_path)
    db = db_manager.get_database(library_path)
    folder = _make_doc(
        "catalogue-folder",
        "/library/catalogue-folder",
        file_type=FileType.text,
        doc_type=DocType.folder,
    )
    file_1 = _make_doc(
        "catalogue-file-1",
        "/library/catalogue-folder/a.txt",
        file_type=FileType.text,
        parent_id=folder.id,
    )
    file_2 = _make_doc(
        "catalogue-file-2",
        "/library/catalogue-folder/b.txt",
        file_type=FileType.text,
        parent_id=folder.id,
    )
    file_1.page_content = "Ada Mock signed the ledger in Mockton."
    file_2.page_content = "Ada Mock signed the ledger in Mockton."
    db.save(folder)
    db.save(file_1)
    db.save(file_2)
    docs_by_id = {folder.id: folder, file_1.id: file_1, file_2.id: file_2}
    return library_path, folder, docs_by_id, [file_1.id, file_2.id]
