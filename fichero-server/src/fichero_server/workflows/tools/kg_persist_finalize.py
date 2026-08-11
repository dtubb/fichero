"""Register step-5 KG finalize for already-extracted KG rows.

This final reviewable workflow stage reuses the existing KG finalize paths
instead of inventing new persistence:

- ``fichero_server.knowledge.triangulation.persist_support_counts`` recomputes and persists
  cross-source corroboration counts onto claims.
- ``Database.embed_entities`` / ``Database.embed_claims`` backfill the
  canonical LanceDB embedding tables when they are missing or stale by row
  count.
- ``fichero_server.knowledge.rebuild.rebuild_kg(..., triples=True)`` refreshes ``kg.nt``
  when the graph snapshot is missing or triangulation changed claim state.

Steps 2-4 already persist entities and claims through the canonical writers, so
this stage stays intentionally conservative: it finalizes the derived KG state
that remains after raw claims exist.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fichero_server.db import db_manager
from fichero_server.db.embeddings import (
    KG_CLAIM_EMBEDDINGS_TABLE,
    KG_ENTITY_EMBEDDINGS_TABLE,
)
from fichero_server.knowledge.rebuild import rebuild_kg
from fichero_server.knowledge.triangulation import persist_support_counts
from fichero_server.models.knowledge import KnowledgeClaim, KnowledgeEntity
from fichero_server.llm import LLMConfig
from fichero_server.models import Document
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.tools._workflow_change_emit import emit_workflow_kg_changes
from fichero_server.workflows.tools.import_artifacts import _coerce_documents
from fichero_server.workflows.tools.progress import emit_progress_event
from fichero_server.workflows.tools.sources import files_tool
from fichero_server.workflows.types import DataType, PortDef, State

logger = logging.getLogger(__name__)


def _empty_summary() -> dict[str, int]:
    return {
        "documents_scoped": 0,
        "entities_total": 0,
        "claims_total": 0,
        "claims_updated": 0,
        "entity_vectors_indexed": 0,
        "claim_vectors_indexed": 0,
        "triples_written": 0,
    }


def _descendant_doc_ids(db, root_ids: list[str]) -> set[str]:
    queue = list(dict.fromkeys(root_ids))
    seen: set[str] = set()

    while queue:
        doc_id = queue.pop(0)
        if not doc_id or doc_id in seen:
            continue
        seen.add(doc_id)
        for child in db.query(Document, parent_id=doc_id):
            if child.id not in seen:
                queue.append(child.id)
    return seen


def _vector_row_count(db, table_name: str) -> int:
    # The ONLY legitimate "empty" case is a table that does not exist yet
    # (first run / never embedded). Gate on it explicitly and return 0.
    # Any OTHER failure must NOT collapse to 0: a transient error would look
    # like an empty vector store and silently trigger a full, expensive KG
    # re-embed of every entity and claim (#2512). Log loudly and propagate.
    try:
        if table_name not in db._lance_tables():
            return 0
        return int(db.lance.open_table(table_name).count_rows())
    except Exception:
        logger.exception(
            "Failed to read vector row count for table %r; refusing to report "
            "0 (a silent 0 would trigger a full KG re-embed)",
            table_name,
        )
        raise


@register_tool(
    name="kg_persist_finalize",
    display_name="KG Persist / Finalize",
    description="Finalize corroboration counts, canonical KG embeddings, and graph snapshot from existing KG rows",
    category="utility",
    icon="point.3.connected.trianglepath.dotted",
    color="blue",
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
        PortDef(
            id="barrier",
            name="Barrier (sync)",
            port_type="input",
            data_type=DataType.ANY,
            required=False,
            description="Optional dependency-only input used by chained presets.",
        ),
    ],
    output_ports=[
        PortDef(
            id="summary",
            name="Summary",
            port_type="output",
            data_type=DataType.JSON,
            description="Finalize counts for triangulation, embeddings, and graph refresh",
        ),
        PortDef(
            id="count",
            name="Count",
            port_type="output",
            data_type=DataType.NUMBER,
            description="Number of scoped documents",
        ),
    ],
    sort_order=39,
)
async def kg_persist_finalize(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Finalize derived KG state for the current library."""
    del llm_config  # deterministic finalize stage

    library_path = state.get("library_path", "")
    if not library_path:
        return {"summary": _empty_summary(), "count": 0}

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
        return {"summary": _empty_summary(), "count": 0}

    scoped_doc_ids = _descendant_doc_ids(db, [document.id for document in documents])
    progress_callback = inputs.get("__progress_callback")

    summary = _empty_summary()
    summary["documents_scoped"] = len(scoped_doc_ids)

    await emit_progress_event(
        progress_callback,
        "file_start",
        "",
        "KG Persist / Finalize",
        1,
        3,
        message="Recomputing corroboration counts",
    )
    claims_updated = persist_support_counts(db)
    summary["claims_updated"] = claims_updated
    await emit_progress_event(
        progress_callback,
        "file_complete",
        "",
        "KG Persist / Finalize",
        1,
        3,
        message=f"Updated corroboration on {claims_updated} claim(s)",
    )

    entities = db.query(KnowledgeEntity)
    claims = db.query(KnowledgeClaim)
    summary["entities_total"] = len(entities)
    summary["claims_total"] = len(claims)

    await emit_progress_event(
        progress_callback,
        "file_start",
        "",
        "KG Embeddings",
        2,
        3,
        message="Refreshing canonical KG embeddings when needed",
    )
    if _vector_row_count(db, KG_ENTITY_EMBEDDINGS_TABLE) != len(entities):
        summary["entity_vectors_indexed"] = db.embed_entities(entities)
    if _vector_row_count(db, KG_CLAIM_EMBEDDINGS_TABLE) != len(claims):
        summary["claim_vectors_indexed"] = db.embed_claims(claims)
    await emit_progress_event(
        progress_callback,
        "file_complete",
        "",
        "KG Embeddings",
        2,
        3,
        message=(
            "KG embeddings finalized "
            f"(entities={summary['entity_vectors_indexed']}, claims={summary['claim_vectors_indexed']})"
        ),
    )

    await emit_progress_event(
        progress_callback,
        "file_start",
        "",
        "KG Graph",
        3,
        3,
        message="Refreshing kg.nt graph snapshot when needed",
    )
    kg_nt_path = Path(db.path).parent / "kg.nt"
    if claims_updated > 0 or not kg_nt_path.exists():
        rebuild_stats = rebuild_kg(db, vectors=False, triples=True, triples_path=kg_nt_path)
        summary["triples_written"] = rebuild_stats["triples_written"]
    await emit_progress_event(
        progress_callback,
        "file_complete",
        "",
        "KG Graph",
        3,
        3,
        message=f"KG graph finalized ({summary['triples_written']} triples written)",
    )

    # Broadcast the finalized KG to the library change-stream so the KG/entity/
    # claim views refresh live, not on next reload (#2518 — finalize previously
    # emitted only to the per-run PROGRESS stream, never to the library change
    # hub). Best-effort: a broadcast failure must never fail the run. entity/claim
    # ids are the finalized library scope (already queried above for embeddings).
    try:
        emit_workflow_kg_changes(
            str(db.path.parent),
            entity_ids=[e.id for e in entities if getattr(e, "id", None)],
            claim_ids=[c.id for c in claims if getattr(c, "id", None)],
            document_ids=sorted(scoped_doc_ids),
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "kg_persist_finalize: change-stream emit failed "
            "(KG persisted; UI will refresh on reload): %s",
            exc,
        )

    return {"summary": summary, "count": len(scoped_doc_ids)}
