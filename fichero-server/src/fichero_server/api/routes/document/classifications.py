"""User-extensible classification registry (#915).

Lets researchers add their own ``epistemic_status`` / ``claim_type`` /
``entity_type`` values without code changes. Built-in values (seeded
on first run) cannot be deleted; user-added values can be edited
freely.
"""

from __future__ import annotations

import logging
from fichero_server.core.timeutil import utc_now

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from fichero_server.api.auth import action_context
from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.actions.registry import registry
from fichero_server.db import Database
from fichero_server.models.knowledge import (
    ClassificationDimension,
    ClassificationValue,
)
from fichero_server.models import ClassificationListResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/classifications")


# Built-in seed values mirror the existing hardcoded enums so a fresh
# library has all the defaults available before the user customises.
_BUILTIN_SEEDS: list[tuple[ClassificationDimension, str, str, str | None]] = [
    (ClassificationDimension.epistemic_status, "confirmed", "Confirmed", "#34C759"),
    (ClassificationDimension.epistemic_status, "tentative", "Tentative", "#FF9500"),
    (ClassificationDimension.epistemic_status, "rejected", "Rejected", "#FF3B30"),
    (ClassificationDimension.claim_type, "fact", "Fact", "#0A84FF"),
    (ClassificationDimension.claim_type, "analysis", "Analysis", "#5856D6"),
    (ClassificationDimension.claim_type, "interpretation", "Interpretation", "#AF52DE"),
    (ClassificationDimension.claim_type, "argument", "Argument", "#FF2D55"),
    (ClassificationDimension.claim_type, "historiography", "Historiography", "#BF5AF2"),
    (ClassificationDimension.claim_type, "theory", "Theory", "#64D2FF"),
    (ClassificationDimension.entity_type, "person", "Person", "#0A84FF"),
    (ClassificationDimension.entity_type, "location", "Place", "#30D158"),
    (ClassificationDimension.entity_type, "organization", "Organization", "#5856D6"),
    (ClassificationDimension.entity_type, "event", "Event", "#FF9500"),
    (ClassificationDimension.entity_type, "concept", "Concept", "#FFD60A"),
    (ClassificationDimension.entity_type, "other", "Other", "#8E8E93"),
    (ClassificationDimension.document_prototype, "book", "Book", "#0A84FF"),
    (ClassificationDimension.document_prototype, "folder", "Folder", "#8E8E93"),
    (ClassificationDimension.document_prototype, "letter", "Letter", "#30D158"),
    (ClassificationDimension.document_prototype, "interview", "Interview", "#FF9500"),
    (ClassificationDimension.document_prototype, "primary_source", "Primary Source", "#5856D6"),
    (ClassificationDimension.document_prototype, "research_workspace", "Research Workspace", "#0A84FF"),
    (ClassificationDimension.document_prototype, "room", "Room", "#BF5AF2"),
    (ClassificationDimension.document_prototype, "secondary_source", "Secondary Source", "#AF52DE"),
    (ClassificationDimension.document_prototype, "map", "Map", "#64D2FF"),
    (ClassificationDimension.document_prototype, "translation", "Translation", "#FFD60A"),
    (ClassificationDimension.node_class, "chapter", "Chapter", "#0A84FF"),
    (ClassificationDimension.node_class, "container", "Container", "#5856D6"),
    (ClassificationDimension.node_class, "note", "Note", "#FF9500"),
]


def _seed_if_empty(db: Database) -> None:
    """Idempotent seed of built-in values when the table is fresh."""
    existing = db.query(ClassificationValue)
    by_key = {(v.dimension, v.key) for v in existing}
    for dim, key, label, color in _BUILTIN_SEEDS:
        if (dim, key) in by_key:
            continue
        db.save(ClassificationValue(
            dimension=dim,
            key=key,
            label=label,
            color=color,
            is_builtin=True,
        ))


@router.get(
    "",
    response_model=ClassificationListResponse,
    summary="List classification values (filter by dimension)",
)
async def list_values(
    dimension: ClassificationDimension | None = Query(default=None),
    db: Database = Depends(get_library_database),
) -> ClassificationListResponse:
    _seed_if_empty(db)
    rows = db.query(ClassificationValue)
    if dimension is not None:
        rows = [r for r in rows if r.dimension == dimension]
    rows.sort(key=lambda r: (r.dimension.value, r.sort_order, r.label))
    return ClassificationListResponse(items=rows, count=len(rows))


class ResolvedPrototypeResponse(BaseModel):
    """A prototype's EFFECTIVE attributes — parent chain merged root→leaf."""

    key: str
    declarations: dict
    defaults: dict


@router.get(
    "/resolved/{key}",
    response_model=ResolvedPrototypeResponse,
    summary="A prototype's effective attributes (inheritance resolved)",
)
async def resolved_prototype(
    key: str,
    db: Database = Depends(get_library_database),
) -> ResolvedPrototypeResponse:
    """Resolve a document prototype's inherited attributes for the editor UI.

    422 on an unknown key or a cyclic parent chain — the resolver prefers
    raising over partial attributes, and so does this surface.
    """
    from fichero_server.models.node_prototypes import (
        PrototypeResolutionError,
        resolve_prototype_attributes,
    )
    from fichero_server.models.prototype_schema import attribute_declarations

    try:
        effective = resolve_prototype_attributes(db, key)
        decls = attribute_declarations(effective)
    except (PrototypeResolutionError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ResolvedPrototypeResponse(
        key=key,
        declarations={n: d.model_dump(mode="json") for n, d in decls.items()},
        defaults={n: d.default for n, d in decls.items()},
    )


class ClassificationCreateRequest(BaseModel):
    dimension: ClassificationDimension
    key: str
    label: str
    description: str | None = None
    parent_key: str | None = None
    color: str | None = None
    icon: str | None = None
    sort_order: int = 0
    # Prototype attributes (dimension=document_prototype): typed declarations
    # or legacy plain defaults — validated by prototype_schema on save.
    attributes: dict = {}


def _validate_prototype_schema(
    dimension: ClassificationDimension, attributes: dict | None, *, db: Database | None = None, key: str | None = None
) -> None:
    """422 on an unknown attribute type/role in a prototype declaration.

    Loud at SAVE time (datasets Stage 1): a silently dropped or mistyped
    column is how extraction QA lies. Non-prototype dimensions carry free-form
    attributes and are left alone.
    """
    if dimension != ClassificationDimension.document_prototype or not attributes:
        return
    from fichero_server.models.prototype_schema import validate_prototype_attributes

    try:
        validate_prototype_attributes(attributes)
        if db is not None and key:
            from fichero_server.models.node_prototypes import check_level_defaults

            check_level_defaults(db, key, attributes)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def create_value_impl(
    db: Database, request: ClassificationCreateRequest
) -> ClassificationValue:
    """Create a custom (non-builtin) classification value.

    The proven create logic, extracted so BOTH the typed route and the audited
    ``classification.create`` action run the *same* code (iterate-not-replace,
    EPIC #1848 / #2014). Rejects a duplicate ``(dimension, key)`` with 409.
    """
    for existing in db.query(ClassificationValue):
        if existing.dimension == request.dimension and existing.key == request.key:
            raise HTTPException(
                409,
                f"{request.dimension.value}={request.key} already exists",
            )
    _validate_prototype_schema(request.dimension, request.attributes, db=db, key=request.key)
    value = ClassificationValue(**request.model_dump(), is_builtin=False)
    db.save(value)
    return value


@router.post(
    "",
    response_model=ClassificationValue,
    summary="Add a custom classification value",
)
async def create_value(
    request: ClassificationCreateRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> ClassificationValue:
    result = registry.invoke(
        db,
        "classification.create",
        request.model_dump(mode="json"),
        ctx,
    )
    return ClassificationValue.model_validate(result.result)


class ClassificationPatchRequest(BaseModel):
    label: str | None = None
    description: str | None = None
    parent_key: str | None = None
    color: str | None = None
    icon: str | None = None
    sort_order: int | None = None
    attributes: dict | None = None


def patch_value_impl(
    db: Database, value_id: str, request: ClassificationPatchRequest
) -> ClassificationValue:
    """Apply a partial edit to a classification value (404 if missing).

    Extracted so the typed route and ``classification.patch`` share one path.
    ``exclude_unset`` preserves PATCH semantics — only provided fields change.
    """
    value = db.get(ClassificationValue, value_id)
    if value is None:
        raise HTTPException(404, f"Value not found: {value_id}")
    if request.attributes is not None:
        _validate_prototype_schema(value.dimension, request.attributes, db=db, key=value.key)
    for field, val in request.model_dump(exclude_unset=True).items():
        setattr(value, field, val)
    value.updated_at = utc_now()
    db.save(value)
    return value


@router.patch(
    "/{value_id}",
    response_model=ClassificationValue,
    summary="Edit a classification value's label / color / order",
)
async def patch_value(
    value_id: str,
    request: ClassificationPatchRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> ClassificationValue:
    result = registry.invoke(
        db,
        "classification.patch",
        {
            "value_id": value_id,
            **request.model_dump(mode="json", exclude_unset=True),
        },
        ctx,
    )
    return ClassificationValue.model_validate(result.result)


def delete_value_impl(db: Database, value_id: str) -> ClassificationValue:
    """Hard-delete a custom classification value; returns the removed row.

    404 if missing, 409 if built-in (built-ins are never deletable). Returning
    the deleted object lets ``classification.delete`` snapshot it as the undo
    payload so ``classification.restore`` can re-create it with the same id.
    """
    value = db.get(ClassificationValue, value_id)
    if value is None:
        raise HTTPException(404, f"Value not found: {value_id}")
    if value.is_builtin:
        raise HTTPException(
            409, f"Built-in value {value.dimension.value}={value.key} cannot be deleted",
        )
    db.delete(value)
    return value


@router.delete("/{value_id}", status_code=204)
async def delete_value(
    value_id: str,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> None:
    registry.invoke(db, "classification.delete", {"value_id": value_id}, ctx)


# ---------------------------------------------------------------------------
# Action layer registration (EPIC #1848 / sweep #2014) — classification/ontology
# ---------------------------------------------------------------------------
#
# Every classification mutation (create / patch / delete) becomes a registered,
# audited action that WRAPS the proven ``*_impl`` above — the typed routes stay
# green and untouched; the action is the additional uniform path that chat tools
# / App Intents / tests drive via POST /api/actions/invoke. All three are
# undoable: ``before``/``after`` snapshots ARE the undo payload, and the typed
# inverse derives from them (delete -> restore -> delete is a clean redo chain).
#
# Covers all dimensions — claim_type ("claim-kinds"), epistemic_status
# ("epistemic-statuses"), entity_type, document_prototype, node_class — since
# they share one ClassificationValue table and one CRUD surface (#915).

from fichero_server.actions.registry import action, ActionContext, ChangeSpec  # noqa: E402


def _snap_value(value: ClassificationValue) -> dict:
    """JSON-able snapshot of a classification value (the undo payload)."""
    return value.model_dump(mode="json")


class ClassificationPatchParams(ClassificationPatchRequest):
    """``classification.patch`` params — the patch fields plus the target id."""

    value_id: str


class ClassificationDeleteParams(BaseModel):
    value_id: str


class ClassificationRestoreParams(BaseModel):
    """``classification.restore`` — re-materialize a deleted value by snapshot."""

    snapshot: dict


def _invert_create(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    """Undo a create by hard-deleting the value it produced."""
    if not after:
        return None
    vid = after.get("id")
    if not vid:
        return None
    return ("classification.delete", {"value_id": vid})


def _invert_patch(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    """Undo a patch by re-applying the pre-edit field values."""
    if not before:
        return None
    fields = {
        k: before.get(k)
        for k in ("label", "description", "parent_key", "color", "icon", "sort_order")
    }
    return ("classification.patch", {"value_id": before["id"], **fields})


def _invert_delete(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    """Undo a delete by restoring the full pre-delete snapshot (same id)."""
    if not before:
        return None
    return ("classification.restore", {"snapshot": before})


def _invert_restore(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    """Undo a restore by deleting again (so delete<->restore redo works)."""
    if not after:
        return None
    vid = after.get("id")
    if not vid:
        return None
    return ("classification.delete", {"value_id": vid})


@action(
    "classification.create",
    ClassificationCreateRequest,
    domains=["classification"],
    undoable=True,
    invert=_invert_create,
)
def _action_create_value(
    db: Database, params: ClassificationCreateRequest, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    value = create_value_impl(db, params)
    after = _snap_value(value)
    spec = ChangeSpec(
        domains=["classification"],
        target_ids=[value.id],
        before=None,
        after=after,
        emit_type="classification.created",
    )
    return after, spec


class ClassificationRevertCopyParams(BaseModel):
    """``classification.revert_copy``: take back a built-in's copy (the undo of `classification.patch` on a built-in)."""

    value_ids: list[str]
    documents: list[dict]


def _invert_patch_or_copy(before: dict | None, after: dict | None, ctx: ActionContext) -> tuple[str, dict] | None:
    if before and before.get("copied_for"):
        return ("classification.revert_copy", {"value_ids": before["created_ids"], "documents": before["documents"]})
    return _invert_patch(before, after, ctx)


def _structural_keys() -> set[str]:
    """The engine's own kinds (`folder`, `book`, `opening`, `page`): the code finds openings and containers by these keys, so
    an edit lands on the row itself and never moves every node that carries one onto a copy."""
    from fichero_server.db import _BUILTIN_DOCUMENT_PROTOTYPE_SEEDS

    return {seed["key"] for seed in _BUILTIN_DOCUMENT_PROTOTYPE_SEEDS}


def _copy_builtin_for_edit(db: Database, builtin: ClassificationValue, patch: ClassificationPatchRequest) -> tuple:
    """A column change on a built-in (attributes-and-prototypes.md section 3): a project-owned child whose parent is the
    built-in, assigned on the nodes that carried it, and the change landed on the child. A node carrying a prototype
    that names the built-in for the nodes beneath it (an `eap_box` for `eap_digital_folder`) gets a child of THAT
    prototype naming the new child, so the rows beneath follow without an assignment per folder.
    Returns (the child, the created ids, the snapshots of every document it touched)."""
    from fichero_server.api.routes.document.documents import PrototypeAssignRequest, assign_document_prototype_impl
    from fichero_server.models import Document
    from fichero_server.models.node_prototypes import resolve_prototype_attributes
    from fichero_server.models.prototype_schema import level_defaults

    keys = {v.key for v in db.query(ClassificationValue, dimension=ClassificationDimension.document_prototype)}

    def fresh(base: str) -> str:
        key, n = f"{base}-copy", 2
        while key in keys:
            key, n = f"{base}-copy-{n}", n + 1
        keys.add(key)
        return key

    def make(source: ClassificationValue, attributes: dict) -> ClassificationValue:
        made = create_value_impl(db, ClassificationCreateRequest(
            dimension=source.dimension, key=fresh(source.key), label=f"{source.label} (this project)",
            parent_key=source.key, attributes=attributes))
        created.append(made.id)
        return made

    created: list[str] = []
    before: dict[str, dict] = {}
    child = make(builtin, {})
    holders: dict[str, ClassificationValue] = {}
    for doc in db.all(Document):
        if doc.deleted_at is not None or not doc.prototype_key:
            continue
        if doc.prototype_key == builtin.key:
            target = child
        else:
            try:
                names = level_defaults(resolve_prototype_attributes(db, doc.prototype_key))
            except Exception:  # noqa: BLE001 -- an unresolvable prototype carries nothing for us
                continue
            levels = [level for level, key in names.items() if key == builtin.key]
            holder = _get_proto(db, doc.prototype_key)
            if not levels or holder is None:
                continue
            if holder.key not in holders:  # a copy of the holder naming the child, so the one undo takes it back too
                holders[holder.key] = make(holder, {level: child.key for level in levels})
            target = holders[holder.key]
        before[doc.id] = doc.model_dump(mode="json")
        assign_document_prototype_impl(db, doc.id, PrototypeAssignRequest(prototype_key=target.key))
    landed = patch_value_impl(db, child.id, patch)
    return landed, created, list(before.values())


def _get_proto(db: Database, key: str) -> ClassificationValue | None:
    found = db.query(ClassificationValue, dimension=ClassificationDimension.document_prototype, key=key)
    return found[0] if found else None


@action(
    "classification.revert_copy",
    ClassificationRevertCopyParams,
    domains=["classification", "document"],
    undoable=False,  # ponytail: redo of a built-in's copy is the person's next edit; add an invert if redo is asked for
)
def _action_revert_copy(
    db: Database, params: ClassificationRevertCopyParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    from fichero_server.api.routes.document.documents import restore_documents_impl

    for value_id in params.value_ids:
        value = db.get(ClassificationValue, value_id)
        if value is not None:
            db.delete(value)
    restored = restore_documents_impl(db, documents=params.documents)
    spec = ChangeSpec(domains=["classification", "document"], target_ids=[*params.value_ids, *restored],
                      before=None, after={"deleted": params.value_ids}, emit_type="classification.deleted",
                      document_ids=restored)
    return {"deleted": params.value_ids, "restored": restored}, spec


@action(
    "classification.patch",
    ClassificationPatchParams,
    domains=["classification"],
    undoable=True,
    invert=_invert_patch_or_copy,
)
def _action_patch_value(
    db: Database, params: ClassificationPatchParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    existing = db.get(ClassificationValue, params.value_id)
    if existing is None:
        raise HTTPException(404, f"Value not found: {params.value_id}")
    before = _snap_value(existing)
    patch = ClassificationPatchRequest(
        **params.model_dump(exclude={"value_id"}, exclude_unset=True)
    )
    if (
        existing.is_builtin
        and existing.key not in _structural_keys()
        and patch.attributes is not None
        and existing.dimension == ClassificationDimension.document_prototype
    ):
        value, created, documents = _copy_builtin_for_edit(db, existing, patch)
        before = {**before, "copied_for": existing.key, "created_ids": created, "documents": documents}
        after = _snap_value(value)
        spec = ChangeSpec(domains=["classification", "document"], target_ids=[value.id, *created], before=before,
                          after=after, emit_type="classification.created",
                          document_ids=[d["id"] for d in documents])
        return after, spec
    value = patch_value_impl(db, params.value_id, patch)
    after = _snap_value(value)
    spec = ChangeSpec(
        domains=["classification"],
        target_ids=[value.id],
        before=before,
        after=after,
        emit_type="classification.updated",
    )
    return after, spec


@action(
    "classification.delete",
    ClassificationDeleteParams,
    domains=["classification"],
    undoable=True,
    invert=_invert_delete,
)
def _action_delete_value(
    db: Database, params: ClassificationDeleteParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    deleted = delete_value_impl(db, params.value_id)
    before = _snap_value(deleted)
    spec = ChangeSpec(
        domains=["classification"],
        target_ids=[params.value_id],
        before=before,
        after=None,
        emit_type="classification.deleted",
    )
    return before, spec


@action(
    "classification.restore",
    ClassificationRestoreParams,
    domains=["classification"],
    undoable=True,
    invert=_invert_restore,
)
def _action_restore_value(
    db: Database, params: ClassificationRestoreParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    """Re-create a deleted value from its snapshot (preserving its id)."""
    value = ClassificationValue(**params.snapshot)
    db.save(value)
    after = _snap_value(value)
    spec = ChangeSpec(
        domains=["classification"],
        target_ids=[value.id],
        before=None,
        after=after,
        emit_type="classification.created",
    )
    return after, spec
