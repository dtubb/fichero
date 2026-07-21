"""Sources API - Canonical FastAPI routes for knowledge sources.

This module implements the "sources" route surface requested in issue #364.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from fichero.actions.registry import ActionContext, registry
from fichero.api.auth import action_context
from fichero.api.library_header import require_library_path
from fichero.api.main import get_library_database, get_library_database_for_write
from fichero.db import Database
from fichero.models import Document
from fichero.models import SourceListResponse

router = APIRouter(tags=["sources"])

_SOURCE_METADATA_FLAG = "_fichero_source"


class SourceUpsertRequest(BaseModel):
    """Request to create or update a source document."""

    id: str | None = None
    title: str
    file_path: str
    document_type: str = "source"
    metadata: dict = Field(default_factory=dict)


class SourceUpsertResponse(BaseModel):
    """Response after upserting or reading a source document."""

    id: str
    title: str
    file_path: str
    document_type: str
    metadata: dict


def _is_source_document(document: Document) -> bool:
    return bool(document.metadata.get(_SOURCE_METADATA_FLAG))


def _to_response(document: Document) -> SourceUpsertResponse:
    metadata = dict(document.metadata)
    metadata.pop(_SOURCE_METADATA_FLAG, None)
    return SourceUpsertResponse(
        id=document.id,
        title=document.name,
        file_path=document.path or "",
        document_type="source",
        metadata=metadata,
    )


def _build_source_metadata(metadata: dict) -> dict:
    source_metadata = dict(metadata)
    source_metadata[_SOURCE_METADATA_FLAG] = True
    return source_metadata


def _upsert_source_impl(
    db: Database, request: SourceUpsertRequest
) -> tuple[Document, dict[str, Any]]:
    """Create or update a source document — the proven body of ``POST /sources``,
    extracted so BOTH the route and the ``source.upsert`` action drive the same
    code (iterate-not-replace). Returns ``(document, before)`` where ``before``
    captures whether the row pre-existed and its prior snapshot (the undo
    payload: a fresh create undoes to a delete, an update undoes to a restore).
    Raises ``HTTPException(400)`` on a non-source ``document_type``."""
    if request.document_type != "source":
        raise HTTPException(status_code=400, detail="document_type must be 'source'")

    document = db.get(Document, request.id) if request.id else None
    before: dict[str, Any] = {
        "existed": document is not None,
        "document": document.model_dump(mode="json") if document is not None else None,
    }
    if document is None:
        kwargs = {
            "name": request.title.strip(),
            "path": request.file_path.strip(),
            "metadata": _build_source_metadata(request.metadata),
        }
        if request.id:
            kwargs["id"] = request.id
        document = Document(**kwargs)
    else:
        document.name = request.title.strip()
        document.path = request.file_path.strip()
        document.metadata = _build_source_metadata(request.metadata)

    db.save(document)
    return document, before


def _update_source_impl(
    db: Database, source_id: str, request: SourceUpsertRequest
) -> tuple[Document, dict[str, Any]]:
    """Update an existing source — the proven body of ``PUT /sources/{id}``,
    extracted for reuse by the ``source.update`` action. Returns
    ``(document, before_snapshot)``. Raises ``HTTPException`` (400 non-source
    type / not-a-source, 404 unknown id)."""
    if request.document_type != "source":
        raise HTTPException(status_code=400, detail="document_type must be 'source'")

    document = db.get(Document, source_id)
    if document is None:
        raise HTTPException(status_code=404, detail=f"Source not found: {source_id}")
    if not _is_source_document(document):
        raise HTTPException(status_code=400, detail=f"Document is not a source: {source_id}")

    before = document.model_dump(mode="json")
    document.name = request.title.strip()
    document.path = request.file_path.strip()
    document.metadata = _build_source_metadata(request.metadata)
    db.save(document)
    return document, before


def _delete_source_impl(db: Database, source_id: str) -> dict[str, Any]:
    """Delete a source — the proven body of ``DELETE /sources/{id}``, extracted
    for reuse by the ``source.delete`` action. Returns the deleted Document's
    snapshot (the undo payload). Raises ``HTTPException`` (400 not-a-source,
    404 unknown id)."""
    document = db.get(Document, source_id)
    if document is None:
        raise HTTPException(status_code=404, detail=f"Source not found: {source_id}")
    if not _is_source_document(document):
        raise HTTPException(status_code=400, detail=f"Document is not a source: {source_id}")
    before = document.model_dump(mode="json")
    db.delete(document)
    return before


def _restore_source_impl(db: Database, payload: dict[str, Any]) -> Document:
    """Re-create a source Document from a prior snapshot — the generic inverse
    for source.upsert (update branch), source.update, and source.delete undo."""
    document = Document(**payload)
    db.save(document)
    return document


def _resolve_action_ctx(
    ctx: ActionContext | object,
    *,
    library_path: str | object | None = None,
) -> ActionContext:
    if isinstance(ctx, ActionContext):
        return ctx
    return ActionContext(
        library_path=library_path if isinstance(library_path, str) else None
    )


@router.post("", response_model=SourceUpsertResponse)
async def upsert_source(
    request: SourceUpsertRequest,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str | object = Depends(require_library_path),
    ctx: ActionContext | object = Depends(action_context),
) -> SourceUpsertResponse:
    """Create or update a source (stored as a Document)."""
    ctx = _resolve_action_ctx(ctx, library_path=x_fichero_library_path)
    result = registry.invoke(
        db,
        "source.upsert",
        request.model_dump(mode="json"),
        ctx,
    )
    return SourceUpsertResponse.model_validate(result.result)


@router.get("", response_model=SourceListResponse)
async def list_sources(
    db: Database = Depends(get_library_database),
) -> SourceListResponse:
    """List all source documents."""
    sources = [_to_response(d) for d in db.all(Document) if _is_source_document(d)]
    return SourceListResponse(items=sources, count=len(sources))


@router.get("/{source_id}", response_model=SourceUpsertResponse)
async def get_source(
    source_id: str,
    db: Database = Depends(get_library_database),
) -> SourceUpsertResponse:
    """Get a specific source."""
    document = db.get(Document, source_id)
    if document is None:
        raise HTTPException(status_code=404, detail=f"Source not found: {source_id}")
    if not _is_source_document(document):
        raise HTTPException(status_code=400, detail=f"Document is not a source: {source_id}")
    return _to_response(document)


@router.put("/{source_id}", response_model=SourceUpsertResponse)
async def update_source(
    source_id: str,
    request: SourceUpsertRequest,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str | object = Depends(require_library_path),
    ctx: ActionContext | object = Depends(action_context),
) -> SourceUpsertResponse:
    """Update an existing source."""
    ctx = _resolve_action_ctx(ctx, library_path=x_fichero_library_path)
    result = registry.invoke(
        db,
        "source.update",
        {
            "source_id": source_id,
            **request.model_dump(mode="json"),
        },
        ctx,
    )
    return SourceUpsertResponse.model_validate(result.result)


@router.delete("/{source_id}", status_code=204)
async def delete_source(
    source_id: str,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str | object = Depends(require_library_path),
    ctx: ActionContext | object = Depends(action_context),
) -> None:
    """Delete a source."""
    ctx = _resolve_action_ctx(ctx, library_path=x_fichero_library_path)
    registry.invoke(
        db,
        "source.delete",
        {"source_id": source_id},
        ctx,
    )


# ---------------------------------------------------------------------------
# Action layer registration (EPIC #1848 sweep #2014) — source mutations
# ---------------------------------------------------------------------------
#
# Sources are Documents flagged `_fichero_source`, so the touched ids are
# document_ids. Each action WRAPS the proven `_impl` above (iterate-not-replace)
# and routes through `registry.invoke` for the generic ActionAudit + a typed
# `source.updated` / `source.deleted` change event. Undo uses the before-snapshot
# in the ChangeSpec: a *created* upsert undoes to `source.delete`; an *updated*
# upsert / update / delete undoes to the generic `source.restore`.

from fichero.actions.registry import action, ChangeSpec  # noqa: E402


class SourceUpdateActionParams(SourceUpsertRequest):
    """Params for source.update — PUT target id + the upsert fields."""

    source_id: str = Field(description="Source (document) id to update")


class SourceDeleteActionParams(BaseModel):
    """Params for source.delete."""

    source_id: str = Field(description="Source (document) id to delete")


class SourceRestoreActionParams(BaseModel):
    """Params for source.restore — re-create a source Document from a snapshot."""

    payload: dict[str, Any] = Field(description="Full Document row snapshot to restore")


def _invert_upsert(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    """Inverse of source.upsert: a fresh create -> delete; an update -> restore."""
    if not before:
        return None
    if before.get("existed"):
        prior = before.get("document")
        if not prior:
            return None
        return ("source.restore", {"payload": prior})
    # Created brand-new -> undo by deleting the new id (captured in after).
    if not after:
        return None
    new_id = after.get("source_id")
    if not new_id:
        return None
    return ("source.delete", {"source_id": new_id})


def _invert_source_to_restore(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    """Inverse of source.update / source.delete: restore the prior snapshot."""
    if not before:
        return None
    return ("source.restore", {"payload": before})


@action(
    "source.upsert",
    SourceUpsertRequest,
    domains=["source", "document"],
    undoable=True,
    invert=_invert_upsert,
)
def _action_upsert_source(
    db: Database, params: SourceUpsertRequest, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    document, before = _upsert_source_impl(db, params)
    spec = ChangeSpec(
        domains=["source", "document"],
        target_ids=[document.id],
        before=before,
        after={"source_id": document.id},
        emit_type="source.updated",
        document_ids=[document.id],
    )
    return _to_response(document).model_dump(mode="json"), spec


@action(
    "source.update",
    SourceUpdateActionParams,
    domains=["source", "document"],
    undoable=True,
    invert=_invert_source_to_restore,
)
def _action_update_source(
    db: Database, params: SourceUpdateActionParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    # SourceUpdateActionParams IS-A SourceUpsertRequest — pass it straight through.
    document, before = _update_source_impl(db, params.source_id, params)
    spec = ChangeSpec(
        domains=["source", "document"],
        target_ids=[document.id],
        before=before,
        after=_to_response(document).model_dump(mode="json"),
        emit_type="source.updated",
        document_ids=[document.id],
    )
    return _to_response(document).model_dump(mode="json"), spec


@action(
    "source.delete",
    SourceDeleteActionParams,
    domains=["source", "document"],
    undoable=True,
    invert=_invert_source_to_restore,
)
def _action_delete_source(
    db: Database, params: SourceDeleteActionParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    before = _delete_source_impl(db, params.source_id)
    spec = ChangeSpec(
        domains=["source", "document"],
        target_ids=[params.source_id],
        before=before,
        after=None,
        emit_type="source.deleted",
        document_ids=[params.source_id],
    )
    return {"status": "deleted", "source_id": params.source_id}, spec


@action(
    "source.restore",
    SourceRestoreActionParams,
    domains=["source", "document"],
    undoable=False,
)
def _action_restore_source(
    db: Database, params: SourceRestoreActionParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    document = _restore_source_impl(db, params.payload)
    spec = ChangeSpec(
        domains=["source", "document"],
        target_ids=[document.id],
        before=None,
        after=_to_response(document).model_dump(mode="json"),
        emit_type="source.updated",
        document_ids=[document.id],
    )
    return _to_response(document).model_dump(mode="json"), spec
