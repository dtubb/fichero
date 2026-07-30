from __future__ import annotations

import asyncio
from pathlib import Path

from tests.integration._seedlib import seed

from fichero_server.db import db_manager
from fichero_server.models import Artifact, DocType, Document, FileType, Workflow
from fichero_server.workflows.builder import build_graph
from fichero_server.workflows.default_workflows import _load_preset_files
from fichero_server.workflows.runtime import build_initial_state, to_workflow_def

import fichero_server.workflows.tools  # noqa: F401


FIXTURE_TEXT = "Marshall went to Istmina this afternoon."


def test_import_artifacts_preset_registers_page_artifacts_and_is_idempotent(
    tmp_path: Path,
):
    library_path, parent_doc_id, page_doc_ids = _seed_importable_pdf_library(tmp_path)
    db = db_manager.get_database(library_path)
    workflow = _load_import_artifacts_workflow()

    first = asyncio.run(
        build_graph(workflow, skip_cache=True).ainvoke(
            _workflow_state(library_path, parent_doc_id, task_id="import-artifacts-first")
        )
    )
    assert not first.get("error")
    first_summary = first["outputs"]["import-artifacts"]["summary"]
    assert first_summary == {
        "documents_processed": 2,
        "artifacts_created": 4,
        "artifacts_skipped": 0,
    }

    second = asyncio.run(
        build_graph(workflow, skip_cache=True).ainvoke(
            _workflow_state(library_path, parent_doc_id, task_id="import-artifacts-second")
        )
    )
    assert not second.get("error")
    second_summary = second["outputs"]["import-artifacts"]["summary"]
    assert second_summary == {
        "documents_processed": 2,
        "artifacts_created": 0,
        "artifacts_skipped": 4,
    }

    artifacts = [
        artifact
        for artifact in db.query(Artifact)
        if artifact.document_id in set(page_doc_ids)
        and artifact.artifact_type in {"import_receipt", "transcription"}
    ]
    assert len(artifacts) == 4

    for page_doc_id in page_doc_ids:
        page_artifacts = db.query(Artifact, document_id=page_doc_id)
        artifact_types = {artifact.artifact_type for artifact in page_artifacts}
        assert {"import_receipt", "transcription"} <= artifact_types

        receipt = next(
            artifact
            for artifact in page_artifacts
            if artifact.artifact_type == "import_receipt"
        )
        assert receipt.data["source"] == "manifest-import"

        transcription = next(
            artifact
            for artifact in page_artifacts
            if artifact.artifact_type == "transcription"
        )
        assert transcription.content == FIXTURE_TEXT

        # #4345: the receipt shipped with a NULL workflow_id, so no import
        # artifact could be traced to the run that wrote it. Every artifact
        # this stage writes carries the full #4313 trio.
        for artifact in (receipt, transcription):
            assert artifact.run_id == "import-artifacts-first"
            assert artifact.workflow_id == (
                "default-import-artifacts-regression-harness"
            )
            assert artifact.step_name == "import-artifacts"
            assert artifact.sequence is not None and artifact.sequence >= 1


def _seed_importable_pdf_library(tmp_path: Path) -> tuple[Path, str, list[str]]:
    library_path = tmp_path / "import-artifacts-stage.fichero"
    seed(library_path)
    db = db_manager.get_database(library_path)

    source_file = tmp_path / "marshall-imported.pdf"
    source_file.write_bytes(b"%PDF-1.4\n% import artifacts fixture\n")

    parent_doc = Document(
        id="marshall-import-root",
        name="Marshall import root",
        path=str(source_file),
        doc_type=DocType.file,
        file_type=FileType.pdf,
        metadata={"canonical_external_id": "marshall-import-root"},
    )
    pages = [
        Document(
            id="marshall-import-page-1",
            parent_id=parent_doc.id,
            name="Marshall import page 1",
            doc_type=DocType.page,
            sequence=1,
            page_content=FIXTURE_TEXT,
            metadata={
                "canonical_external_id": "marshall-import-root__page_001",
                "page_label": "001",
                "page_number": 1,
                "transcription": FIXTURE_TEXT,
                "images": [{"role": "enhanced"}],
            },
        ),
        Document(
            id="marshall-import-page-2",
            parent_id=parent_doc.id,
            name="Marshall import page 2",
            doc_type=DocType.page,
            sequence=2,
            page_content=FIXTURE_TEXT,
            metadata={
                "canonical_external_id": "marshall-import-root__page_002",
                "page_label": "002",
                "page_number": 2,
                "transcription": FIXTURE_TEXT,
                "images": [{"role": "enhanced"}],
            },
        ),
    ]
    db.save(parent_doc)
    for page in pages:
        db.save(page)

    return library_path, parent_doc.id, [page.id for page in pages]


def _load_import_artifacts_workflow():
    preset = next(p for p in _load_preset_files() if p["name"] == "1 · Import → Artifacts")
    return to_workflow_def(
        Workflow(
            id="default-import-artifacts-regression-harness",
            name=preset["name"],
            description=preset.get("description", ""),
            nodes=preset["nodes"],
            edges=preset["edges"],
            config=preset.get("config", {}),
            folder_path=preset.get("folder_path", "/"),
        )
    )


def _workflow_state(library_path: Path, selected_doc_id: str, *, task_id: str) -> dict:
    state = build_initial_state(
        {"selected_doc_ids": [selected_doc_id]},
        library_path=str(library_path),
    )
    state["workflow_id"] = "default-import-artifacts-regression-harness"
    state["task_id"] = task_id
    return state
