from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

from fichero_server.api.change_stream import emit_change

logger = logging.getLogger(__name__)


def _dedupe_ids(raw_ids: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for raw_id in raw_ids:
        value = str(raw_id or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def emit_workflow_kg_changes(
    library_path: str,
    *,
    entity_ids: Iterable[str] = (),
    claim_ids: Iterable[str] = (),
    document_ids: Iterable[str] = (),
) -> None:
    try:
        entity_ids_list = _dedupe_ids(entity_ids)
        claim_ids_list = _dedupe_ids(claim_ids)
        document_ids_list = _dedupe_ids(document_ids)
        emit_change(
            library_path,
            type="entity.updated",
            entity_ids=entity_ids_list,
            actor="workflow",
        )
        emit_change(
            library_path,
            type="claim.updated",
            claim_ids=claim_ids_list,
            actor="workflow",
        )
        if document_ids_list:
            emit_change(
                library_path,
                type="document.updated",
                document_ids=document_ids_list,
                actor="workflow",
            )
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("workflow KG emit failed (best-effort, ignored): %s", exc)


def emit_workflow_kg_changes_for_db(
    db,
    *,
    entity_ids: Iterable[str] = (),
    claim_ids: Iterable[str] = (),
    document_ids: Iterable[str] = (),
) -> None:
    library_path = ""
    try:
        library_path = str(Path(db.path).parent)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("workflow KG emit could not resolve library path: %s", exc)
    emit_workflow_kg_changes(
        library_path,
        entity_ids=entity_ids,
        claim_ids=claim_ids,
        document_ids=document_ids,
    )


def emit_workflow_artifact_changes(
    library_path: str,
    *,
    artifact_ids: Iterable[str] = (),
    document_ids: Iterable[str] = (),
    actor: str = "workflow",
    change_type: str = "created",
) -> None:
    try:
        artifact_ids_list = _dedupe_ids(artifact_ids)
        if not artifact_ids_list:
            return
        emit_change(
            library_path,
            type=f"artifact.{change_type}",
            artifact_ids=artifact_ids_list,
            document_ids=_dedupe_ids(document_ids),
            actor=actor,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("workflow artifact emit failed (best-effort, ignored): %s", exc)


def emit_workflow_artifact_changes_for_db(
    db,
    *,
    artifact_ids: Iterable[str] = (),
    document_ids: Iterable[str] = (),
    actor: str = "workflow",
    change_type: str = "created",
) -> None:
    library_path = ""
    try:
        library_path = str(Path(db.path).parent)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug(
            "workflow artifact emit could not resolve library path: %s", exc,
        )
    emit_workflow_artifact_changes(
        library_path,
        artifact_ids=artifact_ids,
        document_ids=document_ids,
        actor=actor,
        change_type=change_type,
    )


def emit_workflow_citation_changes(
    library_path: str,
    *,
    citation_ids: Iterable[str] = (),
    document_ids: Iterable[str] = (),
    actor: str = "workflow",
    change_type: str = "created",
) -> None:
    try:
        citation_ids_list = _dedupe_ids(citation_ids)
        if not citation_ids_list:
            # Document-scoped refresh still works; IDs are optional by contract.
            emit_change(
                library_path,
                type=f"citation.{change_type}",
                citation_ids=[],
                document_ids=_dedupe_ids(document_ids),
                actor=actor,
            )
            return
        emit_change(
            library_path,
            type=f"citation.{change_type}",
            citation_ids=citation_ids_list,
            document_ids=_dedupe_ids(document_ids),
            actor=actor,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("workflow citation emit failed (best-effort, ignored): %s", exc)


def emit_workflow_citation_changes_for_db(
    db,
    *,
    citation_ids: Iterable[str] = (),
    document_ids: Iterable[str] = (),
    actor: str = "workflow",
    change_type: str = "created",
) -> None:
    library_path = ""
    try:
        library_path = str(Path(db.path).parent)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug(
            "workflow citation emit could not resolve library path: %s", exc,
        )
    emit_workflow_citation_changes(
        library_path,
        citation_ids=citation_ids,
        document_ids=document_ids,
        actor=actor,
        change_type=change_type,
    )
