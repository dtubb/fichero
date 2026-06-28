"""Tests for the export_documents workflow tool."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from tests.integration._seedlib import seed

from fichero.db import db_manager
from fichero.models import DocType, Document, FileType
from fichero.workflows.builder import build_graph
from fichero.workflows.default_workflows import _load_preset_files
from fichero.workflows.runtime import build_initial_state, to_workflow_def

import fichero.workflows.tools  # noqa: F401


FIXTURE_TEXT = "Ada signed the ledger in Mockton."


def _seed_library(tmp_path: Path) -> tuple[Path, str, str]:
    """Seed a library with a folder containing a text doc and a PDF parent."""
    library_path = tmp_path / "export-documents.fichero"
    seed(library_path)
    db = db_manager.get_database(library_path)

    source_file = tmp_path / "export-fixture.pdf"
    source_file.write_bytes(b"%PDF-1.4\n% export fixture\n")

    folder = Document(
        id="export-folder",
        name="Export Folder",
        doc_type=DocType.folder,
    )
    text_doc = Document(
        id="export-text",
        parent_id=folder.id,
        name="Export Letter",
        doc_type=DocType.file,
        file_type=FileType.text,
        page_content=FIXTURE_TEXT,
    )
    parent_doc = Document(
        id="export-pdf",
        parent_id=folder.id,
        name="Export PDF",
        path=str(source_file),
        doc_type=DocType.file,
        file_type=FileType.pdf,
    )
    db.save(folder)
    db.save(text_doc)
    db.save(parent_doc)

    return library_path, folder.id, parent_doc.id


def _load_preset_workflow(name: str):
    preset = next(p for p in _load_preset_files() if p["name"] == name)
    return to_workflow_def(
        __import__("fichero.models", fromlist=["Workflow"]).Workflow(
            id="default-export-regression-harness",
            name=preset["name"],
            description=preset.get("description", ""),
            nodes=preset["nodes"],
            edges=preset["edges"],
            config=preset.get("config", {}),
            folder_path=preset.get("folder_path", "/"),
        )
    )


def _workflow_state(
    library_path: Path,
    selected_doc_id: str | None,
    task_id: str,
    destination: str,
) -> dict:
    state = build_initial_state(
        {"selected_doc_ids": [selected_doc_id] if selected_doc_id else []},
        library_path=str(library_path),
    )
    state["workflow_id"] = "default-export-regression-harness"
    state["task_id"] = task_id
    return state


@pytest.mark.asyncio
async def test_export_documents_all_formats(tmp_path: Path):
    library_path, folder_id, _parent_id = _seed_library(tmp_path)
    workflow = _load_preset_workflow("Export to Desktop (MD + DOCX + XLSX)")
    destination = tmp_path / "desktop"

    # Patch the preset destination to our temp dir.
    for node in workflow.nodes:
        if node.tool == "export_documents":
            node.config["destination"] = str(destination)

    result = await build_graph(workflow, skip_cache=True).ainvoke(
        _workflow_state(library_path, folder_id, "export-all", str(destination))
    )

    assert not result.get("error")
    export_node_id = next(n.id for n in workflow.nodes if n.tool == "export_documents")
    output = result["outputs"][export_node_id]
    assert output["count"] > 0

    export_dir = destination / "Export Folder"
    md_index = export_dir / "Export Folder_markdown" / "index.md"
    docx_file = export_dir / "Export Folder.docx"
    xlsx_file = export_dir / "Export Folder.xlsx"
    assert md_index.exists()
    assert md_index.stat().st_size > 0
    assert docx_file.exists()
    assert docx_file.stat().st_size > 0
    assert xlsx_file.exists()
    assert xlsx_file.stat().st_size > 0

    with zipfile.ZipFile(docx_file) as docx_zip:
        docx_names = set(docx_zip.namelist())
    assert "word/document.xml" in docx_names


@pytest.mark.asyncio
async def test_export_documents_single_format(tmp_path: Path):
    library_path, folder_id, _parent_id = _seed_library(tmp_path)
    workflow = _load_preset_workflow("Export to Desktop (MD + DOCX + XLSX)")
    destination = tmp_path / "single"

    for node in workflow.nodes:
        if node.tool == "export_documents":
            node.config["destination"] = str(destination)
            node.config["formats"] = ["markdown"]

    result = await build_graph(workflow, skip_cache=True).ainvoke(
        _workflow_state(library_path, folder_id, "export-single", str(destination))
    )

    assert not result.get("error")

    export_dir = destination / "Export Folder"
    md_index = export_dir / "Export Folder_markdown" / "index.md"
    docx_file = export_dir / "Export Folder.docx"
    xlsx_file = export_dir / "Export Folder.xlsx"
    assert md_index.exists()
    assert md_index.stat().st_size > 0
    assert not docx_file.exists()
    assert not xlsx_file.exists()


@pytest.mark.asyncio
async def test_export_documents_folder_scope(tmp_path: Path):
    library_path, folder_id, parent_id = _seed_library(tmp_path)
    workflow = _load_preset_workflow("Export to Desktop (MD + DOCX + XLSX)")
    destination = tmp_path / "scoped"

    for node in workflow.nodes:
        if node.tool == "export_documents":
            node.config["destination"] = str(destination)
            node.config["formats"] = ["xlsx"]

    # Run on the parent PDF only; the folder-scoped run should contain more rows.
    folder_result = await build_graph(workflow, skip_cache=True).ainvoke(
        _workflow_state(library_path, folder_id, "export-folder", str(destination))
    )
    parent_result = await build_graph(workflow, skip_cache=True).ainvoke(
        _workflow_state(library_path, parent_id, "export-parent", str(destination))
    )

    assert not folder_result.get("error")
    assert not parent_result.get("error")
    export_node_id = next(n.id for n in workflow.nodes if n.tool == "export_documents")

    folder_file = Path(folder_result["outputs"][export_node_id]["files"][0])
    parent_file = Path(parent_result["outputs"][export_node_id]["files"][0])
    assert folder_file.exists()
    assert folder_file.stat().st_size > 0
    assert parent_file.exists()
    assert parent_file.stat().st_size > 0
    assert folder_file.stat().st_size >= parent_file.stat().st_size


@pytest.mark.asyncio
async def test_export_documents_eleventy_site_format(tmp_path: Path):
    """#2535: the 11ty/Netlify website target is chainable as a workflow node."""
    library_path, folder_id, _parent_id = _seed_library(tmp_path)
    workflow = _load_preset_workflow("Export to Desktop (MD + DOCX + XLSX)")
    destination = tmp_path / "site"

    for node in workflow.nodes:
        if node.tool == "export_documents":
            node.config["destination"] = str(destination)
            node.config["formats"] = ["eleventy"]

    result = await build_graph(workflow, skip_cache=True).ainvoke(
        _workflow_state(library_path, folder_id, "export-site", str(destination))
    )

    assert not result.get("error")
    export_node_id = next(n.id for n in workflow.nodes if n.tool == "export_documents")
    output = result["outputs"][export_node_id]
    assert output["count"] > 0

    site_dir = destination / "Export Folder" / "Export Folder_site"
    # Buildable + deployable 11ty scaffold.
    assert (site_dir / "package.json").exists()
    assert (site_dir / ".eleventy.js").exists()
    assert (site_dir / "netlify.toml").exists()
    assert (site_dir / "src" / "index.md").exists()

    # Edge: the other formats are NOT produced when only eleventy is requested.
    assert not (destination / "Export Folder" / "Export Folder.docx").exists()
    assert not (destination / "Export Folder" / "Export Folder.xlsx").exists()


@pytest.mark.asyncio
async def test_export_documents_eleventy_alongside_other_formats(tmp_path: Path):
    """Regression: adding eleventy doesn't disturb the existing md/docx/xlsx outputs."""
    library_path, folder_id, _parent_id = _seed_library(tmp_path)
    workflow = _load_preset_workflow("Export to Desktop (MD + DOCX + XLSX)")
    destination = tmp_path / "combo"

    for node in workflow.nodes:
        if node.tool == "export_documents":
            node.config["destination"] = str(destination)
            node.config["formats"] = ["markdown", "eleventy"]

    result = await build_graph(workflow, skip_cache=True).ainvoke(
        _workflow_state(library_path, folder_id, "export-combo", str(destination))
    )

    assert not result.get("error")
    export_dir = destination / "Export Folder"
    assert (export_dir / "Export Folder_markdown" / "index.md").exists()
    assert (export_dir / "Export Folder_site" / "package.json").exists()
