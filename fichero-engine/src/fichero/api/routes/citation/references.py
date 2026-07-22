"""Backend API for first-class bibliographic references (#1103, stage A)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
import re

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from fichero.actions.registry import ActionContext, registry
from fichero.api.auth import action_context, request_actor
from fichero.api.library_header import require_library_path
from fichero.api.main import get_library_database, get_library_database_for_write
from fichero.db import Database
from fichero.models.knowledge import (
    Reference,
    ReferenceKind,
    ReferenceProvenance,
    ReferenceStatus,
    ReferenceVerificationSource,
    SourceMetadata,
)
from fichero.models import (
    Document,
    DocumentCitationsResponse,
    ReferenceListResponse,
    ReferenceWithProvenanceResponse,
)

router = APIRouter()


class DeletedResponse(BaseModel):
    """Standard delete envelope."""

    status: str = "deleted"


class ReferencePatchRequest(BaseModel):
    """Patch request for a reference row."""

    bibtex: str | None = None
    authors: list[str] | None = None
    title: str | None = None
    year: int | None = None
    kind: ReferenceKind | None = None
    journal_or_book: str | None = None
    publisher: str | None = None
    doi: str | None = None
    isbn: str | None = None
    pages: str | None = None
    language: str | None = None
    verification_score: float | None = Field(default=None, ge=0.0, le=1.0)
    verification_source: ReferenceVerificationSource | None = None
    verified_at: datetime | None = None
    realized_as_document_id: str | None = None
    notes: str | None = None
    tags: list[str] | None = None
    status: ReferenceStatus | None = None
    metadata: dict[str, Any] | None = None


def _resolve_action_ctx(
    ctx: ActionContext | object,
    *,
    actor: str | object = "system",
    library_path: str | object | None = None,
    origin_window: str | object | None = None,
) -> ActionContext:
    if isinstance(ctx, ActionContext):
        return ctx
    return ActionContext(
        actor=actor if isinstance(actor, str) else "system",
        library_path=library_path if isinstance(library_path, str) else None,
        origin_window=origin_window if isinstance(origin_window, str) else None,
    )


def _year_from_text(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"(\d{4})", value)
    return int(match.group(1)) if match else None


def _reference_from_document(document: Document) -> Reference:
    source_metadata = document.__dict__.get("source_metadata")
    meta = None
    if isinstance(source_metadata, dict):
        try:
            meta = SourceMetadata(**source_metadata)
        except Exception:
            meta = None

    is_article = bool(meta and meta.journal)
    is_book = bool(meta and meta.publisher and not meta.journal)

    payload: dict[str, Any] = {
        "title": (meta.title if meta and meta.title else document.name),
        "authors": meta.authors if meta else [],
        "year": _year_from_text(meta.date if meta else None),
        "kind": ReferenceKind.article
        if is_article
        else ReferenceKind.book
        if is_book
        else ReferenceKind.misc,
        "journal_or_book": (
            meta.journal
            if meta and meta.journal
            else meta.publisher
            if meta and meta.publisher
            else None
        ),
        "publisher": meta.publisher if meta else None,
        "doi": meta.doi if meta else None,
        "isbn": (meta.isbn_13 or meta.isbn_10) if meta else None,
        "pages": meta.pages if meta else None,
        "language": meta.language if meta else None,
        "bibtex": meta.bibtex if meta and meta.bibtex else "",
        "realized_as_document_id": document.id,
        "status": ReferenceStatus.verified
        if meta and (meta.bibtex or meta.title)
        else ReferenceStatus.to_find,
        "metadata": {
            "document_id": document.id,
            "document_name": document.name,
            "document_source_type": document.source_type,
        },
    }
    return Reference(**payload)


def _matches_query(reference: Reference, query: str) -> bool:
    haystack = " ".join(
        part
        for part in [
            reference.bibtex,
            " ".join(reference.authors),
            reference.title,
            reference.journal_or_book or "",
            reference.publisher or "",
            reference.doi or "",
            reference.isbn or "",
            reference.pages or "",
            reference.language or "",
            reference.notes or "",
            " ".join(reference.tags),
        ]
        if part
    ).lower()
    return query.lower() in haystack


def _reference_query(
    db: Database,
    *,
    q: str | None = None,
    status: ReferenceStatus | None = None,
    kind: ReferenceKind | None = None,
    verified: bool | None = None,
    unbacked: bool | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
) -> list[Reference]:
    # Push equality filters into the DB query to avoid whole-table scans (#3256).
    # Range predicates (year_from/year_to, verified, unbacked) and the free-text
    # search (q) stay in Python but operate on a much smaller result set.
    filters: dict[str, Any] = {}
    if status is not None:
        filters["status"] = status
    if kind is not None:
        filters["kind"] = kind
    refs = db.query(Reference, **filters) if filters else db.all(Reference)
    # Sort after filter push-down (same order as before).
    refs = sorted(
        refs,
        key=lambda ref: (ref.updated_at or ref.created_at, ref.id),
        reverse=True,
    )
    filtered: list[Reference] = []
    for reference in refs:
        if q and not _matches_query(reference, q):
            continue
        if verified is not None:
            is_verified = reference.verification_score is not None
            if verified != is_verified:
                continue
        if unbacked is not None:
            is_unbacked = reference.realized_as_document_id is None
            if unbacked != is_unbacked:
                continue
        if year_from is not None and (
            reference.year is None or reference.year < year_from
        ):
            continue
        if year_to is not None and (reference.year is None or reference.year > year_to):
            continue
        filtered.append(reference)
    return filtered


def _reference_provenance(db: Database, reference_id: str) -> list[ReferenceProvenance]:
    return sorted(
        db.query(ReferenceProvenance, reference_id=reference_id),
        key=lambda item: (item.created_at, item.id),
    )


def _document_citations(
    db: Database, document_id: str
) -> tuple[Reference, list[Reference], list[ReferenceProvenance]]:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    self_reference = _reference_from_document(document)
    links = sorted(
        db.query(ReferenceProvenance, document_id=document_id),
        key=lambda item: (item.created_at, item.id),
    )
    # Batch-lookup references instead of N+1 db.get calls (#3256).
    unique_ids = list({link.reference_id for link in links})
    if unique_ids:
        ref_map = {ref.id: ref for ref in db.query_in(Reference, "id", unique_ids)}
    else:
        ref_map: dict[str, Reference] = {}
    references: list[Reference] = []
    seen: set[str] = set()
    for link in links:
        if link.reference_id in seen:
            continue
        reference = ref_map.get(link.reference_id)
        if reference is None:
            continue
        seen.add(link.reference_id)
        references.append(reference)

    return self_reference, references, links


@router.get("/references")
async def list_references(
    q: str | None = Query(
        default=None, description="Free-text search over reference fields."
    ),
    status: ReferenceStatus | None = Query(default=None),
    kind: ReferenceKind | None = Query(default=None),
    verified: bool | None = Query(default=None),
    unbacked: bool | None = Query(default=None),
    year_from: int | None = Query(default=None, ge=0),
    year_to: int | None = Query(default=None, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Database = Depends(get_library_database),
) -> ReferenceListResponse:
    """List references with lightweight filtering."""

    items = _reference_query(
        db,
        q=q,
        status=status,
        kind=kind,
        verified=verified,
        unbacked=unbacked,
        year_from=year_from,
        year_to=year_to,
    )
    page = items[offset : offset + limit]
    return ReferenceListResponse(items=page, count=len(items))


@router.get("/references/{reference_id}")
async def get_reference(
    reference_id: str,
    db: Database = Depends(get_library_database),
) -> ReferenceWithProvenanceResponse:
    """Fetch one reference and its provenance rows."""

    reference = db.get(Reference, reference_id)
    if reference is None:
        raise HTTPException(status_code=404, detail="Reference not found")
    provenance = _reference_provenance(db, reference_id)
    return ReferenceWithProvenanceResponse(reference=reference, provenance=provenance)


def _patch_reference_impl(
    db: Database, reference_id: str, request: ReferencePatchRequest
) -> tuple[Reference, dict[str, Any]]:
    """Apply a patch to a reference row — the proven body of
    ``PATCH /references/{id}``, extracted so BOTH the route and the
    ``reference.patch`` action drive the same bibtex-reconciliation code
    (iterate-not-replace). Returns ``(updated_reference, before_payload)``;
    ``before_payload`` is the full prior row snapshot (the undo payload).
    Raises ``HTTPException(404)`` on unknown id."""
    existing = db.get(Reference, reference_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Reference not found")

    before = existing.model_dump(mode="json")
    updates = request.model_dump(exclude_unset=True)
    payload = existing.model_dump()
    payload["updated_at"] = datetime.now()

    if "bibtex" in updates and updates["bibtex"]:
        bibtex = updates.pop("bibtex")
        structural_keys = {
            "authors",
            "title",
            "year",
            "kind",
            "journal_or_book",
            "publisher",
            "doi",
            "isbn",
            "pages",
            "language",
        }
        payload.update({k: v for k, v in updates.items() if k not in structural_keys})
        parsed = Reference(bibtex=bibtex).model_dump()
        for key in structural_keys | {"bibtex"}:
            payload[key] = parsed[key]
    else:
        payload.update(updates)
        payload["bibtex"] = ""

    reference = Reference(**payload)
    db.save(reference)
    return reference, before


def _delete_reference_impl(db: Database, reference_id: str) -> dict[str, Any]:
    """Delete a reference once no provenance rows remain — the proven body of
    ``DELETE /references/{id}``, extracted so BOTH the route and the
    ``reference.delete`` action share the same guard + delete (iterate-not-
    replace). Returns the deleted row's snapshot (the undo payload). Raises
    ``HTTPException`` (404 unknown, 409 still-cited)."""
    reference = db.get(Reference, reference_id)
    if reference is None:
        raise HTTPException(status_code=404, detail="Reference not found")

    before = reference.model_dump(mode="json")
    provenance = _reference_provenance(db, reference_id)
    if provenance:
        citing_documents: list[dict[str, Any]] = []
        for link in provenance:
            document = db.get(Document, link.document_id)
            citing_documents.append(
                {
                    "document_id": link.document_id,
                    "document_name": document.name if document else None,
                    "page": link.page,
                    "citation_location": link.citation_location.value,
                }
            )
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Reference still has provenance rows.",
                "documents": citing_documents,
            },
        )

    db.delete(reference)
    return before


def _restore_reference_impl(db: Database, payload: dict[str, Any]) -> Reference:
    """Re-create a reference row from a prior snapshot — the generic inverse for
    both ``reference.patch`` and ``reference.delete`` undo. ``Reference``'s
    bibtex validator re-syncs on construction, so a snapshot round-trips."""
    reference = Reference(**payload)
    db.save(reference)
    return reference


@router.patch("/references/{reference_id}")
async def patch_reference(
    reference_id: str,
    request: ReferencePatchRequest,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str | object = Depends(require_library_path),
    x_fichero_origin_window: str | None = Header(
        default=None,
        alias="X-Fichero-Origin-Window",
    ),
    actor: str | object = Depends(request_actor),
    ctx: ActionContext | object = Depends(action_context),
) -> Reference:
    """Update a reference row."""
    ctx = _resolve_action_ctx(
        ctx,
        actor=actor,
        library_path=x_fichero_library_path,
        origin_window=x_fichero_origin_window,
    )
    result = registry.invoke(
        db,
        "reference.patch",
        {
            "reference_id": reference_id,
            "patch": request.model_dump(mode="json", exclude_unset=True),
        },
        ctx,
    )
    return Reference.model_validate(result.result)


@router.delete("/references/{reference_id}")
async def delete_reference(
    reference_id: str,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str | object = Depends(require_library_path),
    x_fichero_origin_window: str | None = Header(
        default=None,
        alias="X-Fichero-Origin-Window",
    ),
    actor: str | object = Depends(request_actor),
    ctx: ActionContext | object = Depends(action_context),
) -> DeletedResponse:
    """Delete a reference when no provenance rows remain."""
    ctx = _resolve_action_ctx(
        ctx,
        actor=actor,
        library_path=x_fichero_library_path,
        origin_window=x_fichero_origin_window,
    )
    registry.invoke(
        db,
        "reference.delete",
        {"reference_id": reference_id},
        ctx,
    )
    return DeletedResponse()


@router.get("/documents/{document_id}/citations")
async def get_document_citations(
    document_id: str,
    db: Database = Depends(get_library_database),
) -> DocumentCitationsResponse:
    """Return the document's own citation and the references it cites."""

    self_reference, references, links = _document_citations(db, document_id)
    return DocumentCitationsResponse(
        self=self_reference, references=references, links=links
    )


# ---------------------------------------------------------------------------
# Action layer registration (EPIC #1848 sweep #2014) — reference mutations
# ---------------------------------------------------------------------------
#
# reference.patch / reference.delete WRAP the proven `_impl`s above (iterate-not-
# replace) and route through `registry.invoke` for the generic ActionAudit + a
# typed `reference.updated` / `reference.deleted` change event. Both are
# undoable; their inverse re-creates the prior row via the generic
# `reference.restore` action — the before-snapshot in the ChangeSpec IS the undo
# payload. `reference.restore` is the leaf inverse (undoable=False): redo of a
# delete-undo is a fresh `reference.delete`, driven by the caller.
#
# Pure reads (list/get/document citations) persist nothing — no action needed.

from fichero.actions.registry import action, ChangeSpec  # noqa: E402


class ReferencePatchActionParams(BaseModel):
    """Params for reference.patch — target id + the patch fields."""

    reference_id: str = Field(description="Target reference id")
    patch: ReferencePatchRequest = Field(description="Fields to update")


class ReferenceDeleteActionParams(BaseModel):
    """Params for reference.delete."""

    reference_id: str = Field(description="Reference id to delete")


class ReferenceRestoreActionParams(BaseModel):
    """Params for reference.restore — re-create a row from a snapshot."""

    payload: dict[str, Any] = Field(
        description="Full Reference row snapshot to restore"
    )


def _invert_reference_to_restore(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    """Inverse of patch/delete: restore the prior reference snapshot."""
    if not before:
        return None
    return ("reference.restore", {"payload": before})


@action(
    "reference.patch",
    ReferencePatchActionParams,
    domains=["reference"],
    undoable=True,
    invert=_invert_reference_to_restore,
)
def _action_patch_reference(
    db: Database, params: ReferencePatchActionParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    reference, before = _patch_reference_impl(db, params.reference_id, params.patch)
    spec = ChangeSpec(
        domains=["reference"],
        target_ids=[reference.id],
        before=before,
        after=reference.model_dump(mode="json"),
        emit_type="reference.updated",
        reference_ids=[reference.id],
    )
    return reference.model_dump(mode="json"), spec


@action(
    "reference.delete",
    ReferenceDeleteActionParams,
    domains=["reference"],
    undoable=True,
    invert=_invert_reference_to_restore,
)
def _action_delete_reference(
    db: Database, params: ReferenceDeleteActionParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    before = _delete_reference_impl(db, params.reference_id)
    spec = ChangeSpec(
        domains=["reference"],
        target_ids=[params.reference_id],
        before=before,
        after=None,
        emit_type="reference.deleted",
        reference_ids=[params.reference_id],
    )
    return {"status": "deleted", "reference_id": params.reference_id}, spec


@action(
    "reference.restore",
    ReferenceRestoreActionParams,
    domains=["reference"],
    undoable=False,
)
def _action_restore_reference(
    db: Database, params: ReferenceRestoreActionParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    reference = _restore_reference_impl(db, params.payload)
    spec = ChangeSpec(
        domains=["reference"],
        target_ids=[reference.id],
        before=None,
        after=reference.model_dump(mode="json"),
        emit_type="reference.updated",
        reference_ids=[reference.id],
    )
    return reference.model_dump(mode="json"), spec
