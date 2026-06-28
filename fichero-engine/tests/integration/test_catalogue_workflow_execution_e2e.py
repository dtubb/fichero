"""Opt-in API-level Catalogue workflow execution regression (#873)."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import pytest

from fichero.db import Database
from fichero.knowledge_models import KnowledgeClaim
from fichero.models import Artifact, DocType, Document, FileType, Workflow
from fichero.workflows.default_workflows import _load_preset_files

from tests.unit.workflows.test_default_workflow_e2e_harness import (
    _install_deterministic_workflow_stubs,
)


TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


def test_terminal_status_helper_treats_only_exited_states_as_done() -> None:
    assert _terminal_status({"status": "completed"}) == "completed"
    assert _terminal_status({"status": "failed"}) == "failed"
    assert _terminal_status({"status": "running"}) is None
    assert _terminal_status({"state": "done"}) == "completed"


def test_json_parse_failure_detector_checks_nested_payloads() -> None:
    assert _has_json_parse_failure({"log": ["ok", {"message": "JSON parse failed"}]})
    assert not _has_json_parse_failure({"log": ["ok", {"message": "parsed"}]})


def test_catalogue_workflow_execution_api_e2e(
    client,
    db: Database,
    test_package: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run Catalogue through the API thread path against a small PDF fixture.

    This is skipped by default because the real version can use live OCR/LLM
    providers. The deterministic stubs keep the local verification path cheap
    when explicitly enabled with FICHERO_INTEGRATION=1.
    """

    if os.environ.get("FICHERO_INTEGRATION") != "1":
        pytest.skip("set FICHERO_INTEGRATION=1 to run workflow execution E2E")

    _install_deterministic_workflow_stubs(monkeypatch)
    workflow, expected_node_ids = _save_catalogue_workflow(db)
    parent_doc_id, page_doc_ids = _seed_spanish_pdf_pages(db, tmp_path)
    before_claims = len(db.all(KnowledgeClaim))

    response = client.post(
        "/api/workflow-execution/execute",
        json={
            "workflow_id": workflow.id,
            "inputs": {"selected_doc_ids": [parent_doc_id]},
            "skip_cache": True,
        },
    )
    assert response.status_code == 202, response.text
    thread_id = response.json()["thread_id"]

    status = _poll_terminal_status(client, thread_id)
    assert status["status"] == "completed", status
    assert not status.get("error")
    assert not _has_json_parse_failure(status)

    current_state = status.get("current_state") or {}
    completed_nodes = set(current_state.get("completed_nodes") or [])
    assert expected_node_ids <= completed_nodes

    catalogue_artifacts = db.query(Artifact, artifact_type="catalogue.narrative")
    assert any(
        artifact.document_id == parent_doc_id and (artifact.content or artifact.text or "")
        for artifact in catalogue_artifacts
    )

    parent_doc = db.get(Document, parent_doc_id)
    assert parent_doc is not None
    assert parent_doc.page_content == "Catalogue narrative for the regression fixture."

    for page_doc_id in page_doc_ids:
        assert db.query(KnowledgeClaim, source_document_id=page_doc_id)

    assert len(db.all(KnowledgeClaim)) > before_claims
    assert Path(test_package).name.endswith(".fichero")


def _save_catalogue_workflow(db: Database) -> tuple[Workflow, set[str]]:
    preset = next(p for p in _load_preset_files() if p["name"] == "Catalogue")
    workflow = Workflow(
        id="catalogue-api-e2e-873",
        name=preset["name"],
        description=preset.get("description", ""),
        nodes=preset["nodes"],
        edges=preset["edges"],
        config=preset.get("config", {}),
        folder_path=preset.get("folder_path", "/"),
    )
    db.save(workflow)
    return workflow, {str(node["id"]) for node in preset["nodes"]}


def _seed_spanish_pdf_pages(db: Database, tmp_path: Path) -> tuple[str, list[str]]:
    fixture_pdf = (
        Path(__file__).resolve().parents[1] / "fixtures" / "sample_files" / "sample.pdf"
    )
    assert fixture_pdf.exists(), f"missing fixture PDF: {fixture_pdf}"
    pdf_path = tmp_path / "catalogue-spanish-873.pdf"
    pdf_path.write_bytes(fixture_pdf.read_bytes())

    parent = Document(
        id="catalogue-spanish-873",
        name="Catalogue Spanish fixture",
        path=str(pdf_path),
        doc_type=DocType.file,
        file_type=FileType.pdf,
    )
    page_texts = [
        "La persona de regresion firmo el acta en Madrid en 1842.",
        "El archivo menciona a la familia y el lugar de origen.",
        "La narracion final debe conservar las afirmaciones por pagina.",
    ]
    pages = [
        Document(
            id=f"catalogue-spanish-873-page-{index}",
            parent_id=parent.id,
            name=f"Catalogue Spanish fixture p. {index}",
            doc_type=DocType.page,
            sequence=index,
            page_content=text,
            metadata={
                "page_number": index,
                "transcription": text,
                "text_length": len(text),
            },
        )
        for index, text in enumerate(page_texts, start=1)
    ]
    db.save(parent)
    for page in pages:
        db.save(page)
    return parent.id, [page.id for page in pages]


def _poll_terminal_status(client, thread_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 60
    last_status: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        response = client.get(f"/api/workflow-execution/threads/{thread_id}/status")
        if response.status_code == 404:
            time.sleep(0.25)
            continue
        assert response.status_code == 200, response.text
        last_status = response.json()
        if _terminal_status(last_status):
            return last_status
        time.sleep(0.25)
    pytest.fail(f"workflow did not finish: {last_status}")


def _terminal_status(status: dict[str, Any]) -> str | None:
    value = status.get("status") or status.get("state")
    if value == "done":
        value = "completed"
    return value if value in TERMINAL_STATUSES else None


def _has_json_parse_failure(payload: Any) -> bool:
    if isinstance(payload, str):
        normalized = payload.lower()
        return "json" in normalized and "parse" in normalized and "fail" in normalized
    if isinstance(payload, dict):
        return any(_has_json_parse_failure(value) for value in payload.values())
    if isinstance(payload, list | tuple):
        return any(_has_json_parse_failure(value) for value in payload)
    return False
