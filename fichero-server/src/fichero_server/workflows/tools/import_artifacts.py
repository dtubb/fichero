"""Register step-1 import artifacts for already-imported documents.

This workflow node is the first discrete stage of the reviewable import
pipeline: create the lightweight per-page artifacts that the importer already
knows how to express (`import_receipt` + `transcription`) and stop there.

It intentionally does NOT extract entities, write KG rows, or create later
catalogue artifacts. Those belong to follow-up stages under #1757.
"""

from __future__ import annotations

import logging
from typing import Any

from fichero_server.db import db_manager
from fichero_server.importers.manifest_import import (
    CANONICAL_VERSION,
    _import_receipt_content,
    _import_receipt_data,
)
from fichero_server.models import Artifact, Document
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.tools.progress import emit_progress_event
from fichero_server.workflows.tools.sources import files_tool
from fichero_server.workflows.types import DataType, PortDef, State
from fichero_server.llm import LLMConfig
from fichero_server.workflows.tools._workflow_change_emit import (
    emit_workflow_artifact_changes,
)

logger = logging.getLogger(__name__)

_ARTIFACT_TYPES = ("import_receipt", "transcription")


def _coerce_documents(raw_documents: list[Any], db, library_path: str) -> list[Document]:
    """Resolve workflow document payloads back to live Document rows."""
    documents: list[Document] = []
    seen: set[str] = set()

    for item in raw_documents:
        document_id = item.get("id") if isinstance(item, dict) else str(item or "")
        if not document_id or document_id in seen:
            continue
        document = db.get(Document, document_id)
        if document is None:
            logger.warning(
                "import_artifacts: selected document %s missing in %s",
                document_id,
                library_path,
            )
            continue
        seen.add(document_id)
        documents.append(document)

    return documents


def _receipt_node(document: Document) -> dict[str, Any]:
    metadata = dict(document.metadata or {})
    page_label = metadata.get("page_label")
    if page_label is None and metadata.get("page_number") is not None:
        page_label = str(metadata["page_number"])
    if page_label is None and document.sequence is not None:
        page_label = str(document.sequence)

    return {
        "name": document.name,
        "external_id": metadata.get("canonical_external_id") or document.id,
        "page_label": page_label,
        "canonical_version": metadata.get("canonical_version") or CANONICAL_VERSION,
        "images": metadata.get("images") or [],
    }


def _transcription_text(document: Document) -> str:
    if isinstance(document.page_content, str) and document.page_content.strip():
        return document.page_content.strip()
    metadata = document.metadata or {}
    transcription = metadata.get("transcription")
    if isinstance(transcription, str):
        return transcription.strip()
    return ""


@register_tool(
    name="import_artifacts",
    display_name="Import Artifacts",
    description="Register import-receipt and transcription artifacts only",
    category="utility",
    icon="square.and.arrow.down.on.square",
    color="green",
    uses_llm=False,
    supports_batch=False,
    input_ports=[
        PortDef(
            id="documents",
            name="Documents",
            port_type="input",
            data_type=DataType.JSON,
            required=False,
            description="Selected document metadata, typically from Files.documents",
        ),
    ],
    output_ports=[
        PortDef(
            id="summary",
            name="Summary",
            port_type="output",
            data_type=DataType.JSON,
            description="Created/skipped artifact counts",
        ),
        PortDef(
            id="count",
            name="Count",
            port_type="output",
            data_type=DataType.NUMBER,
            description="Number of selected atomic documents processed",
        ),
    ],
    sort_order=35,
)
async def import_artifacts(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Create the step-1 artifacts on selected page/file documents."""
    del llm_config  # workflow stage is deterministic and non-LLM

    library_path = state.get("library_path", "")
    if not library_path:
        return {
            "summary": {
                "documents_processed": 0,
                "artifacts_created": 0,
                "artifacts_skipped": 0,
            },
            "count": 0,
        }

    db = db_manager.get_database(library_path)
    raw_documents = list(inputs.get("documents") or [])
    if not raw_documents:
        fallback = await files_tool(
            inputs={},
            state=state,
            llm_config=LLMConfig(provider="", model=""),
        )
        raw_documents = list(fallback.get("documents") or [])

    documents = _coerce_documents(raw_documents, db, library_path)
    if not documents:
        return {
            "summary": {
                "documents_processed": 0,
                "artifacts_created": 0,
                "artifacts_skipped": 0,
            },
            "count": 0,
        }

    doc_ids = {document.id for document in documents}
    existing_keys = {
        (artifact.document_id, artifact.artifact_type)
        for artifact in db.query(Artifact)
        if artifact.document_id in doc_ids and artifact.artifact_type in _ARTIFACT_TYPES
    }

    progress_callback = inputs.get("__progress_callback")
    created = 0
    skipped = 0
    created_artifact_ids: list[str] = []
    created_document_ids: set[str] = set()

    for index, document in enumerate(documents, start=1):
        await emit_progress_event(
            progress_callback,
            "file_start",
            "",
            f"Import Artifacts {document.name}",
            index,
            len(documents),
            message=f"Registering step-1 artifacts for {document.name}",
        )

        receipt_node = _receipt_node(document)
        receipt_key = (document.id, "import_receipt")
        if receipt_key in existing_keys:
            skipped += 1
        else:
            artifact = Artifact(
                document_id=document.id,
                artifact_type="import_receipt",
                content=_import_receipt_content(receipt_node),
                data=_import_receipt_data(receipt_node),
                provider="manifest-importer",
                model=CANONICAL_VERSION,
                step_name="import_artifacts",
                run_id=state.get("task_id"),
                confidence=1.0,
            )
            db.save(artifact)
            created_artifact_ids.append(artifact.id)
            created_document_ids.add(document.id)
            existing_keys.add(receipt_key)
            created += 1

        transcription = _transcription_text(document)
        if transcription:
            transcription_key = (document.id, "transcription")
            if transcription_key in existing_keys:
                skipped += 1
            else:
                db.save(
                    artifact := Artifact(
                        document_id=document.id,
                        artifact_type="transcription",
                        content=transcription,
                        data={
                            "source": "manifest-import",
                            "external_id": receipt_node["external_id"],
                            "page_label": receipt_node["page_label"],
                        },
                        provider="manifest-importer",
                        model=CANONICAL_VERSION,
                        step_name="import_artifacts",
                        run_id=state.get("task_id"),
                        confidence=1.0,
                    )
                )
                created_artifact_ids.append(artifact.id)
                created_document_ids.add(document.id)
                existing_keys.add(transcription_key)
                created += 1

        await emit_progress_event(
            progress_callback,
            "file_complete",
            "",
            f"Import Artifacts {document.name}",
            index,
            len(documents),
            message=f"Registered step-1 artifacts for {document.name}",
        )

    # Artifact writes above are direct + already durable, serialized on the
    # single per-package connection lock (#2508/#2514) — no queue to flush.
    if created_artifact_ids:
        emit_workflow_artifact_changes(
            str(db.path.parent),
            artifact_ids=created_artifact_ids,
            document_ids=created_document_ids,
        )
    summary = {
        "documents_processed": len(documents),
        "artifacts_created": created,
        "artifacts_skipped": skipped,
    }
    return {"summary": summary, "count": len(documents)}
