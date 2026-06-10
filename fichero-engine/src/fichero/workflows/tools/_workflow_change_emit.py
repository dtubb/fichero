from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

from fichero.api.change_stream import emit_change

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
) -> None:
    try:
        entity_ids_list = _dedupe_ids(entity_ids)
        claim_ids_list = _dedupe_ids(claim_ids)
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
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("workflow KG emit failed (best-effort, ignored): %s", exc)


def emit_workflow_kg_changes_for_db(
    db,
    *,
    entity_ids: Iterable[str] = (),
    claim_ids: Iterable[str] = (),
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
    )
