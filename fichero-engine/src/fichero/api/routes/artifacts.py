"""
Artifact Routes

API endpoints for accessing processing artifacts (transcriptions, summaries, entities, etc.)
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fichero.actions.registry import ActionContext, ChangeSpec, action, registry
from fichero.api.library_header import optional_library_path
from fichero.api.auth import request_actor
from pydantic import BaseModel, Field

from fichero.api.main import get_library_database, get_library_database_for_write
from fichero.db import Database
from fichero.llm import LLMConfig, translate_text
from fichero.models import Artifact, ArtifactTypeListResponse, Document

logger = logging.getLogger(__name__)
router = APIRouter()


# Response models
class ArtifactResponse(BaseModel):
    """Artifact response with formatted data."""

    id: str
    document_id: str
    artifact_type: str
    content: Optional[str] = None
    data: Optional[dict] = None
    version: int
    provider: Optional[str] = None
    model: Optional[str] = None
    confidence: Optional[float] = None
    reviewed: bool
    created_at: str


class ArtifactListResponse(BaseModel):
    """Standardized {items, count} envelope for listing artifacts."""

    items: list[ArtifactResponse]
    count: int


class ArtifactCreateRequest(BaseModel):
    """Create a processing artifact for a document.

    This is the public API counterpart to workflow tools saving
    ``Artifact`` rows internally. Importers use it so imported, already
    processed corpora materialize the same transcription/entity/catalogue
    artifacts SwiftUI reads after an in-app workflow run.
    """

    document_id: str
    artifact_type: str
    content: Optional[str] = None
    data: Optional[dict] = None
    source_artifact_id: Optional[str] = None
    version: int = 1
    source_document_id: Optional[str] = None
    run_id: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    step_name: Optional[str] = None
    confidence: Optional[float] = None
    reviewed: bool = False


class ArtifactUpdateActionParams(BaseModel):
    artifact_id: str
    patch: "ArtifactUpdate"


class ArtifactDeleteActionParams(BaseModel):
    artifact_id: str


class ArtifactRestoreActionParams(BaseModel):
    payload: dict[str, Any]


def _artifact_response(artifact: Artifact) -> ArtifactResponse:
    return ArtifactResponse(
        id=artifact.id,
        document_id=artifact.document_id,
        artifact_type=artifact.artifact_type,
        content=artifact.content,
        data=artifact.data,
        version=artifact.version,
        provider=artifact.provider,
        model=artifact.model,
        confidence=artifact.confidence,
        reviewed=artifact.reviewed,
        created_at=artifact.created_at.isoformat() if artifact.created_at else "",
    )


def _resolve_action_ctx(
    *,
    actor: str,
    library_path: str | None,
    origin_window: str | None,
    db: Database,
) -> ActionContext:
    return ActionContext(
        actor=actor,
        library_path=library_path or str(db.path.parent),
        origin_window=origin_window,
    )


def _create_artifact_impl(db: Database, request: ArtifactCreateRequest) -> Artifact:
    doc = db.get(Document, request.document_id)
    if not doc:
        raise HTTPException(
            status_code=404,
            detail=f"Document not found: {request.document_id}",
        )
    artifact_type = request.artifact_type.strip()
    if not artifact_type:
        raise HTTPException(status_code=422, detail="artifact_type is required")
    artifact = Artifact(
        document_id=request.document_id,
        artifact_type=artifact_type,
        content=request.content,
        data=request.data,
        source_artifact_id=request.source_artifact_id,
        version=request.version,
        source_document_id=request.source_document_id,
        run_id=request.run_id,
        provider=request.provider,
        model=request.model,
        step_name=request.step_name,
        confidence=request.confidence,
        reviewed=request.reviewed,
    )
    db.save(artifact)
    return artifact


def _update_artifact_impl(
    db: Database, artifact_id: str, update: "ArtifactUpdate"
) -> tuple[Artifact, dict[str, Any]]:
    artifact = db.get(Artifact, artifact_id)
    if not artifact:
        raise HTTPException(
            status_code=404, detail=f"Artifact not found: {artifact_id}"
        )
    before = artifact.model_dump(mode="json")
    if update.content is not None:
        artifact.content = update.content
    if update.reviewed is not None:
        artifact.reviewed = update.reviewed
    db.save(artifact)
    return artifact, before


def _delete_artifact_impl(db: Database, artifact_id: str) -> dict[str, Any]:
    artifact = db.get(Artifact, artifact_id)
    if not artifact:
        raise HTTPException(
            status_code=404, detail=f"Artifact not found: {artifact_id}"
        )
    before = artifact.model_dump(mode="json")
    # Translation and other artifact-scope embeddings must be removed when the
    # artifact is deleted so stale vectors don't linger in search results.
    if artifact.artifact_type == "translation":
        try:
            db.delete_artifact_embeddings(artifact_id, embedding_scope="translation")
        except Exception:
            logger.debug("No translation embedding rows for %s (expected on first delete)", artifact_id)
    elif artifact.artifact_type == "translation_review":
        try:
            db.delete_artifact_embeddings(artifact_id, embedding_scope="translation")
        except Exception:
            logger.debug("No translation embedding rows for %s (expected on first delete)", artifact_id)
    db.delete(artifact)
    logger.info(f"Deleted artifact {artifact_id}")
    return before


def _restore_artifact_impl(db: Database, payload: dict[str, Any]) -> Artifact:
    artifact = Artifact(**payload)
    db.save(artifact)
    return artifact


def _invert_artifact_to_restore(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    if not before:
        return None
    return ("artifact.restore", {"payload": before})


def _invert_artifact_create(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    if not after:
        return None
    artifact_id = after.get("artifact_id")
    if not artifact_id:
        return None
    return ("artifact.delete", {"artifact_id": artifact_id})


# Routes


@router.post("/", response_model=ArtifactResponse)
async def create_artifact(
    request: ArtifactCreateRequest,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str | None = Depends(optional_library_path),
    x_fichero_origin_window: str | None = Header(
        default=None,
        alias="X-Fichero-Origin-Window",
    ),
    actor: str = Depends(request_actor),
) -> ArtifactResponse:
    ctx = _resolve_action_ctx(
        actor=actor,
        library_path=x_fichero_library_path,
        origin_window=x_fichero_origin_window,
        db=db,
    )
    result = registry.invoke(
        db,
        "artifact.create",
        request.model_dump(mode="json"),
        ctx,
    )
    return ArtifactResponse.model_validate(result.result)


@router.get("/")
async def list_all_artifacts(
    artifact_type: Optional[str] = Query(None, description="Filter by artifact type"),
    limit: int = Query(100, ge=1, le=500, description="Max results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: Database = Depends(get_library_database),
) -> ArtifactListResponse:
    """List all artifacts in the library.

    Returns artifacts sorted by creation date (newest first).
    """
    query_kwargs = {}
    if artifact_type:
        query_kwargs["artifact_type"] = artifact_type

    artifacts = (
        db.query(Artifact, **query_kwargs) if query_kwargs else db.query(Artifact)
    )
    artifacts.sort(key=lambda a: a.created_at, reverse=True)

    total = len(artifacts)
    artifacts = artifacts[offset : offset + limit]

    response_artifacts = [_artifact_response(a) for a in artifacts]
    return ArtifactListResponse(items=response_artifacts, count=total)


@router.get("/types", response_model=ArtifactTypeListResponse)
async def list_artifact_types(
    db: Database = Depends(get_library_database),
) -> ArtifactTypeListResponse:
    """List all artifact types in the library.

    Useful for filtering UI.
    """
    artifacts = db.query(Artifact)
    types = set(a.artifact_type for a in artifacts if a.artifact_type)
    items = sorted(types)
    return ArtifactTypeListResponse(items=items, count=len(items))


@router.get("/document/{doc_id}")
async def list_document_artifacts(
    doc_id: str,
    artifact_type: Optional[str] = Query(None, description="Filter by artifact type"),
    limit: int = Query(50, ge=1, le=200, description="Max results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    include_descendants: bool = Query(
        True,
        description=(
            "Include artifacts from children and parent (legacy aggregation). "
            "Set false for strict per-document scope — V2 inspector uses this so "
            "delete operations are visibly per-artifact rather than confused by "
            "sibling artifacts."
        ),
    ),
    db: Database = Depends(get_library_database),
) -> ArtifactListResponse:
    """List all artifacts for a document.

    Returns artifacts sorted by creation date (newest first).
    """
    # Verify document exists
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")

    if include_descendants:
        # Legacy aggregation: doc itself + direct children (pages) + parent
        # (transcription workflows historically save artifacts on the parent
        # PDF, not per page). Used by the V1 inspector. Causes "delete pops
        # back" confusion in V2 where each artifact gets its own panel —
        # deleting a child's artifact made the parent's similar artifact
        # appear to "respawn" because it was always there in the aggregate.
        children = db.query(Document, parent_id=doc_id)
        child_ids = [d.id for d in children]
        # Map page-child doc_id → sequence so we can sort artifacts by page
        # number (ascending) rather than creation time (#1271).
        page_sequence: dict[str, int] = {d.id: (d.sequence or 0) for d in children}
        all_doc_ids = [doc_id] + child_ids
        if doc.parent_id:
            all_doc_ids.append(doc.parent_id)
    else:
        page_sequence = {}
        all_doc_ids = [doc_id]

    # Query artifacts across the resolved doc IDs
    all_artifacts = []
    for did in all_doc_ids:
        query_kwargs: dict = {"document_id": did}
        if artifact_type:
            query_kwargs["artifact_type"] = artifact_type
        all_artifacts.extend(db.query(Artifact, **query_kwargs))

    artifacts = all_artifacts

    # Sort: non-page artifacts newest-first; page-child artifacts by page
    # sequence ascending so transcription panels read in document order (#1271).
    def _sort_key(a: Artifact) -> tuple:
        if a.document_id in page_sequence:
            return (1, page_sequence[a.document_id], 0.0)
        return (0, 0, -(a.created_at.timestamp() if a.created_at else 0.0))

    artifacts.sort(key=_sort_key)

    # Apply pagination
    total = len(artifacts)
    artifacts = artifacts[offset : offset + limit]

    # Convert to response format
    response_artifacts = [_artifact_response(a) for a in artifacts]

    return ArtifactListResponse(items=response_artifacts, count=total)


@router.get("/{artifact_id}")
async def get_artifact(
    artifact_id: str,
    db: Database = Depends(get_library_database),
) -> ArtifactResponse:
    """Get a specific artifact by ID."""
    artifact = db.get(Artifact, artifact_id)
    if not artifact:
        raise HTTPException(
            status_code=404, detail=f"Artifact not found: {artifact_id}"
        )

    return _artifact_response(artifact)


class ArtifactUpdate(BaseModel):
    """Request to update an artifact's editable fields. Used by the V2
    inspector's per-panel edit. Only `content` is editable today; provider,
    model, version etc. are immutable provenance and stay set by the tool
    that produced them.
    """

    content: Optional[str] = None
    reviewed: Optional[bool] = None


ArtifactUpdateActionParams.model_rebuild(
    _types_namespace={"ArtifactUpdate": ArtifactUpdate}
)


@router.put("/{artifact_id}")
async def update_artifact(
    artifact_id: str,
    update: ArtifactUpdate,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str | None = Depends(optional_library_path),
    x_fichero_origin_window: str | None = Header(
        default=None,
        alias="X-Fichero-Origin-Window",
    ),
    actor: str = Depends(request_actor),
) -> ArtifactResponse:
    """Update an artifact's editable fields (content, reviewed flag).

    Used by the V2 inspector to let users correct workflow output (e.g. fix
    OCR mistakes in a transcription) without re-running the whole tool. The
    artifact stays attached to its original document and keeps its provider/
    model provenance — we just update the text.
    """
    ctx = _resolve_action_ctx(
        actor=actor,
        library_path=x_fichero_library_path,
        origin_window=x_fichero_origin_window,
        db=db,
    )
    result = registry.invoke(
        db,
        "artifact.update",
        {"artifact_id": artifact_id, "patch": update.model_dump(mode="json")},
        ctx,
    )
    return ArtifactResponse.model_validate(result.result)


@router.delete("/{artifact_id}", status_code=204)
async def delete_artifact(
    artifact_id: str,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str | None = Depends(optional_library_path),
    x_fichero_origin_window: str | None = Header(
        default=None,
        alias="X-Fichero-Origin-Window",
    ),
    actor: str = Depends(request_actor),
) -> None:
    """Delete an artifact."""
    ctx = _resolve_action_ctx(
        actor=actor,
        library_path=x_fichero_library_path,
        origin_window=x_fichero_origin_window,
        db=db,
    )
    registry.invoke(
        db,
        "artifact.delete",
        {"artifact_id": artifact_id},
        ctx,
    )


@action(
    "artifact.create",
    ArtifactCreateRequest,
    domains=["artifact", "document"],
    undoable=True,
    invert=_invert_artifact_create,
)
def _action_create_artifact(
    db: Database, params: ArtifactCreateRequest, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    artifact = _create_artifact_impl(db, params)
    spec = ChangeSpec(
        domains=["artifact", "document"],
        target_ids=[artifact.id],
        after={"artifact_id": artifact.id},
        emit_type="artifact.created",
        artifact_ids=[artifact.id],
        document_ids=[artifact.document_id],
    )
    return _artifact_response(artifact).model_dump(mode="json"), spec


@action(
    "artifact.update",
    ArtifactUpdateActionParams,
    domains=["artifact", "document"],
    undoable=True,
    invert=_invert_artifact_to_restore,
)
def _action_update_artifact(
    db: Database, params: ArtifactUpdateActionParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    artifact, before = _update_artifact_impl(db, params.artifact_id, params.patch)
    spec = ChangeSpec(
        domains=["artifact", "document"],
        target_ids=[artifact.id],
        before=before,
        after=artifact.model_dump(mode="json"),
        emit_type="artifact.updated",
        artifact_ids=[artifact.id],
        document_ids=[artifact.document_id],
    )
    return _artifact_response(artifact).model_dump(mode="json"), spec


@action(
    "artifact.delete",
    ArtifactDeleteActionParams,
    domains=["artifact", "document"],
    undoable=True,
    invert=_invert_artifact_to_restore,
)
def _action_delete_artifact(
    db: Database, params: ArtifactDeleteActionParams, ctx: ActionContext
) -> tuple[None, ChangeSpec]:
    before = _delete_artifact_impl(db, params.artifact_id)
    spec = ChangeSpec(
        domains=["artifact", "document"],
        target_ids=[params.artifact_id],
        before=before,
        after={"artifact_id": params.artifact_id},
        emit_type="artifact.deleted",
        artifact_ids=[params.artifact_id],
        document_ids=[before["document_id"]],
    )
    return None, spec


@action(
    "artifact.restore",
    ArtifactRestoreActionParams,
    domains=["artifact", "document"],
    undoable=False,
)
def _action_restore_artifact(
    db: Database, params: ArtifactRestoreActionParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    artifact = _restore_artifact_impl(db, params.payload)
    spec = ChangeSpec(
        domains=["artifact", "document"],
        target_ids=[artifact.id],
        after={"artifact_id": artifact.id},
        emit_type="artifact.created",
        artifact_ids=[artifact.id],
        document_ids=[artifact.document_id],
    )
    return _artifact_response(artifact).model_dump(mode="json"), spec


# =============================================================================
# artifact.translate action (#3325)
# =============================================================================


class ArtifactTranslateParams(BaseModel):
    """Request to translate a document and persist the result as a searchable artifact.

    Wraps the engine's translation path (DeepL when configured, LLM fallback)
    in an audited action so SwiftUI, chat, and App Intents can trigger a
    translation without authoring a workflow.  The resulting artifact is
    embedded with ``embedding_scope='translation'`` so it is discoverable by
    semantic and fulltext search alongside the original.
    """

    document_id: str = Field(description="Document to translate")
    target_lang: str = Field(description="Target language (e.g. 'en', 'es', 'fr')")
    source_lang: str = Field(default="auto", description="Source language ('auto' to detect)")
    provider: str | None = Field(default=None, description="LLM provider override (optional)")


class ArtifactTranslateUndoParams(BaseModel):
    artifact_id: str


def _invert_translate(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    """Undo a translation by deleting the artifact (and its vectors)."""
    if not after or "artifact_id" not in after:
        return None
    return ("artifact.delete", {"artifact_id": after["artifact_id"]})


@action(
    "artifact.translate",
    ArtifactTranslateParams,
    domains=["artifact", "document"],
    undoable=True,
    invert=_invert_translate,
)
def _action_translate(
    db: Database, params: ArtifactTranslateParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    """Translate a document and persist the result as a searchable artifact."""
    import asyncio


    doc = db.get(Document, params.document_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document not found: {params.document_id}")

    text = getattr(doc, "page_content", None) or ""
    if not text.strip():
        raise HTTPException(
            status_code=422,
            detail=f"Document {params.document_id} has no text content to translate",
        )

    # Build an LLMConfig — explicit provider wins, else default
    llm_config = LLMConfig(
        provider=params.provider or "openai",
        model="gpt-4o-mini",
    )

    # Run the translation (async, off the sync action handler)
    translated = asyncio.get_event_loop().run_until_complete(
        translate_text(
            text,
            source_lang=params.source_lang,
            target_lang=params.target_lang,
            config=llm_config,
        )
    )

    # Save the translation artifact
    from fichero.models import Artifact as ArtifactModel

    artifact = ArtifactModel(
        document_id=params.document_id,
        source_document_id=params.document_id,
        artifact_type="translation",
        content=translated,
        provider=llm_config.provider,
        model=llm_config.model,
    )
    db.save(artifact)

    # Embed the translation content with the translation scope
    try:
        db.embed_artifact_content(
            doc, translated, artifact_id=artifact.id,
            embedding_scope="translation",
        )
    except Exception as embed_exc:
        logger.error(
            "Translation embedding failed for artifact %s on doc %s: %s",
            artifact.id, params.document_id, embed_exc,
        )

    spec = ChangeSpec(
        domains=["artifact", "document"],
        target_ids=[artifact.id],
        after={"artifact_id": artifact.id, "document_id": params.document_id},
        emit_type="artifact.created",
        artifact_ids=[artifact.id],
        document_ids=[params.document_id],
    )
    return _artifact_response(artifact).model_dump(mode="json"), spec
